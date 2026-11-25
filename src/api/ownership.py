"""Per-principal data ownership (api_contracts.md "Principals and ownership", safety Rule 12).

Ownership is enforced in the queries themselves. A resource owned by another principal is
reported exactly like a missing one (404), so IDs of other principals' data are not revealed.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Query, Session

from src.db.models.auth import APIKey
from src.db.models.conversation import Conversation
from src.db.models.project import Project, Sample
from src.db.models.run import AnalysisRun


def principal_key_ids(principal: str):  # noqa: ANN201 — SQLAlchemy Select
    """Subquery: ids of every key (active or not) of *principal*."""
    return select(APIKey.id).where(APIKey.principal == principal)


def projects_query(db: Session, key: APIKey) -> Query:
    return db.query(Project).filter(Project.owner == key.principal)


def runs_query(db: Session, key: APIKey) -> Query:
    return (
        db.query(AnalysisRun)
        .join(Project, AnalysisRun.project_id == Project.id)
        .filter(Project.owner == key.principal)
    )


def samples_query(db: Session, key: APIKey) -> Query:
    return (
        db.query(Sample)
        .join(Project, Sample.project_id == Project.id)
        .filter(Project.owner == key.principal)
    )


def conversations_query(db: Session, key: APIKey) -> Query:
    return db.query(Conversation).filter(
        Conversation.created_by.in_(principal_key_ids(key.principal))
    )


def owned_project(db: Session, key: APIKey, project_id: uuid.UUID) -> Project:
    project = projects_query(db, key).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!s} not found")
    return project


def owned_run(db: Session, key: APIKey, run_id: uuid.UUID) -> AnalysisRun:
    run = runs_query(db, key).filter(AnalysisRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!s} not found")
    return run


def owned_sample(db: Session, key: APIKey, sample_id: uuid.UUID) -> Sample:
    sample = samples_query(db, key).filter(Sample.id == sample_id).first()
    if sample is None:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id!s} not found")
    return sample
