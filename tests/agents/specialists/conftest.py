"""Shared fixtures for specialist agent tests.

Uses in-memory SQLite without FK enforcement so tests can insert
PipelineStage / result rows without creating parent AnalysisRun records.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import src.db.models  # registers all models with Base.metadata  # noqa: F401
from src.db.base import Base

RUN_ID = str(uuid.uuid4())
SAMPLE_ID = str(uuid.uuid4())


@pytest.fixture
def db() -> Session:
    """In-memory SQLite session with all tables created (FK checks disabled)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()
