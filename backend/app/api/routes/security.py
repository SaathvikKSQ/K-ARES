"""Security suite catalog endpoint (T5.5, SR-25).

Serves the static code-versioned suite metadata (categories, covered
scenarios) and the mandatory disclaimer. Read-only; any authenticated user.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.evaluation.security.suite import suite_catalog

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/suites")
def list_security_suites(user: CurrentUser):
    """Static suite catalog; payloads live in code (decision D9)."""
    return suite_catalog()
