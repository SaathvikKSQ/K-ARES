"""Cost evaluators (FR-D6; run scope) built on the versioned pricing table."""

from __future__ import annotations

from app.evaluation.base import CaseEvalInput, EvaluatorSpec, MetricValue, RunEvalInput
from app.evaluation.pricing import PRICING_VERSION, estimate_cost
from app.evaluation.registry import register
from app.models.enums import CaseOutcome, MetricStatus, Provenance, ValueKind


def _usages(cases: list[CaseEvalInput]) -> list[dict]:
    return [
        r.token_usage
        for c in cases
        for r in c.repeats
        if r.outcome == CaseOutcome.SUCCESS and r.token_usage
    ]


def _unavailable(spec: EvaluatorSpec, reason: str) -> MetricValue:
    return MetricValue.unavailable(spec, reason)


def _estimate_total(
    spec: EvaluatorSpec, inp: RunEvalInput
) -> tuple[MetricValue | None, float | None, int | None]:
    """Shared cost computation.

    Returns (unavailable_metric, total_usd, usage_count); ``total_usd`` is
    not None only when every estimate is computable.
    """
    usages = _usages(inp.cases)
    model = inp.run_meta.get("model_name")
    if not usages:
        return _unavailable(spec, "application did not report token usage"), None, None
    estimates = [
        estimate_cost(model, u.get("input", 0), u.get("output", 0)) for u in usages
    ]
    blocked = next((e for e in estimates if e.status != MetricStatus.COMPUTED), None)
    if blocked is not None:
        return _unavailable(spec, blocked.reason or "cost estimate unavailable"), None, None
    total = round(sum(e.amount_usd or 0.0 for e in estimates), 6)
    return None, total, len(estimates)


_COST_TOTAL = EvaluatorSpec(
    id="cost.estimated_total",
    name="Estimated Cost (total)",
    description=(
        "Estimated USD cost of all successful invocations, based on reported "
        "token usage and the versioned pricing table. Estimates only."
    ),
    version="1.0.0",
    provenance=Provenance.ESTIMATED,
    value_kind=ValueKind.CURRENCY,
    scope="run",
)


def _cost_total(inp: RunEvalInput) -> MetricValue:
    blocked, total, count = _estimate_total(_COST_TOTAL, inp)
    if blocked is not None:
        return blocked
    assert total is not None and count is not None
    return MetricValue(
        evaluator_id=_COST_TOTAL.id,
        evaluator_version=_COST_TOTAL.version,
        provenance=_COST_TOTAL.provenance,
        value_kind=_COST_TOTAL.value_kind,
        status=MetricStatus.COMPUTED,
        score=total,
        explanation=f"estimated cost of {count} successful invocations",
        details={"pricing_version": PRICING_VERSION, "currency": "USD", "usages": count},
    )


_COST_PER_CASE = EvaluatorSpec(
    id="cost.estimated_per_case",
    name="Estimated Cost (per case)",
    description="Mean estimated USD cost per successful invocation.",
    version="1.0.0",
    provenance=Provenance.ESTIMATED,
    value_kind=ValueKind.CURRENCY,
    scope="run",
)


def _cost_per_case(inp: RunEvalInput) -> MetricValue:
    blocked, total, count = _estimate_total(_COST_PER_CASE, inp)
    if blocked is not None:
        return blocked
    assert total is not None and count is not None
    return MetricValue(
        evaluator_id=_COST_PER_CASE.id,
        evaluator_version=_COST_PER_CASE.version,
        provenance=_COST_PER_CASE.provenance,
        value_kind=_COST_PER_CASE.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(total / count, 6) if count else None,
        explanation=f"mean estimated cost over {count} successful invocations",
        details={"pricing_version": PRICING_VERSION, "currency": "USD", "usages": count},
    )


register(_COST_TOTAL, _cost_total)
register(_COST_PER_CASE, _cost_per_case)
