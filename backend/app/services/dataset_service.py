"""Dataset upload, validation, and immutable versioning (T2.4, FR-B1..B6)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.dataset import Dataset, DatasetVersion, TestCase
from app.models.enums import ApplicationType, CaseStatus
from app.schemas.dataset import ValidationIssue, ValidationReport
from app.storage import local_store

SECURITY_MARKER_FIELDS = ("attack_type", "injection_payload", "security_category")


class DatasetError(HTTPException):
    def __init__(self, code_status: int, detail: str):
        super().__init__(status_code=code_status, detail=detail)


def parse_rows(content: bytes, filename: str) -> list[dict[str, Any]]:
    """Parse JSONL or CSV into a list of raw row dicts."""
    text = content.decode("utf-8-sig")
    lower = filename.lower()
    if lower.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        return [{k: v for k, v in raw.items() if k is not None} for raw in reader]
    if lower.endswith((".jsonl", ".json")):
        rows: list[dict[str, Any]] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(422, f"Line {lineno}: invalid JSON ({exc.msg})") from exc
            if not isinstance(obj, dict):
                raise DatasetError(422, f"Line {lineno}: each line must be a JSON object")
            rows.append(obj)
        return rows
    raise DatasetError(422, "Unsupported file type; upload .jsonl or .csv")


def _field_str(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return str(value)
    return None


def validate_row(
    row: dict[str, Any], application_type: ApplicationType, position: int
) -> tuple[dict[str, Any], list[ValidationIssue], list[ValidationIssue]]:
    """Return (parsed_case, errors, warnings) for one row."""
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    def err(field: str, message: str) -> None:
        errors.append(ValidationIssue(row=position, field=field, message=message))

    def warn(field: str, message: str) -> None:
        warnings.append(ValidationIssue(row=position, field=field, message=message))

    input_value = row.get("input", row.get("question", row.get("prompt")))
    if input_value is None or str(input_value).strip() == "":
        err("input", "required field 'input' (or 'question'/'prompt') is missing or empty")
    external_id = _field_str(row, "id", "external_id")
    expected_output = _field_str(row, "expected_output", "expected_answer")
    reference_context = _field_str(row, "reference_context", "context")

    relevant_doc_ids: list[str] | None = None  # None = not labeled
    raw_docs = row.get("relevant_doc_ids")
    if raw_docs is not None:
        if isinstance(raw_docs, str):
            raw_docs = [part.strip() for part in raw_docs.split("|") if part.strip()]
        if not isinstance(raw_docs, list) or not all(isinstance(item, str) for item in raw_docs):
            err(
                "relevant_doc_ids",
                "must be a list of strings (empty list means 'no relevant docs')",
            )
        else:
            relevant_doc_ids = raw_docs

    expected_tool: dict[str, Any] | None = None
    if row.get("expected_tool") is not None:
        tool = row["expected_tool"]
        if isinstance(tool, str):
            tool = {"name": tool}
        if not isinstance(tool, dict) or not tool.get("name"):
            err("expected_tool", "must be an object with at least a 'name' key")
        else:
            expected_tool = tool
            if application_type != ApplicationType.AGENT:
                warn("expected_tool", "expected_tool is only meaningful for agent datasets")

    action_seq = row.get("expected_action_sequence")
    if action_seq is not None and not isinstance(action_seq, list):
        err("expected_action_sequence", "must be a list of action strings")
    structured = row.get("expected_structured_output")
    if structured is not None and not isinstance(structured, dict):
        err("expected_structured_output", "must be a JSON object")

    if expected_output is None:
        warn(
            "expected_output",
            "not provided; exact-match metrics will be unavailable for this case",
        )
    if application_type == ApplicationType.RAG and relevant_doc_ids is None:
        warn(
            "relevant_doc_ids",
            "not labeled for a RAG case; retrieval metrics will be unavailable",
        )

    is_security = bool(row.get("is_security_case")) or any(
        row.get(k) for k in SECURITY_MARKER_FIELDS
    )
    case: dict[str, Any] = {
        "external_id": external_id,
        "input": {"input": str(input_value)} if input_value is not None else {},
        "expected_output": expected_output,
        "reference_context": reference_context,
        "relevant_doc_ids": relevant_doc_ids,
        "expected_tool": expected_tool,
        "expected_action_sequence": action_seq if isinstance(action_seq, list) else None,
        "expected_structured_output": structured if isinstance(structured, dict) else None,
        "category": _field_str(row, "category"),
        "tags": row.get("tags") if isinstance(row.get("tags"), list) else [],
        "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
        "is_security_case": is_security,
    }
    return case, errors, warnings


def _file_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_upload(
    content: bytes, filename: str, application_type: ApplicationType
) -> tuple[
        list[tuple[dict[str, Any], list[ValidationIssue], list[ValidationIssue]]],
        ValidationReport,
    ]:
    """Parse + validate without persisting. Returns per-row tuples and report."""
    rows = parse_rows(content, filename)
    settings = get_settings()
    if len(rows) > settings.max_dataset_rows:
        raise DatasetError(422, f"dataset exceeds the maximum of {settings.max_dataset_rows} rows")
    per_row = [validate_row(row, application_type, pos) for pos, row in enumerate(rows, start=1)]
    error_rows = {issue.row for _, errs, _ in per_row for issue in errs}
    report = ValidationReport(
        total_rows=len(rows),
        valid_rows=len(rows) - len(error_rows),
        invalid_rows=len(error_rows),
        issues=[issue for _, errs, _ in per_row for issue in errs],
        warnings=[issue for _, _, warns in per_row for issue in warns],
    )
    return per_row, report


def _get_or_create_dataset(
    session: Session,
    name: str,
    description: str,
    application_type: ApplicationType,
    owner: str | None,
) -> Dataset:
    dataset = session.scalar(select(Dataset).where(Dataset.name == name))
    if dataset is None:
        dataset = Dataset(
            name=name, description=description, application_type=application_type, owner=owner
        )
        session.add(dataset)
        session.flush()
    return dataset


def create_version(
    session: Session,
    dataset: Dataset,
    content: bytes,
    per_row: list[tuple[dict[str, Any], list[ValidationIssue], list[ValidationIssue]]],
    created_by: str | None,
) -> tuple[DatasetVersion, bool]:
    """Persist a new immutable version, or return the existing identical one."""
    content_hash = _file_content_hash(content)
    existing = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset.id,
            DatasetVersion.content_hash == content_hash,
        )
    )
    if existing is not None:
        return existing, False  # immutable dedupe: reuse identical version

    storage_key, _ = local_store.store_bytes(content)
    errors_by_row: dict[int, list[ValidationIssue]] = {}
    for _, errs, _ in per_row:
        for issue in errs:
            errors_by_row.setdefault(issue.row, []).append(issue)

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=max((v.version_number for v in dataset.versions), default=0) + 1,
        content_hash=content_hash,
        file_storage_key=storage_key,
        case_count=len(per_row),
        valid_case_count=len(per_row) - len(errors_by_row),
        invalid_case_count=len(errors_by_row),
        created_by=created_by,
    )
    session.add(version)
    session.flush()
    for position, (case, _errs, _warns) in enumerate(per_row, start=1):
        session.add(
            TestCase(
                dataset_version_id=version.id,
                position=position,
                status=CaseStatus.INVALID if position in errors_by_row else CaseStatus.VALID,
                validation_errors=[issue.model_dump() for issue in errors_by_row.get(position, [])],
                application_type=dataset.application_type,
                **case,
            )
        )
    session.flush()
    return version, True


async def ingest_upload(
    session: Session,
    file: UploadFile,
    name: str,
    application_type: ApplicationType,
    description: str = "",
    dry_run: bool = False,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Full upload flow: read, parse, validate, persist version (FR-B1..B5)."""
    content = await file.read()
    settings = get_settings()
    if len(content) > settings.max_upload_bytes:
        raise DatasetError(422, f"file exceeds maximum upload size of {settings.max_upload_mb} MB")
    if not content:
        raise DatasetError(422, "uploaded file is empty")
    per_row, report = validate_upload(content, file.filename or "upload.jsonl", application_type)
    if dry_run:
        return {"validation_report": report, "dataset": None, "version": None, "reused": False}
    dataset = _get_or_create_dataset(session, name, description, application_type, created_by)
    version, reused = create_version(session, dataset, content, per_row, created_by)
    session.commit()
    session.refresh(version)
    session.refresh(dataset)
    return {"validation_report": report, "dataset": dataset, "version": version, "reused": reused}
