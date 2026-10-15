"""Pytest fixtures: isolated SQLite DB, app client, authenticated helpers.

Environment variables are set BEFORE importing app modules so cached settings
pick them up (constitution §6: no paid APIs, deterministic fixtures).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="kaers-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR / 'test.db'}"
os.environ["SECRET_KEY"] = "unit-test-secret-key"
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["ADMIN_EMAIL"] = "admin@kaers.dev"
os.environ["ADMIN_PASSWORD"] = "test-admin-password-123"
os.environ["DATA_DIR"] = str(_TMP_DIR / "data")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import create_db_engine, get_db, make_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.user_service import create_user  # noqa: E402

ADMIN_EMAIL = "admin@kaers.dev"
ADMIN_PASSWORD = "test-admin-password-123"


@pytest.fixture(scope="session")
def engine():
    engine = create_db_engine()
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(engine) -> Iterator[Session]:
    """A fresh session per test; tables persist across the session."""
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    """TestClient wired to the test session via dependency override."""
    app = create_app()

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db_session: Session):
    """An admin user, created if not already present."""
    from app.services.user_service import get_user_by_email

    user = get_user_by_email(db_session, ADMIN_EMAIL)
    if user is None:
        user = create_user(db_session, ADMIN_EMAIL, ADMIN_PASSWORD, role="admin")
        db_session.commit()
    return user


@pytest.fixture()
def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    """Bearer headers for an authenticated admin."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
