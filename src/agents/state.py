from __future__ import annotations

from typing import TypedDict


class StageState(TypedDict):
    """Per-stage execution record returned by each BaseStageAgent."""

    stage_name: str
    status: str
    output: dict | None
    error: str | None


class RunState(TypedDict):
    """Full LangGraph pipeline state persisted to AnalysisRun.agent_state."""

    run_id: str
    run_config: dict
    stages: list[str]            # ordered planned stages
    completed_stages: list[str]
    failed_stage: str | None
    stage_outputs: dict[str, dict]
    error_message: str | None
    current_stage: str | None
