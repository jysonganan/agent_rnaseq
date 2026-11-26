"""Shared fixtures for API tests."""

from __future__ import annotations

import contextlib
import hashlib
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from src.api.app import create_app
from src.db.base import Base
from src.db.enums import SampleType
from src.db.models.auth import APIKey
from src.db.models.genome import ReferenceGenome
from src.db.models.project import Project, Sample
from src.db.session import get_db

TEST_API_KEY_RAW = "test-integration-api-key-abc123def456"
TEST_API_KEY_HASH = hashlib.sha256(TEST_API_KEY_RAW.encode()).hexdigest()
TEST_BOOTSTRAP_KEY = os.environ["API_KEY_BOOTSTRAP"]


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture
def seed_data(db_engine) -> dict:
    """Commit baseline API key, genome, project, and sample. Returns IDs."""
    with Session(db_engine) as session:
        api_key = APIKey(
            key_hash=TEST_API_KEY_HASH,
            name="test-key",
            created_by="test-admin",
            principal="test-user",
        )
        genome = ReferenceGenome(
            name="hg38",
            species="Homo sapiens",
            build="GRCh38",
            fasta_path="/ref/hg38.fa",
            gtf_path="/ref/hg38.gtf",
        )
        project = Project(name="Test Project", owner="test-user")
        session.add_all([api_key, genome, project])
        session.flush()

        sample = Sample(
            project_id=project.id,
            name="sample_1",
            sample_type=SampleType.bulk_rnaseq,
            fastq_r1_path="/data/s1.fastq.gz",
            is_paired_end=False,
        )
        session.add(sample)
        session.commit()

        return {
            "api_key_id": api_key.id,
            "genome_id": genome.id,
            "project_id": project.id,
            "sample_id": sample.id,
        }


@pytest.fixture
def client(db_engine) -> TestClient:  # type: ignore[misc]
    app = create_app()
    _sf = sessionmaker(bind=db_engine)

    def _get_db():
        with _sf() as s:
            try:
                yield s
            except Exception:
                s.rollback()
                raise

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:  # type: ignore[misc]
    from src.api.rate_limit import limiter

    with contextlib.suppress(Exception):
        limiter._storage.reset()
    yield  # type: ignore[misc]


@pytest.fixture(autouse=True)
def mock_arq() -> None:  # type: ignore[misc]
    with patch("src.api.routers.runs._enqueue_run", new_callable=AsyncMock):
        yield


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_API_KEY_RAW}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """The bootstrap admin key (API_KEY_BOOTSTRAP, set in tests/conftest.py)."""
    return {"Authorization": f"Bearer {TEST_BOOTSTRAP_KEY}"}


@pytest.fixture
def run_payload(seed_data: dict) -> dict:
    """Minimal valid POST /runs request body."""
    return {
        "project_id": str(seed_data["project_id"]),
        "genome_id": str(seed_data["genome_id"]),
        "name": "test-run",
        "pipeline_type": "bulk_rnaseq",
        "sample_ids": [str(seed_data["sample_id"])],
        "alignment_mode": "genome",
        "aligner": "star",
        "stages": ["qc"],
    }


def ws_close_code(client: TestClient, url: str, first_frame: object) -> int:
    """Connect, send *first_frame* (JSON, or raw text if a str), return the server's close code.

    For sockets that pass the handshake this would block on Redis-less streams, so use it only
    where the server is expected to close after the auth frame.
    """
    with client.websocket_connect(url) as ws:
        if isinstance(first_frame, str):
            ws.send_text(first_frame)
        else:
            ws.send_json(first_frame)
        with pytest.raises(WebSocketDisconnect) as exc:
            while True:
                ws.receive_text()
    return exc.value.code


def auth_frame(api_key: str) -> dict[str, str]:
    return {"type": "auth", "api_key": api_key}
