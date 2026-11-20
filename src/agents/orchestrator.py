from __future__ import annotations

import json
import re
import uuid
from collections.abc import Sequence
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.router import build_pipeline_graph
from src.agents.run_requirements import InputIssue, SampleFacts
from src.agents.state import RunState
from src.config import get_settings
from src.db.enums import Executor, PipelineType, StageName
from src.schemas.run import DEContrast

# Stages whose presence requires other stages to also be in the pipeline.
STAGE_DEPENDENCIES: dict[str, list[str]] = {
    "qc": [],
    "alignment": [],
    "quantification": ["alignment"],
    "variant_calling": ["alignment"],
    "splicing": ["alignment"],
    "differential_expression": ["quantification"],
    "gsea": ["differential_expression"],
    "scrna_seq": [],
    "visualization": [],  # special: at least one of qc/de/gsea — checked separately
    "report": [],  # special: at least one upstream — checked separately
}

_VISUALIZATION_REQUIRES_ONE_OF: frozenset[str] = frozenset(
    {"differential_expression", "gsea", "qc"}
)


class RunConfig(BaseModel):
    run_name: str
    genome_id: str
    pipeline_type: PipelineType = PipelineType.bulk_rnaseq
    stages: list[StageName] = Field(..., min_length=1)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)
    lfc_threshold: float = Field(default=0.0, ge=0.0, le=5.0)
    # User decisions — see docs/specs/api_contracts.md "Analysis inputs".
    de_contrasts: list[DEContrast] = Field(default_factory=list)
    read_length: int | None = Field(default=None, ge=1, le=1000)
    executor: Executor = Executor.local
    dry_run: bool = False  # must be set in API request body, never by LLM


class OrchestratorError(Exception):
    """User-facing error from OrchestratorAgent (dependency, genome, ambiguity)."""


class OrchestratorAgent:
    """Parses user intent, validates RunConfig, and dispatches to LangGraph."""

    def __init__(
        self,
        llm_client: OpenAI | None,
        *,
        dry_run: bool = False,
    ) -> None:
        self._client = llm_client
        self._dry_run = dry_run
        # Stub graph: used by dispatch()/resume() for plan validation without a DB.
        # Real execution goes through execute_run(), which wires specialist nodes.
        self._graph = build_pipeline_graph()

    @property
    def _llm(self) -> OpenAI:
        if self._client is None:
            raise OrchestratorError("This operation requires an LLM client")
        return self._client

    # ── Intent parsing ─────────────────────────────────────────────────────────

    def parse_intent(self, user_message: str, available_genomes: list[dict]) -> dict:
        """Call LLM (single-turn) to extract RunConfig fields from user message."""
        settings = get_settings()
        genome_list = "\n".join(
            f"  - id={g['id']} name={g['name']} species={g.get('species', '')}"
            for g in available_genomes
        )
        system_prompt = (
            "You are an RNA-seq pipeline configuration assistant.\n"
            "Extract pipeline configuration from the user message.\n"
            "Return valid JSON with these fields:\n"
            "  run_name (string), genome_id (string — must be one of the IDs listed),\n"
            "  pipeline_type (bulk_rnaseq or scrna_seq),\n"
            "  stages (array of stage names from: qc, alignment, quantification,\n"
            "    variant_calling, splicing, differential_expression, gsea,\n"
            "    scrna_seq, visualization, report),\n"
            "  alpha (float 0.001–0.1, default 0.05),\n"
            "  lfc_threshold (float 0.0–5.0, default 0.0)\n"
            f"Available genomes:\n{genome_list}\n"
            "Return ONLY valid JSON, no commentary."
        )
        response = self._llm.chat.completions.create(
            model=settings.agent_llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
        )
        raw: str = response.choices[0].message.content or "{}"
        return json.loads(raw)

    # ── Validation ─────────────────────────────────────────────────────────────

    def validate_genome(self, genome_id: str, available_genomes: list[dict]) -> None:
        """Raise OrchestratorError if genome_id is not in the available list."""
        known_ids = {g["id"] for g in available_genomes}
        if genome_id not in known_ids:
            raise OrchestratorError(
                f"Genome '{genome_id}' not found. Available IDs: {sorted(known_ids)}"
            )

    def validate_stage_dependencies(self, stages: list[str]) -> None:
        """Raise OrchestratorError if the stage list violates the dependency map."""
        stage_set = set(stages)
        for stage in stages:
            for dep in STAGE_DEPENDENCIES.get(stage, []):
                if dep not in stage_set:
                    raise OrchestratorError(
                        f"Stage '{stage}' requires '{dep}' to also be in the pipeline."
                    )
        if "visualization" in stage_set and not _VISUALIZATION_REQUIRES_ONE_OF & stage_set:
            raise OrchestratorError(
                "Stage 'visualization' requires at least one of: "
                f"{sorted(_VISUALIZATION_REQUIRES_ONE_OF)}."
            )

    # ── Dispatch & resume ──────────────────────────────────────────────────────

    def dispatch(self, run_config: RunConfig, run_id: str) -> dict[str, Any]:
        """Build initial RunState and invoke the LangGraph pipeline."""
        initial: RunState = {
            "run_id": run_id,
            "run_config": run_config.model_dump(mode="json"),
            "stages": [s.value for s in run_config.stages],
            "completed_stages": [],
            "failed_stage": None,
            "stage_outputs": {},
            "error_message": None,
            "current_stage": None,
        }
        result: dict[str, Any] = self._graph.invoke(initial)
        return result

    def resume(self, checkpoint_state: dict[str, Any]) -> dict[str, Any]:
        """Resume an interrupted pipeline from a DB-persisted state snapshot."""
        result: dict[str, Any] = self._graph.invoke(checkpoint_state)
        return result

    # ── Real execution ─────────────────────────────────────────────────────────

    def execute_run(
        self,
        db: Session,
        run_id: str,
        *,
        output_root: str | None = None,
        mock_registry: Any = None,
    ) -> dict[str, Any]:
        """Execute a persisted AnalysisRun by dispatching each stage to its specialist.

        The plan (stage list) comes from ``AnalysisRun.run_config`` — already validated
        when the run was created — and is re-checked against the dependency map here.
        If ``AnalysisRun.agent_state`` holds a checkpoint, completed stages are skipped
        and a previously failed stage is retried.
        """
        from src.agents.stage_executor import StageRuntime, stage_node_factory
        from src.agents.stage_inputs import load_pipeline_context
        from src.db.models.run import AnalysisRun

        run = db.get(AnalysisRun, uuid.UUID(run_id))
        if run is None:
            raise OrchestratorError(f"Run {run_id} not found")
        stages = [StageName(s).value for s in (run.run_config or {}).get("stages", [])]
        if not stages:
            raise OrchestratorError(f"Run {run_id} has no stages configured")
        self.validate_stage_dependencies(stages)
        # Execute in canonical pipeline order regardless of how the plan was listed.
        from src.agents.router import ALL_PIPELINE_STAGES

        stages = [s for s in ALL_PIPELINE_STAGES if s in stages]

        ctx = None
        if not self._dry_run:
            ctx = load_pipeline_context(db, run_id, output_root or get_settings().output_root)
            self._check_user_inputs(ctx, stages)
            if ctx.executor != Executor.local:
                raise OrchestratorError(
                    f"Executor '{ctx.executor}' is not supported by the agent runner yet; "
                    "use 'local'"
                )

        runtime = StageRuntime(
            db=db,
            ctx=ctx,
            dry_run=self._dry_run,
            mock_registry=mock_registry,
            llm_client=self._client,
        )
        graph = build_pipeline_graph(stage_node_factory(runtime))

        checkpoint = dict(run.agent_state or {})
        state: RunState = {
            "run_id": run_id,
            "run_config": dict(run.run_config or {}),
            "stages": stages,
            "completed_stages": [s for s in checkpoint.get("completed_stages", []) if s in stages],
            "failed_stage": None,  # retry the stage that failed last time
            "stage_outputs": dict(checkpoint.get("stage_outputs", {})),
            "error_message": None,
            "current_stage": None,
        }
        result: dict[str, Any] = graph.invoke(
            state, config={"recursion_limit": 2 * len(stages) + 5}
        )
        return result

    @staticmethod
    def _check_user_inputs(ctx: Any, stages: list[str]) -> None:
        """Refuse to start if contrasts/read length are missing or don't fit the samples."""
        from src.agents.run_requirements import SampleFacts, check_analysis_inputs, format_issues

        try:
            contrasts = [
                DEContrast.model_validate(c) for c in ctx.run_config.get("de_contrasts") or []
            ]
        except Exception as exc:
            raise OrchestratorError(f"Invalid de_contrasts in run config: {exc}") from exc
        facts = [
            SampleFacts(
                sample_id=s.id,
                name=s.name,
                condition=s.condition,
                read_length=s.metadata.get("read_length"),
            )
            for s in ctx.samples
        ]
        issues = check_analysis_inputs(stages, facts, contrasts, ctx.run_config.get("read_length"))
        if issues:
            raise OrchestratorError(format_issues(issues))

    # ── Chat gateway ───────────────────────────────────────────────────────────

    def _build_dispatch_system_prompt(
        self,
        sample_list: list[dict[str, str]],
        genome_list: list[dict[str, str]],
    ) -> str:
        samples_json = json.dumps(sample_list, indent=2)
        genomes_json = json.dumps(genome_list, indent=2)
        return (
            "You are an RNA-seq pipeline assistant. Given the conversation, determine "
            "whether it contains enough information to launch a pipeline run. Earlier "
            "messages may hold the original request; the latest message may be the user's "
            "answer to a follow-up question — combine them.\n\n"
            "Available samples (select sample_ids from this list only — never invent UUIDs):\n"
            f"{samples_json}\n\n"
            "Available genomes (select genome_id from this list only — never invent UUIDs):\n"
            f"{genomes_json}\n\n"
            "Return ONLY valid JSON. If the request is actionable, return:\n"
            '{"type": "run", "run_name": "...", "genome_id": "<exact UUID from list>", '
            '"sample_ids": ["<exact UUID from list>", ...], '
            '"pipeline_type": "bulk_rnaseq|scrna_seq", '
            '"stages": ["qc", "alignment", ...], '
            '"alpha": 0.05, "lfc_threshold": 0.0, '
            '"de_contrasts": [{"numerator": "<condition>", "denominator": "<condition>"}], '
            '"read_length": null}\n\n'
            "Rules for de_contrasts and read_length — these are the user's scientific "
            "decisions, never yours:\n"
            "- de_contrasts: include ONLY comparisons the user explicitly stated in this "
            "conversation. 'A vs B' / 'A versus B' / 'A compared to B' means numerator A, "
            "denominator B. Use condition values from the sample list. Never pick a "
            "comparison or a direction yourself; if the user stated none, return [].\n"
            "- read_length: an integer only if the user explicitly stated the read length; "
            "otherwise null.\n"
            "- If de_contrasts or read_length are the only missing information, still return "
            'type "run" — the system will ask the user for them.\n\n'
            "If the request is ambiguous or missing other required information, return:\n"
            '{"type": "clarification", "question": "..."}'
        )

    @staticmethod
    def _conversation_history(
        db: Session, conversation_id: str, current_message_id: str
    ) -> list[dict[str, str]]:
        """Last ``_HISTORY_LIMIT`` user/assistant turns before the current message."""
        from src.db.enums import MessageRole
        from src.db.models.conversation import ChatMessage

        rows = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.conversation_id == uuid.UUID(conversation_id),
                ChatMessage.id != uuid.UUID(current_message_id),
                ChatMessage.role.in_([MessageRole.user, MessageRole.assistant]),
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(_HISTORY_LIMIT)
            .all()
        )
        return [{"role": str(m.role), "content": m.content} for m in reversed(rows)]

    async def dispatch_from_chat(
        self,
        input: ChatDispatchInput,
        db: Session,
        redis_client: Any | None = None,
    ) -> ChatDispatchOutput:
        """
        Process a chat message: parse intent, validate resources and the user-decided
        analysis inputs, either ask a follow-up question or create the AnalysisRun,
        publish token frames to Redis, write assistant ChatMessage to DB.
        """
        from src.agents.run_requirements import (
            check_analysis_inputs,
            clarification_question,
            sample_facts,
        )
        from src.db.enums import Aligner, AlignmentMode, MessageRole, RunStatus
        from src.db.models.conversation import ChatMessage
        from src.db.models.genome import ReferenceGenome
        from src.db.models.project import RunSample, Sample
        from src.db.models.run import AnalysisRun
        from src.tools.base import ToolValidationError

        settings = get_settings()

        # 1. Query available resources before calling LLM (anti-hallucination)
        samples = db.query(Sample).all()
        genomes = db.query(ReferenceGenome).all()
        sample_list = [
            {
                "id": str(s.id),
                "name": s.name,
                "condition": s.condition or "",
                "sample_type": str(s.sample_type),
            }
            for s in samples
        ]
        genome_list = [{"id": str(g.id), "name": g.name, "build": g.build} for g in genomes]

        # 2. Parse intent over the conversation so far (non-streaming, JSON mode)
        history = self._conversation_history(db, input.conversation_id, input.message_id)
        user_texts = [m["content"] for m in history if m["role"] == "user"]
        user_texts.append(input.user_content)

        system_prompt = self._build_dispatch_system_prompt(sample_list, genome_list)
        intent_resp = self._llm.chat.completions.create(
            model=settings.agent_llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": input.user_content},
            ],
            response_format={"type": "json_object"},
        )
        intent = json.loads(intent_resp.choices[0].message.content or "{}")

        run_id: str | None = None
        question: str | None = None
        validated: RunConfig | None = None

        if intent.get("type", "clarification") != "run":
            question = str(intent.get("question") or "Could you clarify your request?")
        else:
            # 3. Re-validate selected IDs against DB
            selected_genome_id = intent.get("genome_id", "")
            selected_sample_ids: list[str] = list(dict.fromkeys(intent.get("sample_ids") or []))

            known_genome_ids = {str(g.id) for g in genomes}
            if selected_genome_id not in known_genome_ids:
                raise ToolValidationError(
                    "dispatch_from_chat",
                    "genome_id",
                    f"Genome ID '{selected_genome_id}' is not registered in the database",
                )
            by_id = {str(s.id): s for s in samples}
            for sid in selected_sample_ids:
                if sid not in by_id:
                    raise ToolValidationError(
                        "dispatch_from_chat",
                        "sample_ids",
                        f"Sample ID '{sid}' is not in the database",
                    )
            selected = [by_id[sid] for sid in selected_sample_ids]
            facts = sample_facts(selected)

            # 4. User-decided inputs: keep only values the user actually stated
            contrasts, contrast_issues = _contrasts_stated_by_user(
                intent.get("de_contrasts"), facts, user_texts
            )
            read_length = _number_stated_by_user(intent.get("read_length"), user_texts)

            try:
                stages = [StageName(s) for s in intent.get("stages", ["qc"])]
                self.validate_stage_dependencies([s.value for s in stages])
                candidate = RunConfig(
                    run_name=intent.get("run_name", "Chat run"),
                    genome_id=selected_genome_id,
                    pipeline_type=PipelineType(intent.get("pipeline_type", "bulk_rnaseq")),
                    stages=stages,
                    alpha=float(intent.get("alpha", 0.05)),
                    lfc_threshold=float(intent.get("lfc_threshold", 0.0)),
                    de_contrasts=contrasts,
                    read_length=read_length,
                    executor=Executor.local,
                    dry_run=False,
                )
            except OrchestratorError as exc:
                question = f"{exc} Which stages would you like to run?"
            except Exception as exc:
                raise ToolValidationError(
                    "dispatch_from_chat", "run_config", f"Invalid run configuration: {exc}"
                ) from exc
            else:
                if not selected:
                    question = "Which samples should I include in this run?"
                else:
                    issues = contrast_issues + check_analysis_inputs(
                        [s.value for s in candidate.stages],
                        facts,
                        candidate.de_contrasts,
                        candidate.read_length,
                    )
                    if issues:
                        question = clarification_question(issues, facts)
                    else:
                        validated = candidate

            if validated is not None:
                # 5. Create AnalysisRun (Pydantic-validated params — no raw LLM numerics)
                run = AnalysisRun(
                    project_id=selected[0].project_id,
                    genome_id=uuid.UUID(selected_genome_id),
                    created_by=uuid.UUID(input.api_key_id),
                    name=validated.run_name,
                    status=RunStatus.pending,
                    pipeline_type=validated.pipeline_type,
                    alignment_mode=AlignmentMode.genome,
                    aligner=Aligner.star,
                    run_config={
                        **validated.model_dump(mode="json"),
                        "sample_ids": selected_sample_ids,
                    },
                    conversation_id=uuid.UUID(input.conversation_id),
                    triggering_message_id=uuid.UUID(input.message_id),
                )
                db.add(run)
                db.flush()
                for sid in selected_sample_ids:
                    db.add(RunSample(run_id=run.id, sample_id=uuid.UUID(sid)))
                run_id = str(run.id)

        # 6. Publish the response as token frames
        asst_msg_id = str(uuid.uuid4())
        conv_channel = f"conv:{input.conversation_id}"
        accumulated: list[str] = []

        async def _emit(token: str) -> None:
            accumulated.append(token)
            if redis_client is not None:
                frame = {"type": "token", "payload": {"message_id": asst_msg_id, "token": token}}
                await redis_client.publish(conv_channel, json.dumps(frame))

        if question is not None:
            # Follow-up questions are emitted verbatim (deterministic for analysis inputs).
            await _emit(question)
        else:
            assert validated is not None
            stream = self._llm.chat.completions.create(
                model=settings.agent_llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful RNA-seq pipeline assistant. A pipeline run has "
                            "just been queued for the user's request. Acknowledge it in one or "
                            "two sentences. Do not state any numbers, parameters or results — "
                            "the run plan is shown to the user separately."
                        ),
                    },
                    {"role": "user", "content": input.user_content},
                ],
                stream=True,
                max_tokens=150,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    await _emit(delta)
            await _emit(_format_run_plan(validated))

        if redis_client is not None:
            done_frame = {"type": "done", "payload": {"message_id": asst_msg_id, "run_id": run_id}}
            await redis_client.publish(conv_channel, json.dumps(done_frame))

        # 7. Write assistant ChatMessage AFTER done frame — atomic commit
        asst_msg = ChatMessage(
            id=uuid.UUID(asst_msg_id),
            conversation_id=uuid.UUID(input.conversation_id),
            role=MessageRole.assistant,
            content=_sanitize_chat_content("".join(accumulated)),
            run_id=uuid.UUID(run_id) if run_id else None,
        )
        db.add(asst_msg)
        db.commit()

        return ChatDispatchOutput(
            run_id=run_id,
            assistant_message_id=asst_msg_id,
            needs_clarification=question is not None,
            clarification_prompt=question,
        )


# ── Chat guards: user-decided inputs ───────────────────────────────────────────

_HISTORY_LIMIT = 20


def _mentioned(term: str, user_blob: str) -> bool:
    t = term.lower()
    return t in user_blob or t.replace("_", " ") in user_blob or t.replace("-", " ") in user_blob


def _contrasts_stated_by_user(
    raw: Any, samples: Sequence[SampleFacts], user_texts: list[str]
) -> tuple[list[DEContrast], list[InputIssue]]:
    """Keep LLM-extracted contrasts only if both conditions exist and the user named them."""
    from src.agents.run_requirements import InputIssue, condition_counts

    conditions = {c.lower(): c for c in condition_counts(samples)}
    user_blob = " ".join(user_texts).lower()
    kept: list[DEContrast] = []
    issues: list[InputIssue] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        num = str(item.get("numerator") or "").strip()
        den = str(item.get("denominator") or "").strip()
        canon_num, canon_den = conditions.get(num.lower()), conditions.get(den.lower())
        if (
            canon_num is None
            or canon_den is None
            or canon_num == canon_den
            or not _mentioned(canon_num, user_blob)
            or not _mentioned(canon_den, user_blob)
        ):
            issues.append(
                InputIssue(
                    "unknown_condition",
                    f"I couldn't match '{num or '?'} vs {den or '?'}' to the conditions "
                    "of the selected samples.",
                )
            )
            continue
        kept.append(DEContrast(numerator=canon_num, denominator=canon_den))
    return kept, issues


def _number_stated_by_user(raw: Any, user_texts: list[str]) -> int | None:
    """Accept an LLM-extracted integer only if it literally appears in the user's messages."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    pattern = re.compile(rf"(?<![\d.]){value}(?![\d.])")
    return value if any(pattern.search(t) for t in user_texts) else None


def _format_run_plan(cfg: RunConfig) -> str:
    """Deterministic summary of what will run, so the user can verify their decisions."""
    lines = ["", "", "**Run plan**", f"- Stages: {', '.join(s.value for s in cfg.stages)}"]
    for c in cfg.de_contrasts:
        lines.append(
            f"- Contrast `{c.name}`: **{c.numerator}** vs **{c.denominator}** "
            f"(fold change = {c.numerator} / {c.denominator})"
        )
    if cfg.read_length is not None:
        lines.append(f"- Read length: {cfg.read_length} bp")
    return "\n".join(lines)


# ── Chat gateway Pydantic types ────────────────────────────────────────────────


class ChatDispatchInput(BaseModel):
    conversation_id: str
    message_id: str
    user_content: str
    api_key_id: str


class ChatDispatchOutput(BaseModel):
    run_id: str | None
    assistant_message_id: str
    needs_clarification: bool
    clarification_prompt: str | None


# ── Content sanitization (safety_policy Rule 11.6) ────────────────────────────

_PATH_RE = re.compile(r"(/[a-zA-Z0-9_/.\-]+){2,}")
_AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")
_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\):.*", re.DOTALL)


def _sanitize_chat_content(text: str) -> str:
    """Strip file paths, AWS credential patterns, and tracebacks from agent content."""
    text = _PATH_RE.sub("[PATH]", text)
    text = _AWS_KEY_RE.sub("[REDACTED]", text)
    text = _TRACEBACK_RE.sub("[TRACEBACK REMOVED]", text)
    return text.strip()
