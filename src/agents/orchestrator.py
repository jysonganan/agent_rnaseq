from __future__ import annotations

import json
import re
import uuid
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.router import build_pipeline_graph
from src.agents.state import RunState
from src.config import get_settings
from src.db.enums import Executor, PipelineType, StageName

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
    executor: Executor = Executor.local
    dry_run: bool = False  # must be set in API request body, never by LLM


class OrchestratorError(Exception):
    """User-facing error from OrchestratorAgent (dependency, genome, ambiguity)."""


class OrchestratorAgent:
    """Parses user intent, validates RunConfig, and dispatches to LangGraph."""

    def __init__(
        self,
        llm_client: OpenAI,
        *,
        dry_run: bool = False,
    ) -> None:
        self._client = llm_client
        self._dry_run = dry_run
        self._graph = build_pipeline_graph()

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
        response = self._client.chat.completions.create(
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

    # ── Chat gateway ───────────────────────────────────────────────────────────

    def _build_dispatch_system_prompt(
        self,
        sample_list: list[dict],
        genome_list: list[dict],
    ) -> str:
        samples_json = json.dumps(sample_list, indent=2)
        genomes_json = json.dumps(genome_list, indent=2)
        return (
            "You are an RNA-seq pipeline assistant. Given a user's request, determine "
            "whether it contains enough information to launch a pipeline run.\n\n"
            "Available samples (select sample_ids from this list only — never invent UUIDs):\n"
            f"{samples_json}\n\n"
            "Available genomes (select genome_id from this list only — never invent UUIDs):\n"
            f"{genomes_json}\n\n"
            "Return ONLY valid JSON. If the request is actionable, return:\n"
            '{"type": "run", "run_name": "...", "genome_id": "<exact UUID from list>", '
            '"sample_ids": ["<exact UUID from list>", ...], '
            '"pipeline_type": "bulk_rnaseq|scrna_seq", '
            '"stages": ["qc", "alignment", ...], '
            '"alpha": 0.05, "lfc_threshold": 0.0}\n\n'
            "If the request is ambiguous or missing required information, return:\n"
            '{"type": "clarification", "question": "..."}'
        )

    async def dispatch_from_chat(
        self,
        input: "ChatDispatchInput",
        db: Session,
        redis_client: Any | None = None,
    ) -> "ChatDispatchOutput":
        """
        Process a chat message: parse intent, validate resources, optionally create
        AnalysisRun, publish token frames to Redis, write assistant ChatMessage to DB.
        """
        from src.db.enums import (
            Aligner,
            AlignmentMode,
            MessageRole,
            RunStatus,
        )
        from src.db.models.conversation import ChatMessage
        from src.db.models.genome import ReferenceGenome
        from src.db.models.project import Sample
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
        genome_list = [
            {"id": str(g.id), "name": g.name, "build": g.build}
            for g in genomes
        ]

        # 2. Parse intent (non-streaming, JSON mode)
        system_prompt = self._build_dispatch_system_prompt(sample_list, genome_list)
        intent_resp = self._client.chat.completions.create(
            model=settings.agent_llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input.user_content},
            ],
            response_format={"type": "json_object"},
        )
        intent = json.loads(intent_resp.choices[0].message.content or "{}")

        needs_clarification = intent.get("type", "clarification") != "run"
        run_id: str | None = None

        if not needs_clarification:
            # 3. Re-validate selected IDs against DB
            selected_genome_id = intent.get("genome_id", "")
            selected_sample_ids: list[str] = intent.get("sample_ids", [])

            known_genome_ids = {str(g.id) for g in genomes}
            if selected_genome_id not in known_genome_ids:
                raise ToolValidationError(
                    f"Genome ID '{selected_genome_id}' is not registered in the database"
                )

            known_sample_ids = {str(s.id) for s in samples}
            for sid in selected_sample_ids:
                if sid not in known_sample_ids:
                    raise ToolValidationError(
                        f"Sample ID '{sid}' is not in the database"
                    )

            # Derive project_id from the first selected sample
            sample_obj = next(s for s in samples if str(s.id) == selected_sample_ids[0])

            # 4. Create AnalysisRun (with Pydantic-validated params — no raw LLM numerics)
            try:
                validated = RunConfig(
                    run_name=intent.get("run_name", "Chat run"),
                    genome_id=selected_genome_id,
                    pipeline_type=PipelineType(
                        intent.get("pipeline_type", "bulk_rnaseq")
                    ),
                    stages=[StageName(s) for s in intent.get("stages", ["qc"])],
                    alpha=float(intent.get("alpha", 0.05)),
                    lfc_threshold=float(intent.get("lfc_threshold", 0.0)),
                    executor=Executor.local,
                    dry_run=False,
                )
            except Exception as exc:
                raise ToolValidationError(f"Invalid run configuration: {exc}") from exc

            run = AnalysisRun(
                project_id=sample_obj.project_id,
                genome_id=uuid.UUID(selected_genome_id),
                created_by=uuid.UUID(input.api_key_id),
                name=validated.run_name,
                status=RunStatus.pending,
                pipeline_type=validated.pipeline_type,
                alignment_mode=AlignmentMode.genome,
                aligner=Aligner.star,
                run_config=validated.model_dump(mode="json"),
                conversation_id=uuid.UUID(input.conversation_id),
                triggering_message_id=uuid.UUID(input.message_id),
            )
            db.add(run)
            db.flush()
            run_id = str(run.id)

        # 5. Stream response tokens and publish to Redis
        clarification_text: str | None = intent.get("question") if needs_clarification else None
        asst_msg_id = str(uuid.uuid4())
        conv_channel = f"conv:{input.conversation_id}"
        accumulated: list[str] = []

        stream = self._client.chat.completions.create(
            model=settings.agent_llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful RNA-seq pipeline assistant. Respond concisely.",
                },
                {"role": "user", "content": input.user_content},
            ],
            stream=True,
            max_tokens=300,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                accumulated.append(delta)
                if redis_client is not None:
                    frame = json.dumps(
                        {
                            "type": "token",
                            "payload": {"message_id": asst_msg_id, "token": delta},
                        }
                    )
                    await redis_client.publish(conv_channel, frame)

        # Publish done frame
        if redis_client is not None:
            done_frame = json.dumps(
                {
                    "type": "done",
                    "payload": {"message_id": asst_msg_id, "run_id": run_id},
                }
            )
            await redis_client.publish(conv_channel, done_frame)

        # 6. Write assistant ChatMessage AFTER done frame — atomic commit
        full_text = "".join(accumulated) or clarification_text or ""
        asst_msg = ChatMessage(
            id=uuid.UUID(asst_msg_id),
            conversation_id=uuid.UUID(input.conversation_id),
            role=MessageRole.assistant,
            content=_sanitize_chat_content(full_text),
            run_id=uuid.UUID(run_id) if run_id else None,
        )
        db.add(asst_msg)
        db.commit()

        return ChatDispatchOutput(
            run_id=run_id,
            assistant_message_id=asst_msg_id,
            needs_clarification=needs_clarification,
            clarification_prompt=clarification_text,
        )


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
