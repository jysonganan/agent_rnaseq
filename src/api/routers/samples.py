"""Sample endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.auth import require_api_key
from src.api.schemas import CreateSampleIn, SampleListOut, SampleOut
from src.db.models.auth import APIKey
from src.db.models.project import Project, Sample
from src.db.session import get_db

router = APIRouter(tags=["samples"])


@router.get("/projects/{project_id}/samples", response_model=SampleListOut)
def list_samples(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> SampleListOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!s} not found")
    items = db.query(Sample).filter(Sample.project_id == project_id).all()
    return SampleListOut(items=[SampleOut.model_validate(s) for s in items], total=len(items))


@router.post("/projects/{project_id}/samples", response_model=SampleOut, status_code=201)
def create_sample(
    project_id: uuid.UUID,
    body: CreateSampleIn,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> SampleOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!s} not found")
    sample = Sample(project_id=project_id, **body.model_dump())
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return SampleOut.model_validate(sample)


@router.get("/samples/{sample_id}", response_model=SampleOut)
def get_sample(
    sample_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> SampleOut:
    sample = db.get(Sample, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id!s} not found")
    return SampleOut.model_validate(sample)
