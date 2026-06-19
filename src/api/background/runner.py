"""ARQ worker task: dequeues run_id and invokes OrchestratorAgent."""

from __future__ import annotations

from src.db.enums import RunStatus


async def run_pipeline(ctx: dict, run_id: str) -> None:
    """Execute the pipeline for the given run_id. Invoked by the ARQ worker."""
    from src.db.models.run import AnalysisRun

    db = ctx["db"]
    run: AnalysisRun | None = db.get(AnalysisRun, run_id)
    if run is None:
        return

    run.status = RunStatus.running
    db.commit()

    try:
        # TASK-09 OrchestratorAgent.dispatch() invocation happens here.
        # Stub: actual agent wiring is added when TASK-09/11 are integrated.
        pass
    except Exception as exc:
        run.status = RunStatus.failed
        run.error_message = str(exc)
        db.commit()
        raise


async def startup(ctx: dict) -> None:
    """Create a DB session on worker start."""
    from src.db.session import get_session_factory

    ctx["db"] = get_session_factory()()


async def shutdown(ctx: dict) -> None:
    """Close the DB session on worker shutdown."""
    ctx["db"].close()


class WorkerSettings:
    functions = [run_pipeline]
    on_startup = startup
    on_shutdown = shutdown

    @classmethod
    def get_redis_settings(cls):  # type: ignore[no-untyped-def]
        from arq.connections import RedisSettings

        from src.config import get_settings

        return RedisSettings.from_dsn(get_settings().redis_url)
