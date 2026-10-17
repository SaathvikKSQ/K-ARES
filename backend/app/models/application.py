"""Application and application-config models (Module A).

Credentials are stored only as encrypted bytes (Fernet) — never plaintext
(SR-8). Config snapshots never contain credentials (data-model.md).
"""

from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import ApplicationType, IntegrationType, str_enum
from app.models.types import JSONType

DEFAULT_CAPABILITIES: dict[str, bool] = {
    "exposes_retrieved_docs": False,
    "exposes_citations": False,
    "exposes_traces": False,
    "exposes_token_usage": False,
    "streaming": False,
}


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registered AI application under evaluation."""

    __tablename__ = "applications"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    application_type: Mapped[ApplicationType] = mapped_column(
        str_enum(ApplicationType, "application_type"), nullable=False
    )
    integration_type: Mapped[IntegrationType] = mapped_column(
        str_enum(IntegrationType, "integration_type"), nullable=False
    )
    # Fernet-encrypted JSON blob holding auth fields only; None when unused.
    connection_config_encrypted: Mapped[bytes | None] = mapped_column(nullable=True)
    connection_base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    invoke_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    current_version_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Sanitized result of the most recent connection test (no secrets).
    last_connection_test: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    configs: Mapped[list[ApplicationConfig]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationConfig.created_at",
    )


class ApplicationConfig(UUIDPrimaryKeyMixin, Base):
    """Immutable, sanitized configuration snapshot of an application."""

    __tablename__ = "application_configs"

    application_id: Mapped[object] = mapped_column(
        Uuid(), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    version_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    code_revision: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)  # sanitized only
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    application: Mapped[Application] = relationship(back_populates="configs")
