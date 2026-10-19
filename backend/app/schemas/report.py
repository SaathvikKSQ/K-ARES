"""Report schemas: run comparison (FR-F3), overview dashboard (FR-G1)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    baseline_run_id: str
    candidate_run_id: str


class MetricDelta(BaseModel):
    evaluator_id: str
    baseline: float | None = None
    candidate: float | None = None
    delta: float | None = None
    regression: bool | None = None
    provenance: str
    value_kind: str
    unavailable_reason: str | None = None


class LatencyDelta(BaseModel):
    baseline_mean_ms: float | None = None
    candidate_mean_ms: float | None = None
    delta_ms: float | None = None
    baseline_p95_ms: int | None = None
    candidate_p95_ms: int | None = None


class CostDelta(BaseModel):
    baseline_total_usd: float | None = None
    candidate_total_usd: float | None = None
    delta_usd: float | None = None
    unavailable_reason: str | None = None


class CompareOut(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    dataset_compatible: bool
    metric_deltas: list[MetricDelta] = Field(default_factory=list)
    newly_failing_case_ids: list[str] = Field(default_factory=list)
    resolved_case_ids: list[str] = Field(default_factory=list)
    latency_delta: LatencyDelta | None = None
    cost_delta: CostDelta | None = None
    baseline: dict
    candidate: dict


class RunStatusCount(BaseModel):
    status: str
    count: int


class RecentFailure(BaseModel):
    result_id: str
    run_id: str
    external_id: str | None = None
    outcome: str
    error_type: str | None = None
    error_message: str | None = None
    created_at: str | None = None


class KeyMetricSummary(BaseModel):
    run_id: str
    application_name: str | None = None
    completed_at: str | None = None
    success_rate: float | None = None
    latency_mean_ms: float | None = None
    total_cost_usd: float | None = None
    success_rate_status: str = "unavailable"
    latency_status: str = "unavailable"
    cost_status: str = "unavailable"


class OverviewOut(BaseModel):
    totals: dict
    status_breakdown: list[RunStatusCount]
    recent_runs: list[dict]
    key_metrics: list[KeyMetricSummary]
    recent_failures: list[RecentFailure]
