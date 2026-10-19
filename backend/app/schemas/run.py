"""Evaluation run API schemas (FR-C, FR-E, FR-F)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunConfigIn(BaseModel):
    """Runtime knobs; ranges per interface-contract.md Validation Rules."""

    concurrency: int = Field(default=4, ge=1, le=16)
    timeout_ms: int = Field(default=30000, ge=1000, le=300000)
    max_retries: int = Field(default=1, ge=0, le=3)
    repeats: int = Field(default=1, ge=1, le=5)
    rate_limit_rps: float = Field(default=0, ge=0, le=100)
    # T5.5: append the system-generated controlled security suite cases.
    include_security_suite: bool = False


class RunCreate(BaseModel):
    application_id: str
    dataset_id: str
    dataset_version_id: str | None = None
    metric_ids: list[str] = Field(min_length=1)
    run_config: RunConfigIn = Field(default_factory=RunConfigIn)


class ValidateConfigIn(BaseModel):
    application_id: str
    dataset_id: str
    dataset_version_id: str | None = None
    metric_ids: list[str] = Field(min_length=1)


class MetricSpecOut(BaseModel):
    id: str
    name: str
    description: str
    version: str
    provenance: str
    value_kind: str
    scope: str
    application_types: list[str]
    required_fields: list[str]
    capabilities_required: list[str]
    config_schema: dict[str, Any]


class InapplicableMetric(BaseModel):
    id: str
    reason: str


class ValidateConfigOut(BaseModel):
    applicable: list[str]
    inapplicable: list[InapplicableMetric]
    estimated_cases: int


class RunSummaryOut(BaseModel):
    id: str
    application_id: str
    dataset_id: str
    dataset_version_id: str
    status: str
    progress: dict[str, Any]
    metric_ids: list[str]
    triggered_by: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None


class RunDetailOut(RunSummaryOut):
    run_config: dict[str, Any]
    configuration_snapshot: dict[str, Any]
    summary_metrics: list[dict[str, Any]]
    error_summary: dict[str, Any] | None = None
    model_metadata: dict[str, Any] | None = None
    cost_summary: dict[str, Any] | None = None


class MetricValueOut(BaseModel):
    evaluator_id: str
    evaluator_version: str
    provenance: str
    value_kind: str
    status: str
    score: float | None = None
    unavailable_reason: str | None = None
    explanation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CaseResultOut(BaseModel):
    id: str
    run_id: str
    test_case_id: str
    external_id: str | None = None
    repeat_index: int
    outcome: str
    actual_output: str | None = None
    latency_ms: int | None = None
    ttft_ms: int | None = None
    token_usage: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    metrics: list[MetricValueOut] = Field(default_factory=list)


class CaseResultDetailOut(CaseResultOut):
    case_input: dict[str, Any] = Field(default_factory=dict)
    expected_output: str | None = None
    retrieved_document_ids: list[str] | None = None
    agent_trace: dict[str, Any] | None = None
    category: str | None = None


class PageOut(BaseModel):
    """Generic pagination envelope."""

    items: list[Any]
    page: int
    page_size: int
    total: int
