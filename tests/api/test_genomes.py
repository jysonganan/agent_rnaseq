"""Tests for genome endpoints."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


class TestListGenomes:
    def test_no_auth_returns_401(self, client: TestClient) -> None:
        r = client.get("/api/v1/genomes")
        assert r.status_code == 401

    def test_returns_200_with_seed(self, client: TestClient, seed_data: dict, auth_headers: dict) -> None:
        r = client.get("/api/v1/genomes", headers=auth_headers)
        assert r.status_code == 200

    def test_seed_genome_in_list(self, client: TestClient, seed_data: dict, auth_headers: dict) -> None:
        r = client.get("/api/v1/genomes", headers=auth_headers)
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "hg38"

    def test_pagination_fields_present(self, client: TestClient, seed_data: dict, auth_headers: dict) -> None:
        r = client.get("/api/v1/genomes?limit=10&offset=0", headers=auth_headers)
        body = r.json()
        assert "limit" in body
        assert "offset" in body
        assert body["limit"] == 10
        assert body["offset"] == 0


class TestCreateGenome:
    def test_creates_genome(self, client: TestClient, seed_data: dict, auth_headers: dict) -> None:
        payload = {
            "name": "mm39",
            "species": "Mus musculus",
            "build": "GRCm39",
            "fasta_path": "/ref/mm39.fa",
            "gtf_path": "/ref/mm39.gtf",
        }
        r = client.post("/api/v1/genomes", json=payload, headers=auth_headers)
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "mm39"
        assert "id" in body


class TestGetGenome:
    def test_unknown_genome_returns_404(self, client: TestClient, seed_data: dict, auth_headers: dict) -> None:
        r = client.get(f"/api/v1/genomes/{uuid.uuid4()}", headers=auth_headers)
        assert r.status_code == 404

    def test_returns_genome_by_id(self, client: TestClient, seed_data: dict, auth_headers: dict) -> None:
        r = client.get(f"/api/v1/genomes/{seed_data['genome_id']}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["name"] == "hg38"
