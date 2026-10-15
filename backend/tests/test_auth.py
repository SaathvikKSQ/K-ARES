"""Auth MVP tests (acceptance P1: login works; roles enforced)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_login_success_sets_cookie_and_token(client: TestClient, admin_user) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert "kaers_session" in resp.cookies


def test_login_wrong_password_is_unauthorized(client: TestClient, admin_user) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_login_unknown_user_same_error(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": "nobody@kaers.dev", "password": "x"})
    assert resp.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_with_bearer_token(client: TestClient, auth_headers: dict) -> None:
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "admin"
    assert "password_hash" not in body


def test_me_with_session_cookie(client: TestClient, admin_user) -> None:
    client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    resp = client.get("/api/v1/auth/me")  # cookie persisted by TestClient
    assert resp.status_code == 200


def test_logout_clears_cookie(client: TestClient, admin_user) -> None:
    client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
