"""Result endpoints: QC, DE, GSEA, splicing, variants."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.auth import require_api_key
from src.api.schemas import (
    DEResultOut,
    DEResultsOut,
    GSEAResultOut,
    GSEAResultsOut,
    QCMetricOut,
    QCMetricsOut,
    SplicingResultOut,
    SplicingResultsOut,
    VariantListOut,
    VariantOut,
)
from src.db.models.auth import APIKey
from src.db.models.results import (
    DEGResult,
    GSEAResult,
    QCMetric,
    SplicingResult,
    VariantCall,
)
from src.db.models.run import AnalysisRun, PipelineStage
from src.db.session import get_db

router = APIRouter(tags=["results"])


def _require_run(run_id: uuid.UUID, db: Session) -> AnalysisRun:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!s} not found")
    return run


def _stage_ids(run_id: uuid.UUID, db: Session) -> list[uuid.UUID]:
    return [s.id for s in db.query(PipelineStage).filter(PipelineStage.run_id == run_id).all()]


@router.get("/runs/{run_id}/qc", response_model=QCMetricsOut)
def get_qc(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> QCMetricsOut:
    _require_run(run_id, db)
    sids = _stage_ids(run_id, db)
    if not sids:
        return QCMetricsOut(items=[], total=0)
    items = db.query(QCMetric).filter(QCMetric.stage_id.in_(sids)).all()
    return QCMetricsOut(items=[QCMetricOut.model_validate(m) for m in items], total=len(items))


@router.get("/runs/{run_id}/de", response_model=DEResultsOut)
def get_de(
    run_id: uuid.UUID,
    contrast: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> DEResultsOut:
    _require_run(run_id, db)
    q = db.query(DEGResult).filter(DEGResult.run_id == run_id)
    if contrast:
        q = q.filter(DEGResult.contrast == contrast)
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    return DEResultsOut(
        items=[DEResultOut.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}/gsea", response_model=GSEAResultsOut)
def get_gsea(
    run_id: uuid.UUID,
    contrast: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> GSEAResultsOut:
    _require_run(run_id, db)
    q = db.query(GSEAResult).filter(GSEAResult.run_id == run_id)
    if contrast:
        q = q.filter(GSEAResult.contrast == contrast)
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    return GSEAResultsOut(
        items=[GSEAResultOut.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}/splicing", response_model=SplicingResultsOut)
def get_splicing(
    run_id: uuid.UUID,
    contrast: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> SplicingResultsOut:
    _require_run(run_id, db)
    q = db.query(SplicingResult).filter(SplicingResult.run_id == run_id)
    if contrast:
        q = q.filter(SplicingResult.contrast == contrast)
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    return SplicingResultsOut(
        items=[SplicingResultOut.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}/variants", response_model=VariantListOut)
def get_variants(
    run_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> VariantListOut:
    _require_run(run_id, db)
    sids = _stage_ids(run_id, db)
    if not sids:
        return VariantListOut(items=[], total=0, limit=limit, offset=offset)
    q = db.query(VariantCall).filter(VariantCall.stage_id.in_(sids))
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    return VariantListOut(
        items=[VariantOut.model_validate(v) for v in items],
        total=total,
        limit=limit,
        offset=offset,
    )
