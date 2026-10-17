"""Application registry endpoints (FR-A1..FR-A3, FR-G).

All routes require authentication; mutations require editor/admin role.
Credentials are write-only: they are accepted in request bodies and never
returned by any endpoint (SR-8).
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, EditorUser
from app.schemas.application import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
    ConnectionTestOut,
)
from app.services import application_service as svc

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationOut])
def list_applications(session: DbSession, user: CurrentUser, enabled_only: bool = False):
    """List registered applications (secrets never included)."""
    return svc.list_applications(session, enabled_only=enabled_only)


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(payload: ApplicationCreate, session: DbSession, user: EditorUser):
    """Register an application. Credentials (if any) are encrypted at rest."""
    return svc.create_application(session, payload)


@router.get("/{app_id}", response_model=ApplicationOut)
def get_application(app_id: str, session: DbSession, user: CurrentUser):
    return svc.to_out(svc.get_application(session, app_id))


@router.patch("/{app_id}", response_model=ApplicationOut)
def update_application(
    app_id: str, payload: ApplicationUpdate, session: DbSession, user: EditorUser
):
    return svc.update_application(session, app_id, payload)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(app_id: str, session: DbSession, user: EditorUser) -> None:
    svc.delete_application(session, app_id)


@router.post("/{app_id}/connection-test", response_model=ConnectionTestOut)
async def test_connection(
    app_id: str, session: DbSession, user: EditorUser
) -> ConnectionTestOut:
    """Run a safe connectivity check; result is sanitized and persisted."""
    app = svc.get_application(session, app_id)
    return await svc.run_connection_test(session, app)
