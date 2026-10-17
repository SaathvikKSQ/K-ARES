"""Dataset endpoints: upload, validate, list, versions, cases, samples.

FR-B1..B6, FR-G. Mutations require editor/admin; reads require auth only.
Uploads are multipart/form-data; validation errors are reported row by row.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, EditorUser
from app.models.dataset import Dataset, DatasetVersion, TestCase
from app.models.enums import ApplicationType, CaseStatus
from app.schemas.dataset import (
    DatasetOut,
    DatasetVersionDetail,
    DatasetVersionOut,
    TestCaseOut,
    ValidationReport,
)
from app.services import dataset_service as svc
from app.services import sample_datasets

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _dataset_out(dataset: Dataset) -> DatasetOut:
    out = DatasetOut.model_validate(dataset)
    out.version_count = len(dataset.versions)
    return out


def _get_dataset(session: Session, dataset_id: str) -> Dataset:
    try:
        pk = uuid.UUID(str(dataset_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    dataset = session.get(Dataset, pk)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


def _get_version(session: Session, dataset: Dataset, version_number: int) -> DatasetVersion:
    version = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset.id,
            DatasetVersion.version_number == version_number,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    return version


def _version_detail(version: DatasetVersion) -> DatasetVersionDetail:
    issues = [issue for case in version.cases for issue in (case.validation_errors or [])]
    report = ValidationReport(
        total_rows=version.case_count,
        valid_rows=version.valid_case_count,
        invalid_rows=version.invalid_case_count,
        issues=[svc.ValidationIssue(**issue) for issue in issues],
    )
    return DatasetVersionDetail(
        dataset=_dataset_out(version.dataset),
        version=DatasetVersionOut.model_validate(version),
        validation_report=report,
    )


@router.post("/validate", response_model=ValidationReport)
async def validate_dataset(
    session: DbSession,
    user: EditorUser,
    file: Annotated[UploadFile, File()],
    application_type: Annotated[ApplicationType, Form()],
) -> ValidationReport:
    """Dry-run validation of an uploaded dataset file (FR-B2)."""
    result = await svc.ingest_upload(
        session, file, name="__dry_run__",
        application_type=application_type, dry_run=True,
    )
    return result["validation_report"]



@router.post("", response_model=DatasetVersionDetail, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    session: DbSession,
    user: EditorUser,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form(min_length=1, max_length=200)],
    application_type: Annotated[ApplicationType, Form()],
    description: Annotated[str, Form()] = "",
) -> DatasetVersionDetail:
    """Upload + validate + version a dataset. Identical content reuses the version."""
    result = await svc.ingest_upload(
        session, file, name=name, application_type=application_type,
        description=description, created_by=user.email,
    )
    return _version_detail(result["version"])


@router.get("", response_model=list[DatasetOut])
def list_datasets(session: DbSession, user: CurrentUser) -> list[DatasetOut]:
    return [_dataset_out(d) for d in session.scalars(select(Dataset).order_by(Dataset.name))]


@router.get("/samples", response_model=list[dict])
def list_samples(user: CurrentUser) -> list[dict]:
    """Metadata for the bundled sample datasets."""
    return sample_datasets.sample_catalog()


@router.post("/samples/install", response_model=list[DatasetVersionDetail])
def install_samples(session: DbSession, user: EditorUser) -> list[DatasetVersionDetail]:
    """Install (or idempotently re-install) all bundled sample datasets."""
    installed = []
    for sample in sample_datasets.iter_samples():
        result = sample_datasets.ingest_sample(session, sample, created_by=user.email)
        installed.append(_version_detail(result["version"]))
    session.commit()
    return installed


@router.get("/{dataset_id}", response_model=DatasetVersionDetail)
def get_dataset_latest(
    dataset_id: str, session: DbSession, user: CurrentUser,
    version_number: int | None = None,
) -> DatasetVersionDetail:
    dataset = _get_dataset(session, dataset_id)
    version = (
        _get_version(session, dataset, version_number)
        if version_number is not None
        else max(dataset.versions, key=lambda v: v.version_number)
    )
    return _version_detail(version)


@router.get("/{dataset_id}/versions/{version_number}/cases", response_model=list[TestCaseOut])
def list_cases(
    dataset_id: str,
    version_number: int,
    session: DbSession,
    user: CurrentUser,
    case_status: Annotated[CaseStatus | None, Query()] = None,
    category: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TestCaseOut]:
    """Paginated case preview with status/category filters (FR-B6)."""
    dataset = _get_dataset(session, dataset_id)
    version = _get_version(session, dataset, version_number)
    stmt = (
        select(TestCase)
        .where(TestCase.dataset_version_id == version.id)
        .order_by(TestCase.position)
        .offset(offset)
    )
    if case_status is not None:
        stmt = stmt.where(TestCase.status == case_status)
    if category is not None:
        stmt = stmt.where(TestCase.category == category)
    return [TestCaseOut.model_validate(case) for case in session.scalars(stmt)]
