"""Analysis run endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.api.auth import require_api_key
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
from src.db.models.project import RunSample
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
    _: APIKey = Depends(require_api_key),
) -> RunListOut:
    items = db.query(AnalysisRun).all()
    return RunListOut(items=[RunOut.model_validate(r) for r in items], total=len(items))


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> RunDetailOut:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!s} not found")
    stages = [StageOut.model_validate(s) for s in run.stages]
    return RunDetailOut(**RunOut.model_validate(run).model_dump(), stages=stages)


@router.post("/{run_id}/cancel", response_model=CancelRunOut)
def cancel_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> CancelRunOut:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!s} not found")
    if run.status not in (RunStatus.pending, RunStatus.running):
        raise HTTPException(
            status_code=409, detail=f"Cannot cancel run in status {run.status}"
        )
    run.status = RunStatus.cancelled
    db.commit()
    return CancelRunOut(run_id=run.id, status=RunStatus.cancelled)
