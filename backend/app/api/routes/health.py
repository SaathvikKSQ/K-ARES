"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(session: DbSession) -> HealthResponse:
    """Liveness + database readiness check (unauthenticated)."""
    settings = get_settings()
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
        status_value = "ok"
    except Exception:  # pragma: no cover - defensive
        database = "unavailable"
        status_value = "degraded"
    return HealthResponse(
        status=status_value,
        database=database,
        version=settings.version,
        environment=settings.environment,
    )
