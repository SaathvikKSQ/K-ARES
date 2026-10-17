"""Phase 3: core evaluators with hand-computed fixture values (FR-D)."""

from __future__ import annotations

from app.evaluation import registry
from app.evaluation.base import (
    CaseData,
    CaseEvalInput,
    RepeatRecord,
    RunEvalInput,
)
from app.evaluation.evaluators.answer import token_f1
from app.evaluation.evaluators.cost import _usages
from app.evaluation.pricing import PRICING_VERSION
from app.models.enums import CaseOutcome, MetricStatus, Provenance


def _case(expected=None, doc_ids=None) -> CaseData:
    return CaseData(
        id="case-1",
        position=1,
        case_input={"input": "question"},
        expected_output=expected,
        relevant_doc_ids=doc_ids,
    )


def _repeat(
    i=0,
    outcome=CaseOutcome.SUCCESS,
    output=None,
    latency=None,
    usage=None,
) -> RepeatRecord:
    return RepeatRecord(
        repeat_index=i,
        outcome=outcome,
        output=output,
        latency_ms=latency,
        token_usage=usage,
    )


def _case_input(case, repeats) -> CaseEvalInput:
    return CaseEvalInput(case=case, repeats=repeats)


def _run_input(case_inputs, *, duration_ms=1000, model=None, config=None) -> RunEvalInput:
    return RunEvalInput(
        cases=case_inputs,
        run_config=config or {"concurrency": 2, "repeats": 1},
        run_meta={"duration_ms": duration_ms, "model_name": model},
    )


def _value(metric_id, inp):
    spec, fn = registry.get(metric_id)
    return fn(inp)


# --- answer.* ------------------------------------------------------------


def test_token_f1_helper_hand_computed():
    # overlap {the, cat} = 2; precision 2/3, recall 2/3 -> F1 = 2/3
    assert abs(token_f1("the cat sat", "the cat ran") - 2 / 3) < 1e-9


def test_token_f1_no_overlap_is_zero():
    assert token_f1("alpha beta", "gamma delta") == 0.0


def test_exact_match_fraction_of_repeats():
    case = _case(expected="hello world")
    repeats = [
        _repeat(0, output="Hello   World"),  # matches after normalization
        _repeat(1, output="something else"),
    ]
    value = _value("answer.exact_match", _case_input(case, repeats))
    assert value.status == MetricStatus.COMPUTED
    assert value.score == 0.5
    assert value.details["matches"] == 1
    assert value.details["successful_repeats"] == 2


def test_exact_match_all_match():
    value = _value(
        "answer.exact_match",
        _case_input(_case(expected=" paris "), [_repeat(output="PARIS")]),
    )
    assert value.score == 1.0


def test_exact_match_unavailable_without_label():
    value = _value(
        "answer.exact_match", _case_input(_case(expected=None), [_repeat(output="x")])
    )
    assert value.status == MetricStatus.UNAVAILABLE
    assert "expected_output" in value.unavailable_reason


def test_exact_match_unavailable_when_execution_failed():
    value = _value(
        "answer.exact_match",
        _case_input(_case(expected="x"), [_repeat(outcome=CaseOutcome.APPLICATION_ERROR)]),
    )
    assert value.status == MetricStatus.UNAVAILABLE
    assert "did not succeed" in value.unavailable_reason


def test_token_f1_metric_mean_over_repeats():
    case = _case(expected="the cat sat")
    repeats = [
        _repeat(0, output="the cat ran"),  # F1 = 2/3
        _repeat(1, output="the cat sat"),  # F1 = 1.0
    ]
    value = _value("answer.token_f1", _case_input(case, repeats))
    assert abs(value.score - (2 / 3 + 1.0) / 2) < 1e-6


def test_correctness_is_estimated_not_model_judged():
    value = _value(
        "answer.correctness",
        _case_input(_case(expected="alpha beta"), [_repeat(output="alpha gamma")]),
    )
    assert value.status == MetricStatus.COMPUTED
    assert value.provenance == Provenance.ESTIMATED


def test_correctness_unavailable_when_judge_model_requested():
    inp = _case_input(_case(expected="x"), [_repeat(output="x")])
    inp.config = {"judge_model": "some-model"}
    value = _value("answer.correctness", inp)
    assert value.status == MetricStatus.UNAVAILABLE
    assert "judge" in value.unavailable_reason.lower()


# --- reliability.* -------------------------------------------------------


def _mixed_run():
    """4 invocations: 2 success, 1 application error, 1 timeout."""
    a = _case_input(_case(expected="x"), [_repeat(0, output="x"), _repeat(1, output="x")])
    b = _case_input(_case(expected="x"), [_repeat(0, outcome=CaseOutcome.APPLICATION_ERROR)])
    c = _case_input(_case(expected="x"), [_repeat(0, outcome=CaseOutcome.TIMEOUT)])
    return [a, b, c]


def test_reliability_success_rate():
    value = _value("reliability.success_rate", _run_input(_mixed_run()))
    assert value.score == 0.5  # 2 of 4 invocations
    assert value.details == {"hits": 2, "total": 4}


def test_reliability_error_and_timeout_rates():
    assert _value("reliability.error_rate", _run_input(_mixed_run())).score == 0.25
    assert _value("reliability.timeout_rate", _run_input(_mixed_run())).score == 0.25


def test_reliability_rates_unavailable_with_no_executions():
    value = _value("reliability.success_rate", _run_input([]))
    assert value.status == MetricStatus.UNAVAILABLE
    assert value.score is None


def test_reliability_malformed_rate_over_successes():
    cases = [
        _case_input(_case(), [_repeat(0, output="ok")]),
        _case_input(_case(), [_repeat(0, output="   ")]),
        _case_input(_case(), [_repeat(0, output="")]),
    ]
    value = _value("reliability.malformed_rate", _run_input(cases))
    assert abs(value.score - 2 / 3) < 1e-6
    assert value.details["total"] == 3  # denominator = successful only


def test_reliability_consistency_with_two_cases():
    consistent = _case_input(_case(), [_repeat(0, output="same"), _repeat(1, output="SAME")])
    divergent = _case_input(_case(), [_repeat(0, output="a"), _repeat(1, output="b")])
    value = _value("reliability.consistency", _run_input([consistent, divergent]))
    assert value.score == 0.5


def test_reliability_consistency_unavailable_without_repeats():
    single = _case_input(_case(), [_repeat(0, output="x")])
    value = _value("reliability.consistency", _run_input([single]))
    assert value.status == MetricStatus.UNAVAILABLE


# --- performance.* -------------------------------------------------------


def test_latency_aggregates_with_percentiles():
    cases = [
        _case_input(_case(), [_repeat(0, output="x", latency=ms)])
        for ms in (400, 100, 300, 200)
    ]
    value = _value("performance.latency", _run_input(cases))
    assert value.value_kind == "ms"
    assert value.score == 250.0  # mean(100, 200, 300, 400)
    assert value.details["min"] == 100
    assert value.details["p50"] == 200  # nearest-rank
    assert value.details["p95"] == 400
    assert value.details["max"] == 400


def test_latency_unavailable_without_successes():
    value = _value(
        "performance.latency",
        _run_input([_case_input(_case(), [_repeat(outcome=CaseOutcome.TIMEOUT)])]),
    )
    assert value.status == MetricStatus.UNAVAILABLE


def test_throughput_from_duration():
    cases = [_case_input(_case(), [_repeat(0, output="x")]) for _ in range(4)]
    value = _value("performance.throughput", _run_input(cases, duration_ms=2000))
    assert value.score == 2.0  # 4 executions / 2 s


def test_token_usage_mean_and_totals():
    cases = [
        _case_input(_case(), [_repeat(0, output="x", usage={"input": 10, "output": 5})]),
        _case_input(_case(), [_repeat(0, output="y", usage={"input": 20, "output": 5})]),
    ]
    value = _value("performance.token_usage", _run_input(cases))
    assert value.score == 20.0  # mean(15, 25)
    assert value.details["input_total"] == 30
    assert value.details["output_total"] == 10


def test_token_usage_unavailable_when_not_reported():
    value = _value(
        "performance.token_usage",
        _run_input([_case_input(_case(), [_repeat(0, output="x", usage=None)])]),
    )
    assert value.status == MetricStatus.UNAVAILABLE
    assert "token usage" in value.unavailable_reason


# --- cost.* --------------------------------------------------------------


def test_cost_total_hand_computed():
    # gpt-4o: input $2.50, output $10.00 per 1M tokens
    # (1000 * 2.5 + 500 * 10) / 1e6 = 0.0075
    cases = [
        _case_input(_case(), [_repeat(0, output="x", usage={"input": 1000, "output": 500})])
    ]
    value = _value("cost.estimated_total", _run_input(cases, model="gpt-4o"))
    assert value.status == MetricStatus.COMPUTED
    assert value.provenance == Provenance.ESTIMATED
    assert abs(value.score - 0.0075) < 1e-9
    assert value.details["pricing_version"] == PRICING_VERSION


def test_cost_per_case_divides_by_usages():
    cases = [
        _case_input(_case(), [_repeat(0, output="x", usage={"input": 1000, "output": 500})]),
        _case_input(_case(), [_repeat(0, output="y", usage={"input": 1000, "output": 500})]),
    ]
    value = _value("cost.estimated_per_case", _run_input(cases, model="gpt-4o"))
    assert abs(value.score - 0.0075) < 1e-9  # mean of two identical 0.0075 usages


def test_cost_unavailable_without_model_metadata():
    cases = [
        _case_input(_case(), [_repeat(0, output="x", usage={"input": 1, "output": 1})])
    ]
    value = _value("cost.estimated_total", _run_input(cases, model=None))
    assert value.status == MetricStatus.UNAVAILABLE
    assert "model" in value.unavailable_reason


def test_cost_unavailable_with_unknown_model():
    cases = [
        _case_input(_case(), [_repeat(0, output="x", usage={"input": 1, "output": 1})])
    ]
    value = _value("cost.estimated_total", _run_input(cases, model="totally-unknown"))
    assert value.status == MetricStatus.UNAVAILABLE
    assert "no pricing entry" in value.unavailable_reason


def test_cost_unavailable_without_usage():
    cases = [_case_input(_case(), [_repeat(0, output="x")])]
    value = _value(
        "cost.estimated_total",
        _run_input(cases, model="gpt-4o"),
    )
    assert value.status == MetricStatus.UNAVAILABLE
    assert "token usage" in value.unavailable_reason


def test_usages_helper_ignores_failed_repeats():
    cases = [
        _case_input(
            _case(),
            [
                _repeat(0, output="x", usage={"input": 1, "output": 1}),
                _repeat(1, outcome=CaseOutcome.APPLICATION_ERROR, usage={"input": 9, "output": 9}),
            ],
        )
    ]
    assert _usages(cases) == [{"input": 1, "output": 1}]
