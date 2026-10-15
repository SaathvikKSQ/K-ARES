"""Dataset, dataset-version, and test-case models (Module B).

Dataset versions are immutable. ``relevant_doc_ids`` semantics: NULL = not
labeled, [] = explicitly labeled "no relevant docs" (dataset-format.md).
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ApplicationType, CaseStatus, str_enum

# JSONB on PostgreSQL, portable JSON elsewhere (SQLite tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Dataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A logical evaluation dataset."""

    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    application_type: Mapped[ApplicationType] = mapped_column(
        str_enum(ApplicationType, "dataset_application_type"), nullable=False
    )
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)

    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetVersion.version_number",
    )


class DatasetVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable version of a dataset."""

    __tablename__ = "dataset_versions"

    dataset_id: Mapped[object] = mapped_column(
        Uuid(), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_case_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_case_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(320), nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    cases: Mapped[list[TestCase]] = relationship(
        back_populates="dataset_version", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version"),)


class TestCase(UUIDPrimaryKeyMixin, Base):
    """A single evaluation example. Invalid rows are retained, never dropped."""

    __tablename__ = "test_cases"

    dataset_version_id: Mapped[object] = mapped_column(
        Uuid(), ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # row order
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[CaseStatus] = mapped_column(str_enum(CaseStatus, "case_status"), nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    input: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)  # question/prompt
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)  # None = not provided
    reference_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevant_doc_ids: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    expected_tool: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    expected_action_sequence: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    expected_structured_output: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    application_type: Mapped[ApplicationType] = mapped_column(
        str_enum(ApplicationType, "case_application_type"), nullable=False
    )
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tags: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    is_security_case: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="cases")
