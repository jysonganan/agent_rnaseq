"""LangGraph stage nodes that dispatch to specialist sub-agents.

Each node:
1. Checks the run has not been cancelled.
2. Builds the specialist's typed input(s) deterministically (``stage_inputs``).
3. Runs the specialist (per sample, or once) — the specialist calls the tools,
   validates outputs via Pydantic, and writes PipelineStage/result/artifact rows.
4. Commits, records the validated output in ``RunState.stage_outputs`` and
   checkpoints the merged state to ``AnalysisRun.agent_state``.

No LLM call happens here: all numbers come from tool outputs.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from src.agents.base_agent import MockToolRegistry
from src.agents.run_events import NullRunEvents, RunEvents, output_excerpt
from src.agents.sanitize import sanitize_text
from src.agents.specialists import (
    AlignmentAgent,
    DEAgent,
    GSEAAgent,
    QCAgent,
    QuantificationAgent,
    ReportAgent,
    SplicingAgent,
    VariantAgent,
    VizAgent,
    scRNAAgent,
)
from src.agents.specialists._base import BaseSpecialistAgent
from src.agents.stage_inputs import (
    PER_CONTRAST_STAGES,
    PER_SAMPLE_STAGES,
    PipelineContext,
    build_stage_inputs,
)
from src.agents.state import RunState
from src.db.enums import Executor, RunStatus, StageName, StageStatus

logger = logging.getLogger(__name__)

SPECIALISTS: dict[str, type[BaseSpecialistAgent]] = {
    "qc": QCAgent,
    "alignment": AlignmentAgent,
    "quantification": QuantificationAgent,
    "variant_calling": VariantAgent,
    "splicing": SplicingAgent,
    "differential_expression": DEAgent,
    "gsea": GSEAAgent,
    "scrna_seq": scRNAAgent,
    "visualization": VizAgent,
    "report": ReportAgent,
}

_MAX_ERROR_LEN = 1000

# Tool recorded on the audit row of a failed invocation (matches the specialists).
_STAGE_TOOL: dict[str, str] = {
    "qc": "fastqc",
    "alignment": "star",
    "variant_calling": "gatk",
    "splicing": "rmats",
    "differential_expression": "deseq2",
    "gsea": "reactome_gsea",
    "scrna_seq": "cellranger",
    "visualization": "streamlit",
    "report": "report_compiler",
}
_QUANT_TOOL = {"star_htseq": "htseq", "salmon": "salmon", "rsem": "rsem"}


# Primary tool function per stage, used as ``tool_call.tool_name`` (api_contracts.md).
_STAGE_TOOL_FN: dict[str, str] = {
    "qc": "run_fastqc",
    "alignment": "run_star_align",
    "variant_calling": "run_gatk_haplotypecaller",
    "splicing": "run_rmats",
    "differential_expression": "run_deseq2",
    "gsea": "run_reactome_gsea",
    "scrna_seq": "run_cellranger_count",
    "visualization": "prepare_streamlit_data",
    "report": "compile_report",
}
_QUANT_TOOL_FN = {"star_htseq": "run_htseq_count", "salmon": "run_salmon_quant", "rsem": "run_rsem"}


def _agent_name(stage: str) -> str:
    """Log-frame ``agent`` field, e.g. ``alignment_agent``."""
    return SPECIALISTS[stage].__module__.rsplit(".", 1)[-1]


def _tool_fn(stage: str, rt: StageRuntime) -> str:
    if stage == "quantification":
        if rt.ctx is None:
            return "run_htseq_count"
        from src.agents.stage_inputs import quantification_method

        return _QUANT_TOOL_FN[quantification_method(rt.ctx)]
    return _STAGE_TOOL_FN[stage]


class RunCancelledError(Exception):
    pass


class StageFailure(Exception):
    """Wraps the original error with the input that failed and any finished items."""

    def __init__(self, cause: Exception, failed_input: dict | None, partial: dict | None) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.failed_input = failed_input
        self.partial = partial


@dataclass
class StageRuntime:
    """Everything a stage node needs besides the graph state."""

    db: Session
    ctx: PipelineContext | None  # None only in dry-run mode
    dry_run: bool = False
    mock_registry: MockToolRegistry | None = None
    llm_client: Any = None
    events: RunEvents = field(default_factory=NullRunEvents)


def _run_row(db: Session, run_id: str) -> Any:
    from src.db.models.run import AnalysisRun

    return db.get(AnalysisRun, uuid.UUID(run_id))


def _check_not_cancelled(db: Session, run_id: str) -> None:
    run = _run_row(db, run_id)
    if run is None:
        return
    db.refresh(run, attribute_names=["status"])
    if run.status == RunStatus.cancelled:
        raise RunCancelledError(f"Run {run_id} was cancelled")


def _record_failed_attempt(db: Session, run_id: str, stage: str, inp: dict) -> None:
    """Audit row for an invocation whose own (uncommitted) rows were rolled back."""
    from src.db.models.run import PipelineStage

    tool = _STAGE_TOOL.get(stage) or _QUANT_TOOL.get(inp.get("quantification_method", ""), stage)
    now = datetime.now(UTC)
    db.add(
        PipelineStage(
            run_id=uuid.UUID(run_id),
            sample_id=uuid.UUID(inp["sample_id"]) if inp.get("sample_id") else None,
            stage_name=StageName(stage),
            status=StageStatus.failed,
            tool_name=tool,
            input_params=json.loads(json.dumps(inp, default=str)),
            executor=Executor.local,
            started_at=now,
            completed_at=now,
        )
    )


def _checkpoint(db: Session, state: RunState, update: dict) -> None:
    run = _run_row(db, state["run_id"])
    if run is not None:
        run.agent_state = {**state, **update}
    db.commit()


def _execute(stage: str, state: RunState, rt: StageRuntime) -> dict:
    agent = SPECIALISTS[stage](
        rt.db, llm_client=rt.llm_client, dry_run=rt.dry_run, mock_registry=rt.mock_registry
    )

    if rt.dry_run:
        # Mock mode: no input resolution, no subprocesses, no DB writes.
        result = agent.execute(state)
        if result["status"] != "completed":
            raise RuntimeError(result["error"] or "dry-run stage failed")
        return {"output": result["output"] or {}}

    assert rt.ctx is not None
    inputs = build_stage_inputs(stage, rt.ctx, state.get("stage_outputs", {}))

    if stage in PER_SAMPLE_STAGES or stage in PER_CONTRAST_STAGES:
        key, item_field = (
            ("samples", "sample_id") if stage in PER_SAMPLE_STAGES else ("contrasts", "contrast")
        )
        # Resume: items finished before an earlier failure are not re-run.
        previous = (state.get("stage_outputs", {}).get(stage) or {}).get(key) or {}
        done: dict[str, dict] = dict(previous)
        for inp in inputs:
            item = inp[item_field]
            if item in done:
                continue
            try:
                _check_not_cancelled(rt.db, state["run_id"])
                rt.events.log("info", stage, _agent_name(stage), f"{stage}: starting {item}")
                done[item] = agent.run_stage(inp)
            except RunCancelledError as exc:
                raise StageFailure(exc, None, {key: done}) from exc
            except Exception as exc:
                raise StageFailure(exc, inp, {key: done}) from exc
            rt.db.commit()  # persist each finished item immediately
        return {key: done}

    try:
        return agent.run_stage(inputs[0])
    except Exception as exc:
        raise StageFailure(exc, inputs[0], None) from exc


def make_stage_node(stage: str, rt: StageRuntime) -> Callable[[RunState], dict]:
    """Return the LangGraph node function for ``stage``."""

    def _node(state: RunState) -> dict:
        run_id = state["run_id"]
        logger.info("run=%s stage=%s starting", run_id, stage)
        rt.events.stage_update(stage, "running")
        rt.events.tool_call(_tool_fn(stage, rt), "running")
        rt.events.log("info", stage, _agent_name(stage), f"Stage {stage} started")
        try:
            if not rt.dry_run:
                _check_not_cancelled(rt.db, run_id)
            stage_output = _execute(stage, state, rt)
        except Exception as raw:
            exc = raw.cause if isinstance(raw, StageFailure) else raw
            logger.exception("run=%s stage=%s failed", run_id, stage)
            message = sanitize_text(f"{type(exc).__name__}: {exc}", _MAX_ERROR_LEN)
            update: dict[str, Any] = {
                "current_stage": stage,
                "failed_stage": stage,
                "error_message": message,
            }
            if isinstance(raw, StageFailure) and raw.partial:
                update["stage_outputs"] = {
                    **state.get("stage_outputs", {}),
                    stage: {**raw.partial, "partial": True},
                }
            if not rt.dry_run:
                # Drop the failed invocation's uncommitted result rows (no partial
                # DEG/QC rows survive), but keep an audit record of the attempt.
                rt.db.rollback()
                if isinstance(raw, StageFailure) and raw.failed_input is not None:
                    _record_failed_attempt(rt.db, run_id, stage, raw.failed_input)
                _checkpoint(rt.db, state, update)
            rt.events.stage_update(stage, "failed")
            rt.events.tool_call(_tool_fn(stage, rt), "failed")
            rt.events.log("error", stage, _agent_name(stage), message)
            return update

        completed = list(state.get("completed_stages", []))
        if stage not in completed:
            completed.append(stage)
        update = {
            "current_stage": stage,
            "completed_stages": completed,
            "stage_outputs": {**state.get("stage_outputs", {}), stage: stage_output},
        }
        if not rt.dry_run:
            _checkpoint(rt.db, state, update)
        rt.events.stage_update(stage, "completed")
        rt.events.tool_call(_tool_fn(stage, rt), "completed", output_excerpt(stage_output))
        rt.events.log("info", stage, _agent_name(stage), f"Stage {stage} completed")
        logger.info("run=%s stage=%s completed", run_id, stage)
        return update

    _node.__name__ = f"{stage}_node"
    return _node


def stage_node_factory(rt: StageRuntime) -> Callable[[str], Callable[[RunState], dict]]:
    return lambda stage: make_stage_node(stage, rt)
