"""Per-principal data isolation (api_contracts.md "Principals and ownership", safety Rule 12).

``test-user`` (the seeded key, ``auth_headers``) must not see or act on anything owned by
``team_b``; another key of the same principal must see everything (key rotation).
"""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from starlette.websockets import WebSocketDisconnect

from src.db.enums import (
    Aligner,
    AlignmentMode,
    ArtifactType,
    PipelineType,
    RunStatus,
    SampleType,
    StageName,
    StageStatus,
)
from src.db.models.auth import APIKey
from src.db.models.conversation import Conversation
from src.db.models.project import Project, Sample
from src.db.models.run import AnalysisRun, Artifact, PipelineStage

TEAM_B_RAW = "team-b-raw-key-0123456789"
SECOND_TEST_USER_RAW = "test-user-second-key-0123456789"


def _key(session: Session, raw: str, principal: str) -> APIKey:
    key = APIKey(
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        name=raw[:20],
        created_by="test-admin",
        principal=principal,
    )
    session.add(key)
    session.flush()
    return key


@pytest.fixture
def other(db_engine, seed_data: dict) -> dict:
    """team_b's key, project, sample, run, artifact and conversation."""
    with Session(db_engine) as s:
        key = _key(s, TEAM_B_RAW, "team_b")
        _key(s, SECOND_TEST_USER_RAW, "test-user")
        project = Project(name="B project", owner="team_b")
        s.add(project)
        s.flush()
        sample = Sample(
            project_id=project.id,
            name="b_1",
            sample_type=SampleType.bulk_rnaseq,
            fastq_r1_path="/data/b1.fastq.gz",
            is_paired_end=False,
        )
        run = AnalysisRun(
            project_id=project.id,
            genome_id=seed_data["genome_id"],
            created_by=key.id,
            name="b-run",
            status=RunStatus.failed,
            pipeline_type=PipelineType.bulk_rnaseq,
            alignment_mode=AlignmentMode.genome,
            aligner=Aligner.star,
            run_config={},
        )
        s.add_all([sample, run])
        s.flush()
        stage = PipelineStage(
            run_id=run.id,
            stage_name=StageName.report,
            status=StageStatus.completed,
            tool_name="compile_report",
        )
        s.add(stage)
        s.flush()
        artifact = Artifact(
            stage_id=stage.id,
            run_id=run.id,
            artifact_type=ArtifactType.html_report,
            path="/out/b/report.html",
        )
        conv = Conversation(title="B chat", created_by=key.id)
        s.add_all([artifact, conv])
        s.commit()
        return {
            "project_id": str(project.id),
            "sample_id": str(sample.id),
            "run_id": str(run.id),
            "artifact_id": str(artifact.id),
            "conversation_id": str(conv.id),
        }


B = {"Authorization": f"Bearer {TEAM_B_RAW}"}


class TestProjectsAndSamples:
    def test_lists_only_own_projects(self, client: TestClient, other: dict, auth_headers):
        ids = {
            p["id"] for p in client.get("/api/v1/projects", headers=auth_headers).json()["items"]
        }
        assert other["project_id"] not in ids
        b_ids = {p["id"] for p in client.get("/api/v1/projects", headers=B).json()["items"]}
        assert b_ids == {other["project_id"]}

    def test_total_counts_only_own(self, client: TestClient, other: dict, auth_headers):
        assert client.get("/api/v1/projects", headers=auth_headers).json()["total"] == 1

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/projects/{project_id}",
            "/api/v1/projects/{project_id}/samples",
            "/api/v1/samples/{sample_id}",
        ],
    )
    def test_foreign_resources_are_404(
        self, client: TestClient, other: dict, auth_headers, path: str
    ) -> None:
        r = client.get(path.format(**other), headers=auth_headers)
        assert r.status_code == 404
        assert client.get(path.format(**other), headers=B).status_code == 200

    def test_cannot_add_sample_to_foreign_project(
        self, client: TestClient, other: dict, auth_headers
    ) -> None:
        r = client.post(
            f"/api/v1/projects/{other['project_id']}/samples",
            json={"name": "x", "sample_type": "bulk_rnaseq", "fastq_r1_path": "/d/x.fq.gz"},
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_owner_set_from_principal(self, client: TestClient, seed_data: dict, auth_headers):
        r = client.post("/api/v1/projects", json={"name": "mine"}, headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["owner"] == "test-user"

    def test_matching_owner_still_accepted(
        self, client: TestClient, seed_data: dict, auth_headers
    ) -> None:
        r = client.post(
            "/api/v1/projects", json={"name": "m", "owner": "test-user"}, headers=auth_headers
        )
        assert r.status_code == 201

    def test_foreign_owner_rejected(self, client: TestClient, seed_data: dict, auth_headers):
        r = client.post(
            "/api/v1/projects", json={"name": "m", "owner": "team_b"}, headers=auth_headers
        )
        assert r.status_code == 403


class TestRuns:
    def test_list_runs_only_own(self, client: TestClient, other: dict, auth_headers):
        ids = {r["id"] for r in client.get("/api/v1/runs", headers=auth_headers).json()["items"]}
        assert other["run_id"] not in ids
        b_ids = {r["id"] for r in client.get("/api/v1/runs", headers=B).json()["items"]}
        assert b_ids == {other["run_id"]}

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/runs/{run_id}",
            "/api/v1/runs/{run_id}/qc",
            "/api/v1/runs/{run_id}/de",
            "/api/v1/runs/{run_id}/gsea",
            "/api/v1/runs/{run_id}/splicing",
            "/api/v1/runs/{run_id}/variants",
            "/api/v1/runs/{run_id}/artifacts",
            "/api/v1/runs/{run_id}/artifacts/{artifact_id}/download",
        ],
    )
    def test_foreign_run_reads_are_404(
        self, client: TestClient, other: dict, auth_headers, path: str
    ) -> None:
        assert client.get(path.format(**other), headers=auth_headers).status_code == 404
        assert client.get(path.format(**other), headers=B).status_code == 200

    def test_cannot_cancel_foreign_run(self, client: TestClient, other: dict, auth_headers):
        r = client.post(f"/api/v1/runs/{other['run_id']}/cancel", headers=auth_headers)
        assert r.status_code == 404

    def test_cannot_retry_foreign_run(self, client: TestClient, other: dict, auth_headers):
        r = client.post(f"/api/v1/runs/{other['run_id']}/retry", headers=auth_headers)
        assert r.status_code == 404
        assert client.post(f"/api/v1/runs/{other['run_id']}/retry", headers=B).status_code == 202

    def test_create_run_in_foreign_project_is_404(
        self, client: TestClient, other: dict, auth_headers, run_payload: dict
    ) -> None:
        payload = {**run_payload, "project_id": other["project_id"]}
        assert client.post("/api/v1/runs", json=payload, headers=auth_headers).status_code == 404

    def test_create_run_with_foreign_sample_is_422(
        self, client: TestClient, other: dict, auth_headers, run_payload: dict
    ) -> None:
        payload = {**run_payload, "sample_ids": [*run_payload["sample_ids"], other["sample_id"]]}
        r = client.post("/api/v1/runs", json=payload, headers=auth_headers)
        assert r.status_code == 422
        assert other["sample_id"] in r.json()["detail"]

    def test_other_key_of_same_principal_sees_runs(
        self, client: TestClient, other: dict, auth_headers, run_payload: dict
    ) -> None:
        run_id = client.post("/api/v1/runs", json=run_payload, headers=auth_headers).json()[
            "run_id"
        ]
        second = {"Authorization": f"Bearer {SECOND_TEST_USER_RAW}"}
        assert client.get(f"/api/v1/runs/{run_id}", headers=second).status_code == 200


class TestConversations:
    def test_list_only_own(self, client: TestClient, other: dict, auth_headers):
        convs = client.get("/api/v1/conversations", headers=auth_headers).json()["conversations"]
        assert other["conversation_id"] not in {c["id"] for c in convs}

    def test_foreign_conversation_is_404(self, client: TestClient, other: dict, auth_headers):
        cid = other["conversation_id"]
        assert client.get(f"/api/v1/conversations/{cid}", headers=auth_headers).status_code == 404
        assert client.get(f"/api/v1/conversations/{cid}", headers=B).status_code == 200

    def test_same_principal_other_key_sees_conversation(
        self, client: TestClient, other: dict, auth_headers
    ) -> None:
        cid = client.post("/api/v1/conversations", json={}, headers=auth_headers).json()["id"]
        second = {"Authorization": f"Bearer {SECOND_TEST_USER_RAW}"}
        assert client.get(f"/api/v1/conversations/{cid}", headers=second).status_code == 200

    def test_ws_stream_rejects_foreign_conversation(
        self, client: TestClient, other: dict, db_engine
    ) -> None:
        factory = sessionmaker(bind=db_engine)
        url = (
            f"/api/v1/ws/conversations/{other['conversation_id']}/stream"
            "?api_key=test-integration-api-key-abc123def456"
        )
        with (
            patch(
                "src.api.websocket.conversation_stream.get_session_factory",
                return_value=factory,
            ),
            pytest.raises(WebSocketDisconnect) as exc,
            client.websocket_connect(url),
        ):
            pass
        assert exc.value.code == 4404


def test_unknown_ids_and_foreign_ids_look_the_same(
    client: TestClient, other: dict, auth_headers
) -> None:
    """A foreign run's 404 body matches a non-existent run's, apart from the id."""
    foreign = client.get(f"/api/v1/runs/{other['run_id']}", headers=auth_headers).json()
    missing_id = str(uuid.uuid4())
    missing = client.get(f"/api/v1/runs/{missing_id}", headers=auth_headers).json()
    assert foreign["detail"].replace(other["run_id"], "X") == missing["detail"].replace(
        missing_id, "X"
    )
