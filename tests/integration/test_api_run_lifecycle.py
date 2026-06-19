"""Integration test: POST /runs lifecycle via TestClient."""

from __future__ import annotations

from tests.integration.conftest import AUTH_HEADERS


def _create_run_payload(seed: dict) -> dict:
    return {
        "project_id": seed["project_id"],
        "genome_id": seed["genome_id"],
        "name": "Integration Test Run",
        "pipeline_type": "bulk_rnaseq",
        "sample_ids": [seed["sample_id"]],
        "alignment_mode": "genome",
        "aligner": "star",
        "stages": ["qc", "alignment"],
        "de_contrasts": [],
    }


def test_create_run_returns_202(api_client):
    seed = api_client._seed
    resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed), headers=AUTH_HEADERS)
    assert resp.status_code == 202


def test_create_run_returns_run_id(api_client):
    seed = api_client._seed
    resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed), headers=AUTH_HEADERS)
    body = resp.json()
    assert "run_id" in body


def test_create_run_status_is_pending(api_client):
    seed = api_client._seed
    resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed), headers=AUTH_HEADERS)
    assert resp.json()["status"] == "pending"


def test_create_run_message_queued(api_client):
    seed = api_client._seed
    resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed), headers=AUTH_HEADERS)
    assert "queued" in resp.json()["message"].lower()


def test_list_runs_includes_created_run(api_client):
    seed = api_client._seed
    create_resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed), headers=AUTH_HEADERS)
    run_id = create_resp.json()["run_id"]

    list_resp = api_client.get("/api/v1/runs", headers=AUTH_HEADERS)
    assert list_resp.status_code == 200
    ids = [r["id"] for r in list_resp.json()["items"]]
    assert run_id in ids


def test_get_run_detail_returns_stages_list(api_client):
    seed = api_client._seed
    create_resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed), headers=AUTH_HEADERS)
    run_id = create_resp.json()["run_id"]

    detail_resp = api_client.get(f"/api/v1/runs/{run_id}", headers=AUTH_HEADERS)
    assert detail_resp.status_code == 200
    assert "stages" in detail_resp.json()


def test_get_run_detail_name_matches(api_client):
    seed = api_client._seed
    create_resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed), headers=AUTH_HEADERS)
    run_id = create_resp.json()["run_id"]

    detail_resp = api_client.get(f"/api/v1/runs/{run_id}", headers=AUTH_HEADERS)
    assert detail_resp.json()["name"] == "Integration Test Run"


def test_cancel_pending_run_returns_cancelled(api_client):
    seed = api_client._seed
    create_resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed), headers=AUTH_HEADERS)
    run_id = create_resp.json()["run_id"]

    cancel_resp = api_client.post(f"/api/v1/runs/{run_id}/cancel", headers=AUTH_HEADERS)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_cancel_nonexistent_run_returns_404(api_client):
    import uuid
    resp = api_client.post(f"/api/v1/runs/{uuid.uuid4()}/cancel", headers=AUTH_HEADERS)
    assert resp.status_code == 404


def test_get_nonexistent_run_returns_404(api_client):
    import uuid
    resp = api_client.get(f"/api/v1/runs/{uuid.uuid4()}", headers=AUTH_HEADERS)
    assert resp.status_code == 404


def test_create_run_requires_auth(api_client):
    seed = api_client._seed
    resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed))
    assert resp.status_code == 401


def test_list_runs_requires_auth(api_client):
    resp = api_client.get("/api/v1/runs")
    assert resp.status_code == 401


def test_cancel_already_cancelled_run_returns_409(api_client):
    seed = api_client._seed
    create_resp = api_client.post("/api/v1/runs", json=_create_run_payload(seed), headers=AUTH_HEADERS)
    run_id = create_resp.json()["run_id"]

    api_client.post(f"/api/v1/runs/{run_id}/cancel", headers=AUTH_HEADERS)
    second_cancel = api_client.post(f"/api/v1/runs/{run_id}/cancel", headers=AUTH_HEADERS)
    assert second_cancel.status_code == 409
