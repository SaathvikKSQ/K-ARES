"""Artifact index model (storage abstraction lives in app.storage)."""

from __future__ import annotations

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import ArtifactKind, str_enum


class Artifact(UUIDPrimaryKeyMixin, Base):
    """Index row for stored files (dataset files, exports, artifacts)."""

    __tablename__ = "artifacts"

    kind: Mapped[ArtifactKind] = mapped_column(
        str_enum(ArtifactKind, "artifact_kind"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
