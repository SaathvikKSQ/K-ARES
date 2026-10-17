"""Phase 2: application registry API — CRUD, secret masking, connection tests."""

from __future__ import annotations

import uuid as _uuid

from fastapi.testclient import TestClient


def _mock_app() -> dict:
    """Unique payload per call (the test DB is shared across the session)."""
    return {
        "name": f"Mock RAG App {_uuid.uuid4().hex[:8]}",
        "description": "Deterministic mock for tests",
        "application_type": "rag",
        "integration_type": "mock",
        "capabilities": {
            "exposes_retrieved_docs": True,
            "exposes_citations": False,
            "exposes_traces": False,
            "exposes_token_usage": True,
            "streaming": False,
        },
    }


def test_create_and_get_application_masks_credentials(client: TestClient, auth_headers):
    payload = {**_mock_app(), "credentials": {"type": "bearer", "value": "super-secret-token"}}
    resp = client.post("/api/v1/applications", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == payload["name"]
    assert body["has_credentials"] is True
    # The secret must never appear anywhere in the response (SR-8).
    assert "super-secret-token" not in resp.text

    got = client.get(f"/api/v1/applications/{body['id']}", headers=auth_headers)
    assert got.status_code == 200
    assert "super-secret-token" not in got.text
    assert got.json()["has_credentials"] is True


def test_duplicate_application_name_conflict(client: TestClient, auth_headers):
    payload = _mock_app()
    client.post("/api/v1/applications", json=payload, headers=auth_headers)
    resp = client.post("/api/v1/applications", json=payload, headers=auth_headers)
    assert resp.status_code == 409


def test_rest_application_requires_valid_url(client: TestClient, auth_headers):
    bad = client.post(
        "/api/v1/applications",
        json={
            "name": "Bad URL App",
            "application_type": "llm",
            "integration_type": "rest_api",
            "base_url": "http://169.254.169.254/latest/meta-data",  # link-local (SSRF)
        },
        headers=auth_headers,
    )
    assert bad.status_code == 422
    missing = client.post(
        "/api/v1/applications",
        json={"name": "No URL App", "application_type": "llm", "integration_type": "rest_api"},
        headers=auth_headers,
    )
    assert missing.status_code == 422


def test_update_application_and_snapshot(client: TestClient, auth_headers):
    created = client.post("/api/v1/applications", json=_mock_app(), headers=auth_headers).json()
    resp = client.patch(
        f"/api/v1/applications/{created['id']}",
        json={"description": "Updated description", "is_enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated description"
    assert resp.json()["is_enabled"] is False


def test_mock_connection_test_succeeds(client: TestClient, auth_headers):
    created = client.post("/api/v1/applications", json=_mock_app(), headers=auth_headers).json()
    app_id = created["id"]
    resp = client.post(f"/api/v1/applications/{app_id}/connection-test", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert "mock" in body["message"].lower()

def test_rest_connection_test_unreachable_target(client: TestClient, auth_headers):
    created = client.post(
        "/api/v1/applications",
        json={
            "name": f"Unreachable App {_uuid.uuid4().hex[:8]}",
            "application_type": "llm",
            "integration_type": "rest_api",
            # example.com resolves (the SSRF validator requires a resolvable
            # hostname) but port 9 (discard) refuses connections -> fast failure.
            "base_url": "http://example.com:9",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    app_id = created.json()["id"]
    resp = client.post(f"/api/v1/applications/{app_id}/connection-test", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    # The failure message must be sanitized (no exception internals).
    assert "Traceback" not in resp.text and "secret" not in resp.text.lower()

def test_unauthenticated_cannot_mutate_applications(client: TestClient, admin_user):
    # Viewer role gate is covered in test_auth; here: unauthenticated is 401.
    resp = client.get("/api/v1/applications")
    assert resp.status_code == 401
    resp = client.post("/api/v1/applications", json=_mock_app())
    assert resp.status_code in (401, 403)


def test_delete_application(client: TestClient, auth_headers):
    created = client.post("/api/v1/applications", json=_mock_app(), headers=auth_headers).json()
    resp = client.delete(f"/api/v1/applications/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    gone = client.get(f"/api/v1/applications/{created['id']}", headers=auth_headers)
    assert gone.status_code == 404
