"""User model (MVP auth). Spec reference: specs/architecture/data-model.md."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole, str_enum


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Platform user with a single MVP role."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id!s} email={self.email!r} role={self.role}>"


def new_user_id() -> uuid.UUID:
    """Helper for tests/scripts."""
    return uuid.uuid4()
