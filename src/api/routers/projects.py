"""Project endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.auth import require_api_key
from src.api.schemas import CreateProjectIn, ProjectListOut, ProjectOut
from src.db.models.auth import APIKey
from src.db.models.project import Project
from src.db.session import get_db

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListOut)
def list_projects(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> ProjectListOut:
    total = db.query(Project).count()
    items = db.query(Project).offset(offset).limit(limit).all()
    return ProjectListOut(
        items=[ProjectOut.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: CreateProjectIn,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> ProjectOut:
    project = Project(**body.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: APIKey = Depends(require_api_key),
) -> ProjectOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!s} not found")
    return ProjectOut.model_validate(project)
