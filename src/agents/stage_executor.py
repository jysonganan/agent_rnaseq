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

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.agents.base_agent import MockToolRegistry
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
from src.db.enums import RunStatus, StageName, StageStatus

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


class RunCancelledError(Exception):
    pass


@dataclass
class StageRuntime:
    """Everything a stage node needs besides the graph state."""

    db: Session
    ctx: PipelineContext | None  # None only in dry-run mode
    dry_run: bool = False
    mock_registry: MockToolRegistry | None = None
    llm_client: Any = None


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


def _mark_dangling_stages_failed(db: Session, run_id: str, stage: str) -> None:
    """Specialists only fail their PipelineStage on ToolExecutionError; cover the rest."""
    from src.db.models.run import PipelineStage

    rows = (
        db.query(PipelineStage)
        .filter(
            PipelineStage.run_id == uuid.UUID(run_id),
            PipelineStage.stage_name == StageName(stage),
            PipelineStage.status == StageStatus.running,
        )
        .all()
    )
    for row in rows:
        row.status = StageStatus.failed


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
    if stage in PER_SAMPLE_STAGES:
        per_sample: dict[str, dict] = {}
        for inp in inputs:
            _check_not_cancelled(rt.db, state["run_id"])
            per_sample[inp["sample_id"]] = agent.run(inp)
            rt.db.commit()  # persist each sample's rows as soon as it finishes
        return {"samples": per_sample}
    if stage in PER_CONTRAST_STAGES:
        per_contrast: dict[str, dict] = {}
        for inp in inputs:
            _check_not_cancelled(rt.db, state["run_id"])
            per_contrast[inp["contrast"]] = agent.run(inp)
            rt.db.commit()
        return {"contrasts": per_contrast}
    return agent.run(inputs[0])


def make_stage_node(stage: str, rt: StageRuntime) -> Callable[[RunState], dict]:
    """Return the LangGraph node function for ``stage``."""

    def _node(state: RunState) -> dict:
        run_id = state["run_id"]
        logger.info("run=%s stage=%s starting", run_id, stage)
        try:
            if not rt.dry_run:
                _check_not_cancelled(rt.db, run_id)
            stage_output = _execute(stage, state, rt)
        except Exception as exc:
            logger.exception("run=%s stage=%s failed", run_id, stage)
            if not rt.dry_run:
                _mark_dangling_stages_failed(rt.db, run_id, stage)
            update = {
                "current_stage": stage,
                "failed_stage": stage,
                "error_message": f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_LEN],
            }
            if not rt.dry_run:
                _checkpoint(rt.db, state, update)
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
        logger.info("run=%s stage=%s completed", run_id, stage)
        return update

    _node.__name__ = f"{stage}_node"
    return _node


def stage_node_factory(rt: StageRuntime) -> Callable[[str], Callable[[RunState], dict]]:
    return lambda stage: make_stage_node(stage, rt)
