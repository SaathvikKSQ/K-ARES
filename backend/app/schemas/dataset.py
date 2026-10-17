"""Dataset API schemas (FR-B1..FR-B6, FR-G)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ApplicationType, CaseStatus


class ValidationIssue(BaseModel):
    row: int
    field: str
    message: str


class ValidationReport(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    issues: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    application_type: ApplicationType
    owner: str | None = None
    version_count: int = 0


class DatasetVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    content_hash: str
    case_count: int
    valid_case_count: int
    invalid_case_count: int
    created_by: str | None = None
    created_at: Any = None


class TestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    external_id: str | None = None
    status: CaseStatus
    validation_errors: list[Any] = []
    input: dict[str, Any]
    expected_output: str | None = None
    reference_context: str | None = None
    relevant_doc_ids: list[Any] | None = None
    expected_tool: dict[str, Any] | None = None
    expected_action_sequence: list[Any] | None = None
    expected_structured_output: dict[str, Any] | None = None
    application_type: ApplicationType
    category: str | None = None
    tags: list[Any] = []
    is_security_case: bool = False


class DatasetVersionDetail(BaseModel):
    dataset: DatasetOut
    version: DatasetVersionOut
    validation_report: ValidationReport | None = None
