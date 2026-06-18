from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

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
    "visualization": [],   # special: at least one of qc/de/gsea — checked separately
    "report": [],          # special: at least one upstream — checked separately
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
