"""Tests for run management endpoints."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from starlette.websockets import WebSocketDisconnect

from src.db.enums import Aligner, AlignmentMode, PipelineType, RunStatus, StageName, StageStatus
from src.db.models.auth import APIKey
from src.db.models.run import AnalysisRun, PipelineStage
from tests.api.conftest import TEST_API_KEY_RAW


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
    """Run log stream: API key + run ownership are checked before the socket is accepted."""

    @pytest.fixture
    def ws_db(self, db_engine) -> Iterator[sessionmaker]:
        factory = sessionmaker(bind=db_engine)
        with patch("src.api.ws.logs.get_session_factory", return_value=factory):
            yield factory

    @staticmethod
    def _add_run(factory: sessionmaker, seed_data: dict, created_by: uuid.UUID) -> str:
        with factory() as session:
            run = AnalysisRun(
                project_id=seed_data["project_id"],
                genome_id=seed_data["genome_id"],
                created_by=created_by,
                name="ws-run",
                status=RunStatus.running,
                pipeline_type=PipelineType.bulk_rnaseq,
                alignment_mode=AlignmentMode.genome,
                aligner=Aligner.star,
                run_config={},
            )
            session.add(run)
            session.commit()
            return str(run.id)

    @staticmethod
    def _add_key(factory: sessionmaker, raw: str, *, revoked: bool = False) -> uuid.UUID:
        with factory() as session:
            key = APIKey(
                key_hash=hashlib.sha256(raw.encode()).hexdigest(),
                name=raw,
                created_by="test-admin",
                revoked_at=datetime.now(UTC) if revoked else None,
            )
            session.add(key)
            session.commit()
            return key.id

    @staticmethod
    def _close_code(client: TestClient, url: str) -> int:
        with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(url):
            pass
        return exc.value.code

    def test_owner_receives_initial_message(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        url = f"/api/v1/ws/runs/{run_id}/logs?api_key={TEST_API_KEY_RAW}"
        with client.websocket_connect(url) as ws:
            msg = ws.receive_json()
        assert run_id in msg["message"]
        assert msg["level"] == "info"
        assert "ts" in msg

    def test_missing_api_key_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        assert self._close_code(client, f"/api/v1/ws/runs/{run_id}/logs") == 4403

    def test_unknown_api_key_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        url = f"/api/v1/ws/runs/{run_id}/logs?api_key=not-a-real-key"
        assert self._close_code(client, url) == 4403

    def test_revoked_api_key_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        key_id = self._add_key(ws_db, "revoked-key", revoked=True)
        run_id = self._add_run(ws_db, seed_data, key_id)
        url = f"/api/v1/ws/runs/{run_id}/logs?api_key=revoked-key"
        assert self._close_code(client, url) == 4403

    def test_run_of_another_key_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        other = self._add_key(ws_db, "other-users-key")
        run_id = self._add_run(ws_db, seed_data, other)
        url = f"/api/v1/ws/runs/{run_id}/logs?api_key={TEST_API_KEY_RAW}"
        assert self._close_code(client, url) == 4404

    def test_unknown_run_rejected_like_foreign_run(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        url = f"/api/v1/ws/runs/{uuid.uuid4()}/logs?api_key={TEST_API_KEY_RAW}"
        assert self._close_code(client, url) == 4404

    def test_malformed_run_id_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        url = f"/api/v1/ws/runs/not-a-uuid/logs?api_key={TEST_API_KEY_RAW}"
        assert self._close_code(client, url) == 4404

    def test_rejected_before_redis_subscribe(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        with patch("redis.asyncio.from_url") as from_url:
            self._close_code(client, f"/api/v1/ws/runs/{run_id}/logs?api_key=bad")
        from_url.assert_not_called()
