"""Performance evaluators (FR-D4; run scope)."""

from __future__ import annotations

import math

from app.evaluation.base import CaseEvalInput, EvaluatorSpec, MetricValue, RunEvalInput
from app.evaluation.registry import register
from app.models.enums import CaseOutcome, MetricStatus, Provenance, ValueKind


def _percentile(sorted_values: list[int], q: float) -> int:
    """Nearest-rank percentile on a pre-sorted list."""
    if not sorted_values:
        return 0
    idx = max(0, math.ceil(q / 100 * len(sorted_values)) - 1)
    return sorted_values[min(idx, len(sorted_values) - 1)]


def _successful_latencies(cases: list[CaseEvalInput]) -> list[int]:
    return [
        r.latency_ms
        for c in cases
        for r in c.repeats
        if r.outcome == CaseOutcome.SUCCESS and r.latency_ms is not None
    ]


_LATENCY = EvaluatorSpec(
    id="performance.latency",
    name="Latency",
    description=(
        "Mean end-to-end latency of successful invocations, with p50/p95 "
        "min/max breakdown in details."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.MS,
    scope="run",
)


def _latency(inp: RunEvalInput) -> MetricValue:
    latencies = _successful_latencies(inp.cases)
    if not latencies:
        return MetricValue.unavailable(_LATENCY, "no successful executions with latency data")
    ordered = sorted(latencies)
    mean = round(sum(ordered) / len(ordered), 3)
    return MetricValue(
        evaluator_id=_LATENCY.id,
        evaluator_version=_LATENCY.version,
        provenance=_LATENCY.provenance,
        value_kind=_LATENCY.value_kind,
        status=MetricStatus.COMPUTED,
        score=mean,
        explanation=f"mean latency over {len(ordered)} successful invocations",
        details={
            "count": len(ordered),
            "min": ordered[0],
            "p50": _percentile(ordered, 50),
            "p95": _percentile(ordered, 95),
            "max": ordered[-1],
        },
    )


_THROUGHPUT = EvaluatorSpec(
    id="performance.throughput",
    name="Throughput",
    description="Completed case executions per second of run wall time.",
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.RATE,
    scope="run",
)


def _throughput(inp: RunEvalInput) -> MetricValue:
    duration_ms = inp.run_meta.get("duration_ms")
    if not duration_ms:
        return MetricValue.unavailable(_THROUGHPUT, "run duration not recorded")
    completed = sum(
        1
        for r in (r for c in inp.cases for r in c.repeats)
        if r.outcome != CaseOutcome.SKIPPED
    )
    seconds = duration_ms / 1000
    return MetricValue(
        evaluator_id=_THROUGHPUT.id,
        evaluator_version=_THROUGHPUT.version,
        provenance=_THROUGHPUT.provenance,
        value_kind=_THROUGHPUT.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(completed / seconds, 6) if seconds > 0 else None,
        explanation=f"{completed} executions in {round(seconds, 3)} s",
        details={"completed": completed, "duration_ms": duration_ms},
    )


_TOKEN_USAGE = EvaluatorSpec(
    id="performance.token_usage",
    name="Token Usage",
    description=(
        "Mean total tokens (input + output) per successful invocation; "
        "unavailable when the application does not report token usage."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.TOKENS,
    scope="run",
    capabilities_required=("exposes_token_usage",),
)


def _token_usage(inp: RunEvalInput) -> MetricValue:
    usages = [
        r.token_usage
        for c in inp.cases
        for r in c.repeats
        if r.outcome == CaseOutcome.SUCCESS and r.token_usage
    ]
    if not usages:
        return MetricValue.unavailable(
            _TOKEN_USAGE, "application did not report token usage"
        )
    inputs = sum(u.get("input", 0) for u in usages)
    outputs = sum(u.get("output", 0) for u in usages)
    totals = [u.get("input", 0) + u.get("output", 0) for u in usages]
    return MetricValue(
        evaluator_id=_TOKEN_USAGE.id,
        evaluator_version=_TOKEN_USAGE.version,
        provenance=_TOKEN_USAGE.provenance,
        value_kind=_TOKEN_USAGE.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(sum(totals) / len(totals), 3),
        explanation=f"mean total tokens over {len(usages)} successful invocations",
        details={
            "input_total": inputs,
            "output_total": outputs,
            "count": len(usages),
        },
    )


register(_LATENCY, _latency)
register(_THROUGHPUT, _throughput)
register(_TOKEN_USAGE, _token_usage)
