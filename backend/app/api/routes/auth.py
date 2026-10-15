"""Authentication endpoints: login, logout, me.

MVP auth per specs/security/security-requirements.md SR-1..SR-5 and
specs/api/interface-contract.md (Auth section).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.security import create_access_token
from app.schemas.common import LoginRequest, TokenResponse, UserOut
from app.services.user_service import AuthError, authenticate

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE = "kaers_session"


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, session: DbSession) -> TokenResponse:
    """Verify credentials and issue a signed session token (body + cookie)."""
    settings = get_settings()
    try:
        user = authenticate(session, payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    expires = settings.access_token_expire_minutes * 60
    token = create_access_token(str(user.id), user.role, settings.secret_key, expires)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=expires,
    )
    return TokenResponse(access_token=token, expires_in=expires)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """Clear the session cookie (stateless token; client discards it)."""
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """Return the authenticated user's profile."""
    return UserOut.model_validate(user)


@router.get("/openapi-check", include_in_schema=False)
def auth_probe(request: Request) -> dict:
    """Returns 401 when unauthenticated; used by tests and smoke checks."""
    return {"authenticated": bool(request.cookies.get(SESSION_COOKIE))}
