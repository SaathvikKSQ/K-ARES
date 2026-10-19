"""Agent evaluators (T5.4, FR-D; metrics.md Ã‚Â§7).

All metrics are deterministic and case-scope. Inputs come from
``agent_trace.tool_calls[]`` ({name, args, success, duration_ms, order}) plus
dataset labels (``expected_tool``, ``expected_action_sequence``,
``expected_output``). If the target does not expose traces, agent metrics are
``unavailable`` Ã¢â‚¬â€ the platform never fabricates traces (constitution Ã‚Â§2.2).
"""

from __future__ import annotations

from typing import Any

from app.evaluation.base import CaseEvalInput, EvaluatorSpec, MetricValue
from app.evaluation.evaluators.answer import _normalize
from app.evaluation.registry import register
from app.models.enums import MetricStatus, Provenance, ValueKind


def _tool_calls(inp: CaseEvalInput) -> tuple[list[dict[str, Any]], list[int]]:
    """Tool calls per successful repeat ([], 0) when traces are absent."""
    calls_per_repeat: list[list[dict[str, Any]]] = []
    repeats_with_traces = 0
    for r in inp.successful_repeats():
        trace = r.agent_trace or {}
        calls = list(trace.get("tool_calls") or [])
        if r.agent_trace is not None:
            repeats_with_traces += 1
        calls_per_repeat.append(calls)
    return calls_per_repeat, repeats_with_traces


def _expected_tool_name(case) -> str | None:
    tool = case.expected_tool
    if isinstance(tool, dict):
        return str(tool.get("name")) if tool.get("name") else None
    if isinstance(tool, str):
        return tool
    return None


def _expected_sequence(case) -> list[str] | None:
    if case.expected_action_sequence is not None:
        return [str(a) for a in case.expected_action_sequence]
    name = _expected_tool_name(case)
    return [name] if name else None


def _lcs_ratio(expected: list[str], actual: list[str]) -> float:
    """Longest-common-subsequence length / len(expected)."""
    if not expected:
        return 0.0
    m, n = len(expected), len(actual)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if expected[i - 1] == actual[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n] / m


def _flat_calls(calls_per_repeat):
    """Flatten per-repeat call lists with repeat index attached."""
    flat: list[tuple[int, dict[str, Any]]] = []
    for idx, calls in enumerate(calls_per_repeat):
        for call in calls:
            flat.append((idx, call))
    return flat


def _agent_spec(metric: str, name: str, description: str, value_kind: ValueKind) -> EvaluatorSpec:
    return EvaluatorSpec(
        id=metric,
        name=name,
        description=description,
        version="1.0.0",
        provenance=Provenance.MEASURED,
        value_kind=value_kind,
        scope="case",
        application_types=("agent",),
        capabilities_required=("exposes_traces",),
    )


_TASK_COMPLETION = _agent_spec(
    "agent.task_completion",
    "Task Completion",
    "Fraction of successful repeats whose completion criteria are met: "
    "expected output match (when labeled) and/or expected final action "
    "(last step of the expected sequence/tool). Unavailable when no "
    "completion criteria are labeled.",
    ValueKind.SCORE,
)


def _task_completion(inp: CaseEvalInput) -> MetricValue:
    case = inp.case
    has_output_label = case.expected_output is not None
    expected_seq = _expected_sequence(case)
    if not has_output_label and not expected_seq:
        return MetricValue.unavailable(
            _TASK_COMPLETION, "no completion criteria labeled (expected_output / expected_tool)"
        )
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_TASK_COMPLETION, "case execution did not succeed")
    calls_per_repeat, with_traces = _tool_calls(inp)
    if with_traces == 0 and expected_seq:
        return MetricValue.unavailable(_TASK_COMPLETION, "application did not expose agent traces")
    met = 0
    per_repeat = []
    reasons: list[str] = []
    for r, calls in zip(successes, calls_per_repeat, strict=False):
        matched_output = (
            has_output_label and _normalize(r.output or "") == _normalize(case.expected_output)
        )
        final_action = calls[-1].get("name") if calls else None
        expected_final = expected_seq[-1] if expected_seq else None
        matched_action = (
            expected_final is not None and final_action == expected_final
        )
        ok = matched_output or matched_action
        met += ok
        per_repeat.append(ok)
        reasons.append(
            f"output_match={matched_output}, final_action_match={matched_action}"
        )
    return MetricValue(
        evaluator_id=_TASK_COMPLETION.id,
        evaluator_version=_TASK_COMPLETION.version,
        provenance=_TASK_COMPLETION.provenance,
        value_kind=_TASK_COMPLETION.value_kind,
        status=MetricStatus.COMPUTED,
        score=met / len(successes),
        explanation=f"{met} of {len(successes)} successful repeats met completion criteria",
        details={
            "per_repeat": per_repeat,
            "criteria": reasons,
        },
    )


_TOOL_SELECTION = _agent_spec(
    "agent.tool_selection_accuracy",
    "Tool Selection Accuracy",
    "Whether the expected tool appears within the first `position_tolerance` "
    "tool calls (config: position_tolerance, default 1). Unavailable when "
    "expected_tool is not labeled.",
    ValueKind.SCORE,
)


def _tool_selection(inp: CaseEvalInput) -> MetricValue:
    expected = _expected_tool_name(inp.case)
    if expected is None:
        return MetricValue.unavailable(
            _TOOL_SELECTION, "case has no expected_tool label"
        )
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_TOOL_SELECTION, "case execution did not succeed")
    calls_per_repeat, with_traces = _tool_calls(inp)
    if with_traces == 0:
        return MetricValue.unavailable(_TOOL_SELECTION, "application did not expose agent traces")
    try:
        tolerance = max(1, int(inp.config.get("position_tolerance", 1)))
    except (TypeError, ValueError):
        tolerance = 1
    hits = 0
    per_repeat = []
    for calls in calls_per_repeat:
        names = [str(c.get("name", "")) for c in calls[:tolerance]]
        hit = expected in names
        hits += hit
        per_repeat.append(hit)
    return MetricValue(
        evaluator_id=_TOOL_SELECTION.id,
        evaluator_version=_TOOL_SELECTION.version,
        provenance=_TOOL_SELECTION.provenance,
        value_kind=_TOOL_SELECTION.value_kind,
        status=MetricStatus.COMPUTED,
        score=hits / len(successes),
        explanation=(
            f"expected tool '{expected}' within first {tolerance} call(s) "
            f"in {hits} of {len(successes)} repeat(s)"
        ),
        details={
            "expected_tool": expected,
            "position_tolerance": tolerance,
            "per_repeat": per_repeat,
        },
    )


_SUCCESS_RATE = _agent_spec(
    "agent.tool_call_success_rate",
    "Tool Call Success Rate",
    "Fraction of reported tool calls that succeeded. Unavailable when no "
    "tool calls were reported.",
    ValueKind.RATE,
)


def _tool_success_rate(inp: CaseEvalInput) -> MetricValue:
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_SUCCESS_RATE, "case execution did not succeed")
    calls_per_repeat = _tool_calls(inp)[0]
    flat = _flat_calls(calls_per_repeat)
    if not flat:
        return MetricValue.unavailable(_SUCCESS_RATE, "no tool calls reported for this case")
    succeeded = sum(1 for _, c in flat if c.get("success") is True)
    total = len(flat)
    return MetricValue(
        evaluator_id=_SUCCESS_RATE.id,
        evaluator_version=_SUCCESS_RATE.version,
        provenance=_SUCCESS_RATE.provenance,
        value_kind=_SUCCESS_RATE.value_kind,
        status=MetricStatus.COMPUTED,
        score=succeeded / total,
        explanation=f"{succeeded} of {total} reported tool calls succeeded",
        details={"succeeded": succeeded, "total": total},
    )


_INVALID_CALLS = EvaluatorSpec(
    id="agent.invalid_tool_calls",
    name="Invalid Tool Calls",
    description=(
        "Count of tool calls outside the allowed tool set (expected tool plus "
        "the configured 'tool_allowlist'). Value is a count; 0 is the healthy "
        "case. Unavailable without traces."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.COUNT,
    scope="case",
    application_types=("agent",),
    capabilities_required=("exposes_traces",),
    config_schema={"tool_allowlist": {"type": "array", "required": False}},
)


def _invalid_calls(inp: CaseEvalInput) -> MetricValue:
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_INVALID_CALLS, "case execution did not succeed")
    calls_per_repeat, with_traces = _tool_calls(inp)
    if with_traces == 0:
        return MetricValue.unavailable(_INVALID_CALLS, "application did not expose agent traces")
    allowed = {_expected_tool_name(inp.case) or ""}
    allowlist = inp.config.get("tool_allowlist") or []
    if isinstance(allowlist, (list, tuple, set)):
        allowed |= {str(t) for t in allowlist}
    flat = _flat_calls(calls_per_repeat)
    invalid = [
        {"name": str(c.get("name", "")), "repeat_index": idx}
        for idx, c in flat
        if str(c.get("name", "")) not in allowed
    ]
    return MetricValue(
        evaluator_id=_INVALID_CALLS.id,
        evaluator_version=_INVALID_CALLS.version,
        provenance=_INVALID_CALLS.provenance,
        value_kind=_INVALID_CALLS.value_kind,
        status=MetricStatus.COMPUTED,
        score=float(len(invalid)),
        explanation=(
            f"{len(invalid)} call(s) outside the allowed tool set "
            f"({len(flat)} total)"
        ),
        details={
            "invalid": invalid,
            "total_calls": len(flat),
            "allowed_tools": sorted(allowed - {""}),
        },
    )


_UNNECESSARY_CALLS = EvaluatorSpec(
    id="agent.unnecessary_tool_calls",
    name="Unnecessary Tool Calls",
    description=(
        "Count of tool calls not in the expected sequence and not flagged "
        "exploratory. With config allow_exploratory=true (default), unexpected "
        "calls are treated as exploratory and only explicitly flagged "
        "non-exploratory calls (exploratory=false) count. Details always "
        "report both counts."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.COUNT,
    scope="case",
    application_types=("agent",),
    capabilities_required=("exposes_traces",),
    config_schema={"allow_exploratory": {"type": "boolean", "required": False}},
)


def _unnecessary_calls(inp: CaseEvalInput) -> MetricValue:
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_UNNECESSARY_CALLS, "case execution did not succeed")
    calls_per_repeat, with_traces = _tool_calls(inp)
    if with_traces == 0:
        return MetricValue.unavailable(
            _UNNECESSARY_CALLS, "application did not expose agent traces"
        )
    expected_seq = _expected_sequence(inp.case)
    if expected_seq is None:
        return MetricValue.unavailable(
            _UNNECESSARY_CALLS, "no expected action sequence or tool labeled"
        )
    expected = set(expected_seq)
    allow_exploratory = bool(inp.config.get("allow_exploratory", True))
    flat = _flat_calls(calls_per_repeat)
    unexpected = []
    for idx, c in flat:
        name = str(c.get("name", ""))
        if name in expected:
            continue
        unexpected.append(
            {"name": name, "repeat_index": idx, "exploratory": c.get("exploratory")}
        )
    counted = (
        [u for u in unexpected if u["exploratory"] is False]
        if allow_exploratory
        else unexpected
    )
    return MetricValue(
        evaluator_id=_UNNECESSARY_CALLS.id,
        evaluator_version=_UNNECESSARY_CALLS.version,
        provenance=_UNNECESSARY_CALLS.provenance,
        value_kind=_UNNECESSARY_CALLS.value_kind,
        status=MetricStatus.COMPUTED,
        score=float(len(counted)),
        explanation=(
            f"{len(counted)} unnecessary call(s) ({len(unexpected)} outside the "
            f"expected sequence)"
        ),
        details={
            "unexpected": unexpected,
            "counted": counted,
            "allow_exploratory": allow_exploratory,
        },
    )


_SEQUENCE_MATCH = EvaluatorSpec(
    id="agent.action_sequence_match",
    name="Action Sequence Match",
    description=(
        "Longest-common-subsequence ratio between the expected action "
        "sequence and the actual tool-call sequence. Unavailable without "
        "expected_action_sequence labels."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.SCORE,
    scope="case",
    application_types=("agent",),
    capabilities_required=("exposes_traces",),
)


def _sequence_match(inp: CaseEvalInput) -> MetricValue:
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_SEQUENCE_MATCH, "case execution did not succeed")
    calls_per_repeat, with_traces = _tool_calls(inp)
    if with_traces == 0:
        return MetricValue.unavailable(_SEQUENCE_MATCH, "application did not expose agent traces")
    if inp.case.expected_action_sequence is None:
        return MetricValue.unavailable(
            _SEQUENCE_MATCH, "case has no expected_action_sequence label"
        )
    expected_seq = [str(a) for a in inp.case.expected_action_sequence]
    scores = []
    for calls in calls_per_repeat:
        actual = [str(c.get("name", "")) for c in calls]
        scores.append(_lcs_ratio(expected_seq, actual))
    return MetricValue(
        evaluator_id=_SEQUENCE_MATCH.id,
        evaluator_version=_SEQUENCE_MATCH.version,
        provenance=_SEQUENCE_MATCH.provenance,
        value_kind=_SEQUENCE_MATCH.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(sum(scores) / len(scores), 6),
        explanation=f"mean LCS ratio over {len(scores)} successful repeat(s)",
        details={
            "expected_sequence": expected_seq,
            "per_repeat": [round(s, 6) for s in scores],
        },
    )


_DURATION = EvaluatorSpec(
    id="agent.execution_duration",
    name="Agent Execution Duration",
    description="Mean wall-clock duration (ms) of successful repeats.",
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.MS,
    scope="case",
    application_types=("agent",),
)


def _duration(inp: CaseEvalInput) -> MetricValue:
    successes = inp.successful_repeats()
    latencies = [r.latency_ms for r in successes if r.latency_ms is not None]
    if not latencies:
        return MetricValue.unavailable(_DURATION, "no successful repeat reported a duration")
    return MetricValue(
        evaluator_id=_DURATION.id,
        evaluator_version=_DURATION.version,
        provenance=_DURATION.provenance,
        value_kind=_DURATION.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(sum(latencies) / len(latencies), 3),
        explanation=f"mean over {len(latencies)} successful repeat(s)",
        details={"per_repeat_ms": latencies},
    )


_CALL_COUNT = EvaluatorSpec(
    id="agent.tool_call_count",
    name="Tool Call Count",
    description="Mean number of reported tool calls per successful repeat.",
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.COUNT,
    scope="case",
    application_types=("agent",),
    capabilities_required=("exposes_traces",),
)


def _call_count(inp: CaseEvalInput) -> MetricValue:
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_CALL_COUNT, "case execution did not succeed")
    calls_per_repeat, with_traces = _tool_calls(inp)
    if with_traces == 0:
        return MetricValue.unavailable(_CALL_COUNT, "application did not expose agent traces")
    counts = [len(calls) for calls in calls_per_repeat]
    return MetricValue(
        evaluator_id=_CALL_COUNT.id,
        evaluator_version=_CALL_COUNT.version,
        provenance=_CALL_COUNT.provenance,
        value_kind=_CALL_COUNT.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(sum(counts) / len(counts), 4),
        explanation=f"mean over {len(counts)} successful repeat(s)",
        details={"per_repeat": counts},
    )


register(_TASK_COMPLETION, _task_completion)
register(_TOOL_SELECTION, _tool_selection)
register(_SUCCESS_RATE, _tool_success_rate)
register(_INVALID_CALLS, _invalid_calls)
register(_UNNECESSARY_CALLS, _unnecessary_calls)
register(_SEQUENCE_MATCH, _sequence_match)
register(_DURATION, _duration)
register(_CALL_COUNT, _call_count)
