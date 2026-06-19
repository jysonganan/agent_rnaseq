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
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.post(
            "/api/v1/api-keys",
            json={"name": "new-key"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        body = r.json()
        assert "raw_key" in body
        assert len(body["raw_key"]) > 0

    def test_create_key_is_active(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.post("/api/v1/api-keys", json={"name": "new-key"}, headers=auth_headers)
        assert r.json()["is_active"] is True

    def test_list_keys_omits_raw_key(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.get("/api/v1/api-keys", headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert "raw_key" not in item

    def test_revoke_key_returns_204(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.post("/api/v1/api-keys", json={"name": "to-revoke"}, headers=auth_headers)
        key_id = r.json()["id"]
        r2 = client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)
        assert r2.status_code == 204

    def test_revoked_key_returns_401(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        # Create a key
        r = client.post("/api/v1/api-keys", json={"name": "to-revoke-2"}, headers=auth_headers)
        new_raw = r.json()["raw_key"]
        key_id = r.json()["id"]

        # Verify the new key works
        r2 = client.get(
            "/api/v1/genomes",
            headers={"Authorization": f"Bearer {new_raw}"},
        )
        assert r2.status_code == 200

        # Revoke it
        client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)

        # Now it should be rejected
        r3 = client.get(
            "/api/v1/genomes",
            headers={"Authorization": f"Bearer {new_raw}"},
        )
        assert r3.status_code == 401

    def test_delete_unknown_key_returns_404(
        self, client: TestClient, seed_data: dict, auth_headers: dict
    ) -> None:
        r = client.delete(f"/api/v1/api-keys/{uuid.uuid4()}", headers=auth_headers)
        assert r.status_code == 404
