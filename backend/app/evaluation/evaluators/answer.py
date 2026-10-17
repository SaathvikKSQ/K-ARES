"""Answer-quality evaluators (FR-D1/D2; case scope)."""

from __future__ import annotations

import re
from collections import Counter

from app.evaluation.base import CaseEvalInput, EvaluatorSpec, MetricValue
from app.evaluation.registry import register
from app.models.enums import MetricStatus, Provenance, ValueKind

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Case-insensitive, whitespace-collapsed normalization."""
    return _WS_RE.sub(" ", text.strip().lower())


def token_f1(expected: str, actual: str) -> float:
    """Token-level F1 (bag-of-words overlap); deterministic, hand-computable."""
    exp_tokens = _normalize(expected).split()
    act_tokens = _normalize(actual).split()
    if not exp_tokens and not act_tokens:
        return 1.0
    if not exp_tokens or not act_tokens:
        return 0.0
    overlap = sum((Counter(exp_tokens) & Counter(act_tokens)).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(act_tokens)
    recall = overlap / len(exp_tokens)
    return 2 * precision * recall / (precision + recall)


_EXACT_MATCH = EvaluatorSpec(
    id="answer.exact_match",
    name="Exact Match",
    description=(
        "Fraction of successful repeats whose normalized output exactly equals "
        "the expected output. Normalization: trimmed, lowercased, "
        "whitespace-collapsed."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.SCORE,
    scope="case",
    required_fields=("expected_output",),
)


def _exact_match(inp: CaseEvalInput) -> MetricValue:
    expected = inp.case.expected_output
    if expected is None:
        return MetricValue.unavailable(_EXACT_MATCH, "case has no expected_output label")
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_EXACT_MATCH, "case execution did not succeed")
    matches = sum(1 for r in successes if _normalize(r.output or "") == _normalize(expected))
    return MetricValue(
        evaluator_id=_EXACT_MATCH.id,
        evaluator_version=_EXACT_MATCH.version,
        provenance=_EXACT_MATCH.provenance,
        value_kind=_EXACT_MATCH.value_kind,
        status=MetricStatus.COMPUTED,
        score=matches / len(successes),
        explanation=f"{matches} of {len(successes)} successful repeats matched exactly",
        details={"matches": matches, "successful_repeats": len(successes)},
    )


_TOKEN_F1 = EvaluatorSpec(
    id="answer.token_f1",
    name="Token F1",
    description=(
        "Mean token-level F1 between expected and actual output over "
        "successful repeats."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.SCORE,
    scope="case",
    required_fields=("expected_output",),
)

def _mean_token_f1(inp: CaseEvalInput, spec: EvaluatorSpec, *, heuristic: bool) -> MetricValue:
    """Shared implementation for token_f1 and the heuristic correctness metric."""
    expected = inp.case.expected_output
    if expected is None:
        return MetricValue.unavailable(spec, "case has no expected_output label")
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(spec, "case execution did not succeed")
    scores = [token_f1(expected, r.output or "") for r in successes]
    mean = round(sum(scores) / len(scores), 6)
    if heuristic:
        explanation = (
            "heuristic lexical-similarity estimate (token F1); not model-judged "
            "(LLM judge not configured in this MVP)"
        )
        details: dict = {"per_repeat": [round(s, 6) for s in scores], "judge_model": None}
    else:
        explanation = f"mean token F1 over {len(successes)} successful repeats"
        details = {"per_repeat": [round(s, 6) for s in scores]}
    return MetricValue(
        evaluator_id=spec.id,
        evaluator_version=spec.version,
        provenance=spec.provenance,
        value_kind=spec.value_kind,
        status=MetricStatus.COMPUTED,
        score=mean,
        explanation=explanation,
        details=details,
    )


def _token_f1_metric(inp: CaseEvalInput) -> MetricValue:
    return _mean_token_f1(inp, _TOKEN_F1, heuristic=False)


_CORRECTNESS = EvaluatorSpec(
    id="answer.correctness",
    name="Answer Correctness (heuristic)",
    description=(
        "Heuristic lexical-similarity estimate (token F1) of answer "
        "correctness. Provenance is 'estimated': true model-judged "
        "correctness requires an LLM judge model, not configured in this MVP. "
        "Providing config.judge_model makes this metric explicitly "
        "unavailable rather than heuristic."
    ),
    version="1.0.0",
    provenance=Provenance.ESTIMATED,
    value_kind=ValueKind.SCORE,
    scope="case",
    required_fields=("expected_output",),
    config_schema={"judge_model": {"type": "string", "required": False}},
)


def _correctness(inp: CaseEvalInput) -> MetricValue:
    if inp.config.get("judge_model"):
        return MetricValue.unavailable(
            _CORRECTNESS, "LLM-judged correctness is not implemented in this MVP"
        )
    return _mean_token_f1(inp, _CORRECTNESS, heuristic=True)


register(_EXACT_MATCH, _exact_match)
register(_TOKEN_F1, _token_f1_metric)
register(_CORRECTNESS, _correctness)
