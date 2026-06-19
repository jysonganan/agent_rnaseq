"""Artifact endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.auth import require_api_key
from src.api.schemas import ArtifactListOut, ArtifactOut, DownloadUrlOut
from src.db.models.auth import APIKey
from src.db.models.run import Artifact, AnalysisRun
from src.db.session import get_db

router = APIRouter(tags=["artifacts"])


@router.get("/runs/{run_id}/artifacts", response_model=ArtifactListOut)
def list_artifacts(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> ArtifactListOut:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!s} not found")
    items = db.query(Artifact).filter(Artifact.run_id == run_id).all()
    return ArtifactListOut(
        items=[ArtifactOut.model_validate(a) for a in items], total=len(items)
    )


@router.get(
    "/runs/{run_id}/artifacts/{artifact_id}/download", response_model=DownloadUrlOut
)
def download_artifact(
    run_id: uuid.UUID,
    artifact_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> DownloadUrlOut:
    artifact = db.get(Artifact, artifact_id)
    if artifact is None or artifact.run_id != run_id:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id!s} not found")
    return DownloadUrlOut(artifact_id=artifact.id, url=f"file://{artifact.path}")
