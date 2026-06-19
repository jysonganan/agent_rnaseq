"""Shared fixtures for all integration tests."""

from __future__ import annotations

import gzip
import hashlib
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401 — registers all ORM models with SQLAlchemy
from src.db.base import Base
from src.db.enums import SampleType
from src.db.models.auth import APIKey
from src.db.models.genome import ReferenceGenome
from src.db.models.project import Project, Sample
from src.db.session import get_db

FIXTURES_DIR = Path(__file__).parent / "fixtures"

RUN_ID = str(uuid.uuid4())
SAMPLE_ID = str(uuid.uuid4())

TEST_API_KEY_RAW = "integration-test-key-xyzabc12345678"
TEST_API_KEY_HASH = hashlib.sha256(TEST_API_KEY_RAW.encode()).hexdigest()
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_KEY_RAW}"}


@pytest.fixture(scope="session", autouse=True)
def _create_synthetic_fastq():
    """Write synthetic paired-end FASTQ fixture files once per test session."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    r1 = FIXTURES_DIR / "synthetic_R1.fastq.gz"
    r2 = FIXTURES_DIR / "synthetic_R2.fastq.gz"
    if not r1.exists():
        with gzip.open(r1, "wt") as fh:
            for i in range(10):
                fh.write(f"@READ_{i:03d}/1\nACGTACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIIIIIII\n")
    if not r2.exists():
        with gzip.open(r2, "wt") as fh:
            for i in range(10):
                fh.write(f"@READ_{i:03d}/2\nTGCATGCATGCATGCATGCA\n+\nIIIIIIIIIIIIIIIIIIII\n")


# ── Agent / DB fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def db() -> Session:
    """Isolated in-memory SQLite session for agent integration tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()


# ── API test fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def api_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture
def api_seed(api_engine) -> dict:
    """Seed API engine with an APIKey, ReferenceGenome, Project, and Sample."""
    with Session(api_engine) as session:
        api_key = APIKey(
            key_hash=TEST_API_KEY_HASH,
            name="int-test-key",
            created_by="test-admin",
        )
        genome = ReferenceGenome(
            name="GRCh38_int_test",
            species="Homo sapiens",
            build="GRCh38",
            fasta_path="/ref/hg38.fa",
            gtf_path="/ref/hg38.gtf",
        )
        project = Project(name="Integration Test Project", owner="test-user")
        session.add_all([api_key, genome, project])
        session.flush()
        sample = Sample(
            project_id=project.id,
            name="int_sample_001",
            sample_type=SampleType.bulk_rnaseq,
            fastq_r1_path="/data/int_001_R1.fastq.gz",
            is_paired_end=True,
        )
        session.add(sample)
        session.commit()
        session.refresh(api_key)
        session.refresh(genome)
        session.refresh(project)
        session.refresh(sample)
        return {
            "api_key_id": str(api_key.id),
            "genome_id": str(genome.id),
            "project_id": str(project.id),
            "sample_id": str(sample.id),
        }


@pytest.fixture
def api_client(api_engine, api_seed):
    """TestClient wired to the seeded in-memory engine with ARQ enqueue patched."""
    from src.api.app import create_app

    app = create_app()
    _sf = sessionmaker(bind=api_engine)

    def _override_db():
        with _sf() as s:
            try:
                yield s
            except Exception:
                s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db

    from fastapi.testclient import TestClient

    with patch("src.api.routers.runs._enqueue_run", new_callable=AsyncMock):
        with TestClient(app, raise_server_exceptions=True) as client:
            client._seed = api_seed  # type: ignore[attr-defined]
            yield client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from src.api.rate_limit import limiter

    try:
        limiter._storage.reset()
    except Exception:
        pass
    yield
