"""Run orchestration: plan -> execute -> evaluate -> persist (FR-C, T3.3).

Execution model per case: ``repeats`` adapter invocations, each wrapped in a
timeout, with up to ``max_retries`` retries on timeout/application error, a
global rate limiter, and a concurrency semaphore. A failing case is isolated:
its metrics become ``unavailable`` and other cases proceed (FR-C3). Cancellation
is cooperative: checked before each case; not-yet-executed cases are recorded
as skipped (FR-C5). Progress is persisted after every case (FR-C6).
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.evaluation import registry
from app.evaluation.base import (
    CaseData,
    CaseEvalInput,
    MetricValue,
    RepeatRecord,
    RunEvalInput,
)
from app.evaluation.errors import EvaluationError
from app.evaluation.ports import EnginePorts, RunPlan
from app.models.enums import CaseOutcome, RunStatus

logger = logging.getLogger(__name__)


class _RateLimiter:
    """Global pacing between adapter invocations (rate_limit_rps)."""

    def __init__(self, rate_limit_rps: float):
        self._min_interval = (
            1.0 / rate_limit_rps if rate_limit_rps and rate_limit_rps > 0 else 0.0
        )
        self._next_slot = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.perf_counter()
            delay = self._next_slot - now
            if delay > 0:
                await asyncio.sleep(delay)
                now = time.perf_counter()
            self._next_slot = max(now, self._next_slot) + self._min_interval


class EvaluationEngine:
    """Executes one evaluation run end to end via its ports."""

    def __init__(self, ports: EnginePorts):
        self.ports = ports
        self._cancel_seen = False

    def run(self, run_id: str) -> None:
        """Blocking entry point (used by the background worker thread)."""
        asyncio.run(self._execute(run_id))

    async def _execute(self, run_id: str) -> None:
        registry.ensure_loaded()
        plan: RunPlan | None = None
        try:
            plan = self.ports.load_plan(run_id)
            # Security suite (T5.5): system-generated controlled cases appended
            # after the user's dataset selection; verdict metric auto-selected.
            if plan.run_config.get("include_security_suite"):
                from app.evaluation.security.suite import build_security_cases

                extra = build_security_cases()
                object.__setattr__(plan, "cases", list(plan.cases) + extra)
                if not any(
                    s.get("evaluator_id") == "security.verdict"
                    for s in plan.selected_metrics
                ):
                    object.__setattr__(
                        plan,
                        "selected_metrics",
                        list(plan.selected_metrics) + [{"evaluator_id": "security.verdict"}],
                    )
            adapter = self.ports.build_adapter(run_id)
            wall_start = time.perf_counter()
            self.ports.mark_running(run_id)
            run_config = plan.run_config
            timeout_s = float(run_config.get("timeout_ms", 30000)) / 1000
            repeats = int(run_config.get("repeats", 1))
            retries = int(run_config.get("max_retries", 1))
            semaphore = asyncio.Semaphore(int(run_config.get("concurrency", 4)))
            limiter = _RateLimiter(float(run_config.get("rate_limit_rps", 0) or 0))

            recorded: list[CaseEvalInput] = []
            tasks = [
                asyncio.create_task(
                    self._execute_case(
                        run_id, case, plan, adapter, semaphore, limiter,
                        timeout_s, repeats, retries,
                    )
                )
                for case in plan.cases
            ]
            for future in asyncio.as_completed(tasks):
                recorded.append(await future)

            duration_ms = int((time.perf_counter() - wall_start) * 1000)
            run_meta = {
                "model_name": plan.model_name,
                "duration_ms": duration_ms,
                "application_type": plan.application_type,
            }
            if self._cancel_seen:
                self.ports.finish(
                    run_id,
                    status=RunStatus.CANCELLED,
                    summary_metrics=[],
                    error_summary={"reason": "cancelled by user"},
                    model_metadata={"model": plan.model_name},
                    duration_ms=duration_ms,
                )
                return
            summary = self._evaluate_run_scope(plan, recorded, run_meta)
            self.ports.finish(
                run_id,
                status=RunStatus.COMPLETED,
                summary_metrics=summary,
                error_summary=None,
                model_metadata={"model": plan.model_name},
                duration_ms=duration_ms,
            )
        except Exception as exc:  # any engine failure: sanitized taxonomy
            logger.exception("Run %s failed", run_id)
            duration_ms = 0
            error_type = type(exc).__name__
            message = (
                exc.message if isinstance(exc, EvaluationError) else "unexpected engine error"
            )
            self.ports.finish(
                run_id,
                status=RunStatus.FAILED,
                summary_metrics=[],
                error_summary={"error_type": error_type, "message": message},
                model_metadata={"model": plan.model_name if plan else None},
                duration_ms=duration_ms,
            )

    async def _execute_case(
        self,
        run_id: str,
        case: CaseData,
        plan: RunPlan,
        adapter,
        semaphore: asyncio.Semaphore,
        limiter: _RateLimiter,
        timeout_s: float,
        repeats: int,
        retries: int,
    ) -> CaseEvalInput:
        async with semaphore:
            if self.ports.is_cancel_requested(run_id):
                self._cancel_seen = True
                skipped = RepeatRecord(
                    repeat_index=0,
                    outcome=CaseOutcome.SKIPPED,
                    error_type="cancelled",
                    error_message="run cancelled before execution",
                )
                case_input = CaseEvalInput(case=case, repeats=[skipped])
                self.ports.record_case(run_id, case_input, [])
                return case_input
            repeat_records = [
                await self._invoke_with_retry(
                    case, i, adapter, limiter, timeout_s, retries
                )
                for i in range(repeats)
            ]
            case_input = CaseEvalInput(case=case, repeats=repeat_records)
            metrics = self._evaluate_case(plan, case_input)
            self.ports.record_case(run_id, case_input, metrics)
            return case_input

    async def _invoke_with_retry(
        self,
        case: CaseData,
        repeat_index: int,
        adapter,
        limiter: _RateLimiter,
        timeout_s: float,
        retries: int,
    ) -> RepeatRecord:
        """One repeat: invoke with timeout, retrying application errors."""
        last: RepeatRecord | None = None
        for _attempt in range(retries + 1):
            await limiter.wait()
            started = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    adapter.invoke(case.case_input, timeout_s), timeout=timeout_s
                )
            except TimeoutError:
                elapsed = int((time.perf_counter() - started) * 1000)
                last = RepeatRecord(
                    repeat_index=repeat_index,
                    outcome=CaseOutcome.TIMEOUT,
                    error_type="timeout",
                    error_message=f"no response within {int(timeout_s * 1000)} ms",
                    latency_ms=elapsed,
                )
                continue
            except Exception as exc:  # transport/application failure (sanitized)
                elapsed = int((time.perf_counter() - started) * 1000)
                last = RepeatRecord(
                    repeat_index=repeat_index,
                    outcome=CaseOutcome.APPLICATION_ERROR,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:500],
                    latency_ms=elapsed,
                )
                continue
            elapsed = int((time.perf_counter() - started) * 1000)
            return RepeatRecord(
                repeat_index=repeat_index,
                outcome=CaseOutcome.SUCCESS,
                output=response.output,
                latency_ms=elapsed,
                ttft_ms=response.ttft_ms,
                token_usage=response.token_usage,
                retrieved_document_ids=[
                    d.doc_id for d in (response.retrieved_documents or [])
                ],
                retrieved_documents=[
                    d.model_dump() for d in (response.retrieved_documents or [])
                ],
                citations=[c.doc_id for c in (response.citations or [])],
                agent_trace=response.agent_trace,
            )
        assert last is not None
        return last

    def _evaluate_case(self, plan: RunPlan, case_input: CaseEvalInput) -> list[MetricValue]:
        """Case-scope evaluators for one case; errors become unavailable."""
        values: list[MetricValue] = []
        for selection in plan.selected_metrics:
            spec, fn = registry.get(selection["evaluator_id"])
            if spec.scope != "case":
                continue
            # Per-evaluator config merged over the run config (judge/embedding
            # settings, thresholds, k values; T5.3/T5.6).
            case_input.config = {**plan.run_config, **(selection.get("config") or {})}
            values.append(fn(case_input))
        return values

    def _evaluate_run_scope(
        self, plan: RunPlan, cases: list[CaseEvalInput], run_meta: dict
    ) -> list[MetricValue]:
        """Run-scope (aggregate) evaluators over all recorded cases."""
        run_input = RunEvalInput(
            cases=cases, run_config=dict(plan.run_config), run_meta=run_meta
        )
        values: list[MetricValue] = []
        for selection in plan.selected_metrics:
            spec, fn = registry.get(selection["evaluator_id"])
            if spec.scope != "run":
                continue
            values.append(fn(run_input))
        return values
