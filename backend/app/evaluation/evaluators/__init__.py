"""Core evaluators (T3.2, FR-D).

Importing this package registers all built-in evaluators with the registry
(``app.evaluation.registry.ensure_loaded``). Add new metrics here — or in a
new module imported below — via ``registry.register(spec, fn)``; no engine
changes required (FR-E3).
"""

from __future__ import annotations

from app.evaluation.evaluators import answer, cost, performance, reliability  # noqa: F401

CORE_EVALUATOR_IDS = (
    "answer.exact_match",
    "answer.token_f1",
    "answer.correctness",
    "reliability.success_rate",
    "reliability.error_rate",
    "reliability.timeout_rate",
    "reliability.malformed_rate",
    "reliability.consistency",
    "performance.latency",
    "performance.throughput",
    "performance.token_usage",
    "cost.estimated_total",
    "cost.estimated_per_case",
)
