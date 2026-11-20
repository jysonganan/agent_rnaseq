"""ARQ worker task: dequeues run_id and executes the pipeline via OrchestratorAgent."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from src.db.enums import RunStatus

logger = logging.getLogger(__name__)


def execute_run_sync(db: Session, run_id: str, **execute_kwargs: Any) -> RunStatus:
    """Run the pipeline for ``run_id`` to completion and persist its terminal status.

    Blocking (tools are subprocesses); call from a worker thread.
    """
    from src.agents.orchestrator import OrchestratorAgent
    from src.db.models.run import AnalysisRun

    run = db.get(AnalysisRun, uuid.UUID(run_id))
    if run is None:
        logger.warning("run_pipeline: run %s not found", run_id)
        return RunStatus.failed
    if run.status not in (RunStatus.pending, RunStatus.failed):
        logger.info("run_pipeline: run %s is %s, skipping", run_id, run.status)
        return run.status

    run.status = RunStatus.running
    run.error_message = None
    run.started_at = run.started_at or datetime.now(UTC)
    db.commit()

    try:
        dry_run = bool((run.run_config or {}).get("dry_run", False))
        # Execution is deterministic: no LLM client is needed to run stages.
        agent = OrchestratorAgent(llm_client=None, dry_run=dry_run)
        final = agent.execute_run(db, run_id, **execute_kwargs)
    except Exception as exc:
        logger.exception("run_pipeline: run %s crashed", run_id)
        db.rollback()
        run = db.get(AnalysisRun, uuid.UUID(run_id))
        if run is not None:
            run.status = RunStatus.failed
            run.error_message = f"{type(exc).__name__}: {exc}"[:1000]
            run.completed_at = datetime.now(UTC)
            db.commit()
        return RunStatus.failed

    db.refresh(run)
    if run.status == RunStatus.cancelled:
        pass  # keep the user's cancellation
    elif final.get("failed_stage"):
        run.status = RunStatus.failed
        run.error_message = final.get("error_message")
    else:
        run.status = RunStatus.completed
    run.completed_at = datetime.now(UTC)
    run.agent_state = final
    db.commit()
    return run.status


async def run_pipeline(ctx: dict, run_id: str) -> None:
    """Execute the pipeline for the given run_id. Invoked by the ARQ worker."""
    from src.db.session import get_session_factory

    def _job() -> None:
        db = get_session_factory()()
        try:
            execute_run_sync(db, run_id)
        finally:
            db.close()

    await asyncio.to_thread(_job)


async def startup(ctx: dict) -> None:
    """Kept for backwards compatibility; each job now opens its own session."""


async def shutdown(ctx: dict) -> None:
    """Kept for backwards compatibility."""


class WorkerSettings:
    functions = [run_pipeline]
    on_startup = startup
    on_shutdown = shutdown

    @classmethod
    def get_redis_settings(cls):  # type: ignore[no-untyped-def]
        from arq.connections import RedisSettings

        from src.config import get_settings

        return RedisSettings.from_dsn(get_settings().redis_url)
