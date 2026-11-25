"""Tests for API key management and authentication."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


class TestAuthRequired:
    def test_no_auth_header_returns_401(self, client: TestClient, seed_data: dict) -> None:
        r = client.get("/api/v1/genomes")
        assert r.status_code == 401

    def test_401_is_rfc9457(self, client: TestClient, seed_data: dict) -> None:
        r = client.get("/api/v1/genomes")
        body = r.json()
        assert body["status"] == 401
        assert "type" in body
        assert "detail" in body

    def test_invalid_key_returns_401(self, client: TestClient, seed_data: dict) -> None:
        r = client.get("/api/v1/genomes", headers={"Authorization": "Bearer bad-key-xxxx"})
        assert r.status_code == 401

    def test_health_no_auth_required(self, client: TestClient) -> None:
        r = client.get("/api/v1/health")
        assert r.status_code == 200


class TestAPIKeyManagement:
    def test_create_key_returns_raw_key(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        r = client.post(
            "/api/v1/api-keys",
            json={"name": "new-key"},
            headers=admin_headers,
        )
        assert r.status_code == 201
        body = r.json()
        assert "raw_key" in body
        assert len(body["raw_key"]) > 0

    def test_create_key_is_active(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        r = client.post("/api/v1/api-keys", json={"name": "new-key"}, headers=admin_headers)
        assert r.json()["is_active"] is True

    def test_list_keys_omits_raw_key(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        r = client.get("/api/v1/api-keys", headers=admin_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert "raw_key" not in item

    def test_revoke_key_returns_204(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        r = client.post("/api/v1/api-keys", json={"name": "to-revoke"}, headers=admin_headers)
        key_id = r.json()["id"]
        r2 = client.delete(f"/api/v1/api-keys/{key_id}", headers=admin_headers)
        assert r2.status_code == 204

    def test_revoked_key_returns_401(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        # Create a key
        r = client.post("/api/v1/api-keys", json={"name": "to-revoke-2"}, headers=admin_headers)
        new_raw = r.json()["raw_key"]
        key_id = r.json()["id"]

        # Verify the new key works
        r2 = client.get(
            "/api/v1/genomes",
            headers={"Authorization": f"Bearer {new_raw}"},
        )
        assert r2.status_code == 200

        # Revoke it
        client.delete(f"/api/v1/api-keys/{key_id}", headers=admin_headers)

        # Now it should be rejected
        r3 = client.get(
            "/api/v1/genomes",
            headers={"Authorization": f"Bearer {new_raw}"},
        )
        assert r3.status_code == 401

    def test_delete_unknown_key_returns_404(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        r = client.delete(f"/api/v1/api-keys/{uuid.uuid4()}", headers=admin_headers)
        assert r.status_code == 404


class TestAdminOnlyKeyManagement:
    def test_non_admin_cannot_create_key(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.post("/api/v1/api-keys", json={"name": "x"}, headers=auth_headers)
        assert r.status_code == 403

    def test_non_admin_cannot_list_keys(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        assert client.get("/api/v1/api-keys", headers=auth_headers).status_code == 403

    def test_non_admin_cannot_revoke_key(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.delete(f"/api/v1/api-keys/{seed_data['api_key_id']}", headers=auth_headers)
        assert r.status_code == 403

    def test_admin_sets_principal_and_admin_flag(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        r = client.post(
            "/api/v1/api-keys",
            json={"name": "team-a-ci", "principal": "team_a", "is_admin": True},
            headers=admin_headers,
        )
        assert r.status_code == 201
        body = r.json()
        assert (body["principal"], body["is_admin"], body["created_by"]) == (
            "team_a",
            True,
            "bootstrap",
        )

    def test_principal_defaults_to_issuer(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        r = client.post("/api/v1/api-keys", json={"name": "k2"}, headers=admin_headers)
        assert r.json()["principal"] == "admin"  # BOOTSTRAP_PRINCIPAL default
        assert r.json()["is_admin"] is False

    def test_invalid_principal_rejected(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        r = client.post(
            "/api/v1/api-keys",
            json={"name": "k3", "principal": "has spaces"},
            headers=admin_headers,
        )
        assert r.status_code == 422

    def test_reserved_name_rejected(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        r = client.post("/api/v1/api-keys", json={"name": "bootstrap"}, headers=admin_headers)
        assert r.status_code == 422

    def test_list_excludes_revoked(
        self, client: TestClient, seed_data: dict, admin_headers: dict
    ) -> None:
        kid = client.post("/api/v1/api-keys", json={"name": "gone"}, headers=admin_headers).json()[
            "id"
        ]
        client.delete(f"/api/v1/api-keys/{kid}", headers=admin_headers)
        ids = {
            k["id"] for k in client.get("/api/v1/api-keys", headers=admin_headers).json()["items"]
        }
        assert kid not in ids


class TestBootstrapKey:
    def test_bootstrap_key_is_stored_once_as_admin(
        self, client: TestClient, seed_data: dict, admin_headers: dict, db_engine
    ) -> None:
        from sqlalchemy.orm import Session

        from src.db.models.auth import APIKey

        for _ in range(2):
            assert client.get("/api/v1/api-keys", headers=admin_headers).status_code == 200
        with Session(db_engine) as s:
            rows = s.query(APIKey).filter(APIKey.name == "bootstrap").all()
        assert len(rows) == 1
        assert rows[0].is_admin and rows[0].principal == "admin"

    def test_previous_bootstrap_value_stops_working(
        self, client: TestClient, seed_data: dict, admin_headers: dict, monkeypatch
    ) -> None:
        from src.config import get_settings

        assert client.get("/api/v1/api-keys", headers=admin_headers).status_code == 200
        monkeypatch.setattr(get_settings(), "api_key_bootstrap", "a-new-bootstrap-value-123")
        assert client.get("/api/v1/api-keys", headers=admin_headers).status_code == 401
        new = {"Authorization": "Bearer a-new-bootstrap-value-123"}
        assert client.get("/api/v1/api-keys", headers=new).status_code == 200

    def test_placeholder_bootstrap_is_disabled(
        self, client: TestClient, seed_data: dict, monkeypatch
    ) -> None:
        from src.config import get_settings

        monkeypatch.setattr(get_settings(), "api_key_bootstrap", "change-me-before-use")
        r = client.get("/api/v1/api-keys", headers={"Authorization": "Bearer change-me-before-use"})
        assert r.status_code == 401

    def test_short_bootstrap_is_disabled(
        self, client: TestClient, seed_data: dict, monkeypatch
    ) -> None:
        from src.config import get_settings

        monkeypatch.setattr(get_settings(), "api_key_bootstrap", "short")
        r = client.get("/api/v1/api-keys", headers={"Authorization": "Bearer short"})
        assert r.status_code == 401
