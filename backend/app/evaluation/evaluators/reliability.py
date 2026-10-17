"""Reliability evaluators (FR-D3; run scope)."""

from __future__ import annotations

from app.evaluation.base import CaseEvalInput, EvaluatorSpec, MetricValue, RunEvalInput
from app.evaluation.registry import register
from app.models.enums import CaseOutcome, MetricStatus, Provenance, ValueKind


def _all_repeats(cases: list[CaseEvalInput]):
    return [r for c in cases for r in c.repeats]


def _rate(
    spec: EvaluatorSpec, cases: list[CaseEvalInput], predicate, *, over_successes: bool = False
) -> MetricValue:
    """Shared fraction computation; never fabricates when inputs are missing."""
    repeats = _all_repeats(cases)
    if over_successes:
        denom_repeats = [r for r in repeats if r.outcome == CaseOutcome.SUCCESS]
    else:
        denom_repeats = repeats
    if not denom_repeats:
        reason = (
            "no successful executions recorded"
            if over_successes
            else "no case executions recorded"
        )
        return MetricValue.unavailable(spec, reason)
    hits = sum(1 for r in denom_repeats if predicate(r))
    return MetricValue(
        evaluator_id=spec.id,
        evaluator_version=spec.version,
        provenance=spec.provenance,
        value_kind=spec.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(hits / len(denom_repeats), 6),
        explanation=f"{hits} of {len(denom_repeats)} invocations",
        details={"hits": hits, "total": len(denom_repeats)},
    )


_SUCCESS_RATE = EvaluatorSpec(
    id="reliability.success_rate",
    name="Success Rate",
    description="Fraction of executed case invocations (all repeats) that succeeded.",
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.RATE,
    scope="run",
)

_ERROR_RATE = EvaluatorSpec(
    id="reliability.error_rate",
    name="Error Rate",
    description="Fraction of invocations that ended in an application error.",
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.RATE,
    scope="run",
)

_TIMEOUT_RATE = EvaluatorSpec(
    id="reliability.timeout_rate",
    name="Timeout Rate",
    description="Fraction of invocations that timed out.",
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.RATE,
    scope="run",
)

_MALFORMED_RATE = EvaluatorSpec(
    id="reliability.malformed_rate",
    name="Malformed Output Rate",
    description=(
        "Fraction of successful invocations whose output was empty or "
        "whitespace-only."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.RATE,
    scope="run",
)

_CONSISTENCY = EvaluatorSpec(
    id="reliability.consistency",
    name="Output Consistency",
    description=(
        "Fraction of multi-repeat cases whose successful outputs are identical "
        "after normalization. Unavailable unless repeats > 1 for at least one "
        "case."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.RATE,
    scope="run",
)


def _success_rate(inp: RunEvalInput) -> MetricValue:
    return _rate(_SUCCESS_RATE, inp.cases, lambda r: r.outcome == CaseOutcome.SUCCESS)


def _error_rate(inp: RunEvalInput) -> MetricValue:
    return _rate(_ERROR_RATE, inp.cases, lambda r: r.outcome == CaseOutcome.APPLICATION_ERROR)


def _timeout_rate(inp: RunEvalInput) -> MetricValue:
    return _rate(_TIMEOUT_RATE, inp.cases, lambda r: r.outcome == CaseOutcome.TIMEOUT)


def _is_malformed(r) -> bool:
    return r.outcome == CaseOutcome.SUCCESS and not (r.output or "").strip()


def _malformed_rate(inp: RunEvalInput) -> MetricValue:
    return _rate(_MALFORMED_RATE, inp.cases, _is_malformed, over_successes=True)


def _consistency(inp: RunEvalInput) -> MetricValue:
    from app.evaluation.evaluators.answer import _normalize

    multi = [c for c in inp.cases if len(c.repeats) > 1]
    eligible = [
        c
        for c in multi
        if len(c.successful_repeats()) > 1
    ]
    if not eligible:
        return MetricValue.unavailable(
            _CONSISTENCY, "no case has more than one successful repeat"
        )
    consistent = 0
    for c in eligible:
        outputs = {_normalize(r.output or "") for r in c.successful_repeats()}
        if len(outputs) == 1:
            consistent += 1
    return MetricValue(
        evaluator_id=_CONSISTENCY.id,
        evaluator_version=_CONSISTENCY.version,
        provenance=_CONSISTENCY.provenance,
        value_kind=_CONSISTENCY.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(consistent / len(eligible), 6),
        explanation=f"{consistent} of {len(eligible)} multi-repeat cases fully consistent",
        details={"consistent": consistent, "cases": len(eligible)},
    )


register(_SUCCESS_RATE, _success_rate)
register(_ERROR_RATE, _error_rate)
register(_TIMEOUT_RATE, _timeout_rate)
register(_MALFORMED_RATE, _malformed_rate)
register(_CONSISTENCY, _consistency)
