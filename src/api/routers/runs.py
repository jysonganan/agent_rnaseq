"""Analysis run endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.agents.run_requirements import check_analysis_inputs, format_issues, sample_facts
from src.api.auth import require_api_key
from src.api.ownership import owned_project, owned_run, runs_query
from src.api.rate_limit import limiter
from src.api.schemas import (
    CancelRunOut,
    CreateRunIn,
    RunCreatedOut,
    RunDetailOut,
    RunListOut,
    RunOut,
    StageOut,
)
from src.db.enums import RunStatus
from src.db.models.auth import APIKey
from src.db.models.project import RunSample, Sample
from src.db.models.run import AnalysisRun
from src.db.session import get_db

router = APIRouter(prefix="/runs", tags=["runs"])


async def _enqueue_run(run_id: str) -> None:
    """Enqueue pipeline run via ARQ. Patched in unit tests."""
    from arq.connections import RedisSettings, create_pool

    from src.config import get_settings

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await pool.enqueue_job("run_pipeline", run_id=run_id)
    await pool.aclose()


@router.post("", status_code=202, response_model=RunCreatedOut)
@limiter.limit("10/minute")
async def create_run(
    request: Request,
    body: CreateRunIn,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> RunCreatedOut:
    owned_project(db, api_key, body.project_id)
    # Only samples of the (owned) run project count — others are reported as unknown.
    samples = (
        db.query(Sample)
        .filter(Sample.id.in_(body.sample_ids), Sample.project_id == body.project_id)
        .all()
    )
    missing = {str(i) for i in body.sample_ids} - {str(s.id) for s in samples}
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown sample_ids: {sorted(missing)}")
    issues = check_analysis_inputs(
        [s.value for s in body.stages], sample_facts(samples), body.de_contrasts, body.read_length
    )
    if issues:
        raise HTTPException(status_code=422, detail=format_issues(issues))

    run = AnalysisRun(
        project_id=body.project_id,
        genome_id=body.genome_id,
        created_by=api_key.id,
        name=body.name,
        status=RunStatus.pending,
        pipeline_type=body.pipeline_type,
        alignment_mode=body.alignment_mode,
        aligner=body.aligner,
        run_config=body.model_dump(mode="json"),
    )
    db.add(run)
    db.flush()

    for sid in body.sample_ids:
        db.add(RunSample(run_id=run.id, sample_id=sid))

    db.commit()
    db.refresh(run)

    await _enqueue_run(str(run.id))

    return RunCreatedOut(
        run_id=run.id,
        status=RunStatus.pending,
        message="Pipeline run queued",
    )


@router.get("", response_model=RunListOut)
def list_runs(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> RunListOut:
    items = runs_query(db, api_key).order_by(AnalysisRun.created_at).all()
    return RunListOut(items=[RunOut.model_validate(r) for r in items], total=len(items))


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> RunDetailOut:
    run = owned_run(db, api_key, run_id)
    stages = [StageOut.model_validate(s) for s in run.stages]
    return RunDetailOut(**RunOut.model_validate(run).model_dump(), stages=stages)


@router.post("/{run_id}/cancel", response_model=CancelRunOut)
def cancel_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> CancelRunOut:
    run = owned_run(db, api_key, run_id)
    if run.status not in (RunStatus.pending, RunStatus.running):
        raise HTTPException(status_code=409, detail=f"Cannot cancel run in status {run.status}")
    run.status = RunStatus.cancelled
    db.commit()
    return CancelRunOut(run_id=run.id, status=RunStatus.cancelled)


@router.post("/{run_id}/retry", status_code=202, response_model=RunCreatedOut)
@limiter.limit("10/minute")
async def retry_run(
    request: Request,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(require_api_key),
) -> RunCreatedOut:
    run = owned_run(db, api_key, run_id)
    if run.status not in (RunStatus.failed, RunStatus.cancelled):
        raise HTTPException(status_code=409, detail=f"Cannot retry run in status {run.status}")
    run.status = RunStatus.pending
    run.error_message = None
    run.completed_at = None
    db.commit()

    await _enqueue_run(str(run.id))

    done = list((run.agent_state or {}).get("completed_stages") or [])
    message = "Run re-queued; " + (
        f"resuming after: {', '.join(done)}" if done else "starting from the first stage"
    )
    return RunCreatedOut(run_id=run.id, status=RunStatus.pending, message=message)
