"""Tests for run management endpoints."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.db.enums import Aligner, AlignmentMode, PipelineType, RunStatus, StageName, StageStatus
from src.db.models.run import AnalysisRun, PipelineStage


class TestCreateRun:
    def test_returns_202(
        self, client: TestClient, seed_data: dict, auth_headers: dict, run_payload: dict
    ) -> None:
        r = client.post("/api/v1/runs", json=run_payload, headers=auth_headers)
        assert r.status_code == 202

    def test_body_has_run_id(
        self, client: TestClient, seed_data: dict, auth_headers: dict, run_payload: dict
    ) -> None:
        r = client.post("/api/v1/runs", json=run_payload, headers=auth_headers)
        body = r.json()
        assert "run_id" in body
        uuid.UUID(body["run_id"])  # must be a valid UUID

    def test_status_is_pending(
        self, client: TestClient, seed_data: dict, auth_headers: dict, run_payload: dict
    ) -> None:
        r = client.post("/api/v1/runs", json=run_payload, headers=auth_headers)
        assert r.json()["status"] == "pending"

    def test_no_auth_returns_401(self, client: TestClient, run_payload: dict) -> None:
        r = client.post("/api/v1/runs", json=run_payload)
        assert r.status_code == 401

    def test_invalid_alignment_mode_returns_422(
        self, client: TestClient, seed_data: dict, auth_headers: dict, run_payload: dict
    ) -> None:
        bad_payload = {**run_payload, "alignment_mode": "invalid_mode"}
        r = client.post("/api/v1/runs", json=bad_payload, headers=auth_headers)
        assert r.status_code == 422

    def test_invalid_alignment_mode_is_rfc9457(
        self, client: TestClient, seed_data: dict, auth_headers: dict, run_payload: dict
    ) -> None:
        bad_payload = {**run_payload, "alignment_mode": "invalid_mode"}
        r = client.post("/api/v1/runs", json=bad_payload, headers=auth_headers)
        body = r.json()
        assert "type" in body
        assert "status" in body
        assert body["status"] == 422

    def test_rate_limit_11th_request_is_429(
        self, client: TestClient, seed_data: dict, auth_headers: dict, run_payload: dict
    ) -> None:
        for _ in range(10):
            r = client.post("/api/v1/runs", json=run_payload, headers=auth_headers)
            assert r.status_code == 202, f"Expected 202, got {r.status_code}"
        r = client.post("/api/v1/runs", json=run_payload, headers=auth_headers)
        assert r.status_code == 429


class TestGetRun:
    def test_unknown_run_returns_404(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.get(f"/api/v1/runs/{uuid.uuid4()}", headers=auth_headers)
        assert r.status_code == 404

    def test_404_is_rfc9457(self, client: TestClient, seed_data: dict, auth_headers: dict) -> None:
        r = client.get(f"/api/v1/runs/{uuid.uuid4()}", headers=auth_headers)
        body = r.json()
        assert body["status"] == 404
        assert "type" in body
        assert body["type"].startswith("https://")
        assert "detail" in body
        assert "instance" in body

    def test_returns_run_with_stages(
        self, client: TestClient, seed_data: dict, auth_headers: dict, db_engine
    ) -> None:
        # Create a run with one stage directly in DB
        with Session(db_engine) as session:
            run = AnalysisRun(
                project_id=seed_data["project_id"],
                genome_id=seed_data["genome_id"],
                created_by=seed_data["api_key_id"],
                name="completed-run",
                status=RunStatus.completed,
                pipeline_type=PipelineType.bulk_rnaseq,
                alignment_mode=AlignmentMode.genome,
                aligner=Aligner.star,
                run_config={},
            )
            session.add(run)
            session.flush()
            stage = PipelineStage(
                run_id=run.id,
                stage_name=StageName.qc,
                status=StageStatus.completed,
                tool_name="fastqc",
            )
            session.add(stage)
            session.commit()
            run_id = run.id

        r = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert len(body["stages"]) == 1
        assert body["stages"][0]["stage_name"] == "qc"

    def test_no_auth_returns_401(self, client: TestClient, seed_data: dict) -> None:
        r = client.get(f"/api/v1/runs/{uuid.uuid4()}")
        assert r.status_code == 401


class TestWebSocket:
    def test_receives_initial_message(self, client: TestClient) -> None:
        run_id = str(uuid.uuid4())
        with client.websocket_connect(f"/api/v1/ws/runs/{run_id}/logs") as ws:
            msg = ws.receive_json()
            assert "message" in msg
            assert run_id in msg["message"]
            assert "ts" in msg

    def test_initial_message_has_level_info(self, client: TestClient) -> None:
        run_id = str(uuid.uuid4())
        with client.websocket_connect(f"/api/v1/ws/runs/{run_id}/logs") as ws:
            msg = ws.receive_json()
            assert msg["level"] == "info"
