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
from src.db.models.project import Project
from src.db.models.run import AnalysisRun, PipelineStage
from tests.api.conftest import TEST_API_KEY_RAW, auth_frame, ws_close_code


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
    def _add_run(
        factory: sessionmaker,
        seed_data: dict,
        created_by: uuid.UUID,
        project_owner: str | None = None,
    ) -> str:
        """Add a run; in the seeded (test-user) project unless *project_owner* is given."""
        with factory() as session:
            project_id = seed_data["project_id"]
            if project_owner is not None:
                project = Project(name=f"{project_owner} project", owner=project_owner)
                session.add(project)
                session.flush()
                project_id = project.id
            run = AnalysisRun(
                project_id=project_id,
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
    def _add_key(
        factory: sessionmaker, raw: str, principal: str = "test-user", *, revoked: bool = False
    ) -> uuid.UUID:
        with factory() as session:
            key = APIKey(
                key_hash=hashlib.sha256(raw.encode()).hexdigest(),
                name=raw,
                created_by="test-admin",
                principal=principal,
                revoked_at=datetime.now(UTC) if revoked else None,
            )
            session.add(key)
            session.commit()
            return key.id

    @staticmethod
    def _url(run_id: str) -> str:
        return f"/api/v1/ws/runs/{run_id}/logs"

    def _close_code(self, client: TestClient, run_id: str, api_key: str) -> int:
        return ws_close_code(client, self._url(run_id), auth_frame(api_key))

    def test_owner_receives_initial_message(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        with client.websocket_connect(self._url(run_id)) as ws:
            ws.send_json(auth_frame(TEST_API_KEY_RAW))
            msg = ws.receive_json()
        assert run_id in msg["message"]
        assert msg["level"] == "info"
        assert "ts" in msg

    def test_no_auth_frame_times_out(self, client: TestClient, seed_data: dict, ws_db) -> None:
        """Nothing is sent before the auth frame arrives."""
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        with (
            patch("src.api.ws_auth.WS_AUTH_TIMEOUT_S", 0.05),
            client.websocket_connect(self._url(run_id)) as ws,
            pytest.raises(WebSocketDisconnect) as exc,
        ):
            ws.receive_text()  # first thing received is the close, not a log frame
        assert exc.value.code == 4403

    def test_key_in_url_refused_even_if_valid(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        url = f"{self._url(run_id)}?api_key={TEST_API_KEY_RAW}"
        with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(url):
            pass
        assert exc.value.code == 4403

    @pytest.mark.parametrize(
        "frame",
        [
            "not json",
            "[]",
            {"type": "hello", "api_key": TEST_API_KEY_RAW},
            {"type": "auth"},
            {"type": "auth", "api_key": ""},
            {"type": "auth", "api_key": 123},
            {"type": "auth", "api_key": TEST_API_KEY_RAW, "pad": "x" * 2000},
        ],
    )
    def test_malformed_auth_frame_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker, frame: object
    ) -> None:
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        assert ws_close_code(client, self._url(run_id), frame) == 4403

    def test_unknown_api_key_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        assert self._close_code(client, run_id, "not-a-real-key") == 4403

    def test_revoked_api_key_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        key_id = self._add_key(ws_db, "revoked-key", revoked=True)
        run_id = self._add_run(ws_db, seed_data, key_id)
        assert self._close_code(client, run_id, "revoked-key") == 4403

    def test_run_of_another_principal_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        other = self._add_key(ws_db, "other-users-key", "team_b")
        run_id = self._add_run(ws_db, seed_data, other, project_owner="team_b")
        assert self._close_code(client, run_id, TEST_API_KEY_RAW) == 4404

    def test_run_of_another_key_same_principal_allowed(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        rotated = self._add_key(ws_db, "rotated-key-of-test-user")
        run_id = self._add_run(ws_db, seed_data, rotated)
        with client.websocket_connect(self._url(run_id)) as ws:
            ws.send_json(auth_frame(TEST_API_KEY_RAW))
            assert run_id in ws.receive_json()["message"]

    def test_unknown_run_rejected_like_foreign_run(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        assert self._close_code(client, str(uuid.uuid4()), TEST_API_KEY_RAW) == 4404

    def test_malformed_run_id_rejected(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        assert self._close_code(client, "not-a-uuid", TEST_API_KEY_RAW) == 4404

    def test_rejected_before_redis_subscribe(
        self, client: TestClient, seed_data: dict, ws_db: sessionmaker
    ) -> None:
        run_id = self._add_run(ws_db, seed_data, seed_data["api_key_id"])
        with patch("redis.asyncio.from_url") as from_url:
            self._close_code(client, run_id, "bad")
        from_url.assert_not_called()
