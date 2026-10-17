"""Phase 3: engine orchestration — failure isolation, repeats, cancel (FR-C)."""

from __future__ import annotations

import asyncio

from app.evaluation.base import CaseData
from app.evaluation.engine import EvaluationEngine
from app.evaluation.ports import RunPlan
from app.integrations.base import (
    AdapterCapabilities,
    AdapterResponse,
    ConnectionTestResult,
)
from app.models.enums import CaseOutcome, MetricStatus, RunStatus


class FakeAdapter:
    """Behavior keyed by input text: 'answer' (default), 'fail', 'slow'."""

    def __init__(self, mapping=None, default="answer"):
        self._mapping = mapping or {}
        self._default = default
        self._capabilities = AdapterCapabilities(exposes_token_usage=True)

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(success=True, message="ok")

    async def invoke(self, case_input, timeout_s) -> AdapterResponse:
        action = self._mapping.get(case_input.get("input", ""), self._default)
        if action == "fail":
            raise RuntimeError("simulated application failure")
        if action == "slow":
            await asyncio.sleep(0.35)
        return AdapterResponse(output=action, token_usage={"input": 10, "output": 5})


class FakePorts:
    """In-memory EnginePorts implementation."""

    def __init__(self, cases, selected_metrics, adapter, *, run_config=None, cancel_after=None):
        self.plan = RunPlan(
            run_id="run-1",
            application_type="llm",
            capabilities={"exposes_token_usage": True},
            cases=cases,
            selected_metrics=selected_metrics,
            run_config=run_config
            or {
                "concurrency": 2,
                "timeout_ms": 200,
                "max_retries": 0,
                "repeats": 1,
                "rate_limit_rps": 0,
            },
            model_name="gpt-4o",
        )
        self.adapter = adapter
        self.recorded = []  # list of (case_input, metrics)
        self.finish_args = None
        self.marked_running = False
        self._cancel_checks = 0
        self._cancel_after = cancel_after

    def load_plan(self, run_id: str) -> RunPlan:
        return self.plan

    def build_adapter(self, run_id: str):
        return self.adapter

    def is_cancel_requested(self, run_id: str) -> bool:
        self._cancel_checks += 1
        return self._cancel_after is not None and self._cancel_checks > self._cancel_after

    def mark_running(self, run_id: str) -> None:
        self.marked_running = True

    def record_case(self, run_id: str, case_input, metrics) -> None:
        self.recorded.append((case_input, list(metrics)))

    def finish(self, run_id: str, **kwargs) -> None:
        self.finish_args = kwargs


def _case(position, text, expected="answer") -> CaseData:
    return CaseData(
        id=f"case-{position}",
        position=position,
        case_input={"input": text},
        expected_output=expected,
    )


METRICS = [
    {"evaluator_id": "answer.exact_match", "version": "1.0.0", "config": {}},
    {"evaluator_id": "reliability.success_rate", "version": "1.0.0", "config": {}},
    {"evaluator_id": "performance.latency", "version": "1.0.0", "config": {}},
    {"evaluator_id": "cost.estimated_total", "version": "1.0.0", "config": {}},
]


def _summary_value(summary, evaluator_id):
    return next(m for m in summary if m.evaluator_id == evaluator_id)


def _case_metrics(recorded, text):
    for case_input, metrics in recorded:
        if case_input.case.case_input["input"] == text:
            return metrics
    raise AssertionError(f"case {text!r} not recorded")


def test_completed_run_records_all_cases_and_aggregates():
    adapter = FakeAdapter({"question-1": "answer", "question-2": "fail", "question-3": "answer"})
    ports = FakePorts(
        [_case(1, "question-1"), _case(2, "question-2"), _case(3, "question-3")],
        METRICS,
        adapter,
    )
    EvaluationEngine(ports).run("run-1")

    assert ports.marked_running
    assert ports.finish_args is not None
    assert ports.finish_args["status"] == RunStatus.COMPLETED
    assert len(ports.recorded) == 3

    # Failure isolation (FR-C3): the failing case's metrics are unavailable;
    # the other cases still computed normally.
    failed_metrics = {
        m.evaluator_id: m for m in _case_metrics(ports.recorded, "question-2")
    }
    assert failed_metrics["answer.exact_match"].status == MetricStatus.UNAVAILABLE
    ok_metrics = {m.evaluator_id: m for m in _case_metrics(ports.recorded, "question-1")}
    assert ok_metrics["answer.exact_match"].status == MetricStatus.COMPUTED
    assert ok_metrics["answer.exact_match"].score == 1.0

    summary = ports.finish_args["summary_metrics"]
    success_rate = _summary_value(summary, "reliability.success_rate")
    assert success_rate.status == MetricStatus.COMPUTED
    assert abs(success_rate.score - 2 / 3) < 1e-6  # 2 of 3 invocations

    latency = _summary_value(summary, "performance.latency")
    assert latency.status == MetricStatus.COMPUTED
    assert latency.score is not None and latency.score >= 0

    # Cost: 2 successful invocations, (10*2.5 + 5*10)/1e6 = 0.000075 each.
    cost = _summary_value(summary, "cost.estimated_total")
    assert abs(cost.score - 2 * 0.000075) < 1e-9


def test_progress_and_metadata_passed_to_ports():
    ports = FakePorts([_case(1, "q")], METRICS, FakeAdapter())
    EvaluationEngine(ports).run("run-1")
    assert ports.finish_args["model_metadata"] == {"model": "gpt-4o"}
    assert ports.finish_args["duration_ms"] >= 0
    case_input, metrics = ports.recorded[0]
    assert case_input.repeats[0].outcome == CaseOutcome.SUCCESS
    assert case_input.repeats[0].token_usage == {"input": 10, "output": 5}


def test_timeout_outcome_isolated():
    adapter = FakeAdapter({"q": "slow"})  # sleeps 0.35s > timeout 0.2s
    ports = FakePorts([_case(1, "q")], METRICS, adapter)
    EvaluationEngine(ports).run("run-1")
    case_input, metrics = ports.recorded[0]
    assert case_input.repeats[0].outcome == CaseOutcome.TIMEOUT
    assert case_input.repeats[0].error_type == "timeout"
    match_metrics = {m.evaluator_id: m for m in metrics}
    assert match_metrics["answer.exact_match"].status == MetricStatus.UNAVAILABLE
    summary = ports.finish_args["summary_metrics"]
    assert _summary_value(summary, "reliability.success_rate").score == 0.0


def test_retries_exhausted_then_recorded():
    run_config = {
        "concurrency": 1,
        "timeout_ms": 200,
        "max_retries": 1,
        "repeats": 2,
        "rate_limit_rps": 0,
    }
    metrics = [{"evaluator_id": "reliability.error_rate", "version": "1.0.0", "config": {}}]
    ports = FakePorts(
        [_case(1, "q")], metrics, FakeAdapter(default="fail"), run_config=run_config
    )
    EvaluationEngine(ports).run("run-1")
    case_input, _metrics = ports.recorded[0]
    assert len(case_input.repeats) == 2
    assert all(r.outcome == CaseOutcome.APPLICATION_ERROR for r in case_input.repeats)
    assert case_input.repeats[0].error_type == "RuntimeError"
    # max_retries=1 -> 2 attempts per repeat = 4 total invocations
    summary = ports.finish_args["summary_metrics"]
    assert _summary_value(summary, "reliability.error_rate").score == 1.0


def test_consistency_metric_with_repeats():
    run_config = {
        "concurrency": 2,
        "timeout_ms": 200,
        "max_retries": 0,
        "repeats": 2,
        "rate_limit_rps": 0,
    }
    metrics = [{"evaluator_id": "reliability.consistency", "version": "1.0.0", "config": {}}]
    ports = FakePorts([_case(1, "q")], metrics, FakeAdapter(), run_config=run_config)
    EvaluationEngine(ports).run("run-1")
    summary = ports.finish_args["summary_metrics"]
    assert _summary_value(summary, "reliability.consistency").score == 1.0


def test_cooperative_cancellation_skips_remaining_cases():
    adapter = FakeAdapter()
    ports = FakePorts(
        [_case(1, "q1"), _case(2, "q2"), _case(3, "q3"), _case(4, "q4")],
        METRICS,
        adapter,
        cancel_after=2,
    )
    EvaluationEngine(ports).run("run-1")
    assert ports.finish_args is not None
    assert ports.finish_args["status"] == RunStatus.CANCELLED
    assert ports.finish_args["summary_metrics"] == []
    skipped = [
        ci for ci, _m in ports.recorded
        if ci.repeats[0].outcome == CaseOutcome.SKIPPED
    ]
    assert skipped, "remaining cases must be recorded as skipped"


def test_engine_failure_is_sanitized():
    class BoomPorts(FakePorts):
        def load_plan(self, run_id):
            raise RuntimeError("boom with secret-value")

    ports = BoomPorts([_case(1, "q")], METRICS, FakeAdapter())
    EvaluationEngine(ports).run("run-1")
    error = ports.finish_args["error_summary"]
    assert error["error_type"] == "RuntimeError"
    assert error["message"] == "unexpected engine error"  # internals never leaked
    assert ports.finish_args["status"] == RunStatus.FAILED
