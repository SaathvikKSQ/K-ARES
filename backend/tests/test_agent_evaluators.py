"""Phase 5: agent metrics on hand-built traces (T5.4)."""

from __future__ import annotations

from app.evaluation import registry
from app.evaluation.base import CaseData, CaseEvalInput, RepeatRecord
from app.evaluation.evaluators.agent import _lcs_ratio
from app.models.enums import CaseOutcome, MetricStatus

registry.ensure_loaded()


def _case(expected_tool=None, sequence=None, expected=None) -> CaseData:
    tool = {"name": expected_tool} if isinstance(expected_tool, str) else expected_tool
    return CaseData(
        id="case-1",
        position=1,
        case_input={"input": "do the thing"},
        expected_output=expected,
        expected_tool=tool,
        expected_action_sequence=sequence,
    )


def _repeat(calls=None, output=None, outcome=CaseOutcome.SUCCESS, latency=100) -> RepeatRecord:
    return RepeatRecord(
        repeat_index=0,
        outcome=outcome,
        output=output,
        latency_ms=latency,
        agent_trace={"tool_calls": calls or []},
    )


def _value(metric_id, case, repeats, config=None):
    _, fn = registry.get(metric_id)
    return fn(CaseEvalInput(case=case, repeats=repeats, config=config or {}))


def _call(name, success=True, **extra):
    return {"name": name, "args": {}, "success": success, "order": 1, **extra}


def test_lcs_ratio_hand_computed():
    assert _lcs_ratio(["a", "b", "c"], ["a", "x", "b", "c"]) == 1.0
    assert _lcs_ratio(["a", "b", "c"], ["c", "a"]) == 1 / 3


def test_task_completion_via_output():
    value = _value(
        "agent.task_completion",
        _case(expected_tool="search", expected="done"),
        [_repeat(output="Done", calls=[_call("search")])],
    )
    assert value.score == 1.0


def test_task_completion_via_final_action():
    value = _value(
        "agent.task_completion",
        _case(expected_tool="create_ticket"),
        [_repeat(output="whatever", calls=[_call("search"), _call("create_ticket")])],
    )
    assert value.score == 1.0


def test_task_completion_unavailable_without_labels():
    value = _value("agent.task_completion", _case(), [_repeat(output="x")])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "completion criteria" in value.unavailable_reason


def test_tool_selection_within_tolerance():
    case = _case(expected_tool="search")
    hit = _value("agent.tool_selection_accuracy", case, [_repeat(calls=[_call("search")])])
    assert hit.score == 1.0
    miss_default = _value(
        "agent.tool_selection_accuracy",
        case,
        [_repeat(calls=[_call("browse"), _call("search")])],
    )
    assert miss_default.score == 0.0  # tolerance 1: search not first
    miss_tolerant = _value(
        "agent.tool_selection_accuracy",
        case,
        [_repeat(calls=[_call("browse"), _call("search")])],
        config={"position_tolerance": 2},
    )
    assert miss_tolerant.score == 1.0


def test_tool_selection_unavailable_without_label():
    value = _value("agent.tool_selection_accuracy", _case(), [_repeat(calls=[_call("x")])])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "expected_tool" in value.unavailable_reason


def test_tool_call_success_rate():
    case = _case(expected_tool="a")
    value = _value(
        "agent.tool_call_success_rate",
        case,
        [_repeat(calls=[_call("a", success=True), _call("b", success=False)])],
    )
    assert value.score == 0.5
    assert value.details["total"] == 2


def test_tool_call_success_rate_unavailable_without_calls():
    value = _value("agent.tool_call_success_rate", _case(), [_repeat(calls=[])])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "no tool calls" in value.unavailable_reason


def test_invalid_tool_calls_with_allowlist():
    case = _case(expected_tool="search")
    value = _value(
        "agent.invalid_tool_calls",
        case,
        [_repeat(calls=[_call("search"), _call("rm_rf"), _call("grant_admin")])],
        config={"tool_allowlist": ["grant_admin"]},
    )
    assert value.status == MetricStatus.COMPUTED
    assert value.score == 1.0  # only rm_rf is outside expected + allowlist
    assert value.details["invalid"][0]["name"] == "rm_rf"


def test_unnecessary_calls_respect_exploratory_flag():
    case = _case(expected_tool="search")
    calls = [_call("search"), _call("browse", exploratory=True), _call("blast", exploratory=False)]
    permissive = _value("agent.unnecessary_tool_calls", case, [_repeat(calls=calls)])
    assert permissive.score == 1.0  # default: only flagged non-exploratory count
    strict = _value(
        "agent.unnecessary_tool_calls",
        case,
        [_repeat(calls=calls)],
        config={"allow_exploratory": False},
    )
    assert strict.score == 2.0


def test_action_sequence_match_full():
    case = _case(sequence=["search_issue", "create_issue"])
    value = _value(
        "agent.action_sequence_match",
        case,
        [_repeat(calls=[_call("search_issue"), _call("x"), _call("create_issue")])],
    )
    assert value.score == 1.0


def test_action_sequence_match_partial():
    case = _case(sequence=["a", "b", "c", "d"])
    value = _value("agent.action_sequence_match", case, [_repeat(calls=[_call("a"), _call("c")])])
    assert abs(value.score - 0.5) < 1e-9


def test_action_sequence_match_unavailable_without_labels():
    value = _value("agent.action_sequence_match", _case(), [_repeat(calls=[_call("a")])])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "expected_action_sequence" in value.unavailable_reason


def test_duration_and_call_count():
    case = _case(expected_tool="a")
    duration = _value(
        "agent.execution_duration",
        case,
        [_repeat(latency=120), _repeat(latency=80)],
    )
    assert duration.score == 100.0
    count = _value(
        "agent.tool_call_count",
        case,
        [_repeat(calls=[_call("a"), _call("b")]), _repeat(calls=[])],
    )
    assert count.score == 1.0


def test_metrics_unavailable_when_traces_not_exposed():
    case = _case(expected_tool="a")
    repeat = RepeatRecord(repeat_index=0, outcome=CaseOutcome.SUCCESS, output="x")
    for metric in (
        "agent.tool_selection_accuracy",
        "agent.invalid_tool_calls",
        "agent.action_sequence_match",
        "agent.tool_call_count",
    ):
        value = _value(metric, case, [repeat])
        assert value.status == MetricStatus.UNAVAILABLE, metric
        assert "traces" in value.unavailable_reason

