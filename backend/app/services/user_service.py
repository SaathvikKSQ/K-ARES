"""Service layer: user account management and authentication."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when authentication fails (message is safe to expose)."""


def get_user_by_email(session: Session, email: str) -> User | None:
    """Return an active user by email, or None."""
    stmt = select(User).where(User.email == email.strip().lower())
    return session.execute(stmt).scalar_one_or_none()


def get_user_by_id(session: Session, user_id: str) -> User | None:
    """Return a user by id, or None."""
    try:
        from uuid import UUID

        stmt = select(User).where(User.id == UUID(user_id))
        return session.execute(stmt).scalar_one_or_none()
    except (ValueError, TypeError):
        return None


def authenticate(session: Session, email: str, password: str) -> User:
    """Verify credentials; raise ``AuthError`` on failure (constant-time-ish)."""
    user = get_user_by_email(session, email)
    stored_hash = user.password_hash if user else ""
    if not verify_password(password, stored_hash):
        # Same error for unknown user and bad password (no account enumeration).
        raise AuthError("Invalid email or password")
    if not user.is_active:
        raise AuthError("Account is disabled")
    return user


def create_user(session: Session, email: str, password: str, role: str = "viewer") -> User:
    """Create a user with a hashed password."""
    if get_user_by_email(session, email) is not None:
        raise ValueError("email already registered")
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=role,  # type: ignore[arg-type]
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def seed_admin_from_env(session: Session, settings) -> str | None:
    """Create the initial admin from env settings if configured and absent.

    Returns a status string; never logs or returns the password.
    """
    if not settings.admin_email or not settings.admin_password:
        return "admin bootstrap not configured (set ADMIN_EMAIL/ADMIN_PASSWORD)"
    if get_user_by_email(session, settings.admin_email) is not None:
        return "admin already exists"
    create_user(session, settings.admin_email, settings.admin_password, role="admin")
    logger.info("Seeded initial admin user (email masked)")
    return "admin created"
