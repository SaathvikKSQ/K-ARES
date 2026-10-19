"""Dashboard overview endpoint (FR-G1) — real aggregates, no hardcoded data."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.report import OverviewOut
from app.services import report_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=OverviewOut)
def dashboard_overview(session: DbSession, user: CurrentUser):
    """Counts, status breakdown, recent runs, key metrics, recent failures."""
    return report_service.overview(session)
