"""Versioned token-pricing table for cost estimation (FR-D6, T3.5).

Code-defined and versioned (static at MVP); estimates only - actual billing
may differ. Future work may move this table into the database.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import MetricStatus

PRICING_VERSION = "2026-10"

# USD per 1M tokens: model -> {"input": rate, "output": rate}
_TOKEN_PRICES: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-3-5-sonnet-latest": {"input": 3.00, "output": 15.00},
    "llama-3.1-8b-instruct": {"input": 0.05, "output": 0.08},
}


@dataclass(frozen=True)
class CostEstimate:
    """Result of a cost estimate; ``amount_usd`` is None when unavailable."""

    status: MetricStatus
    amount_usd: float | None
    reason: str | None = None


def estimate_cost(model: str | None, input_tokens: int, output_tokens: int) -> CostEstimate:
    """Estimate USD cost for one invocation; never fabricates a number."""
    if not model:
        return CostEstimate(
            MetricStatus.UNAVAILABLE, None, "no model metadata reported by application"
        )
    prices = _TOKEN_PRICES.get(model)
    if prices is None:
        return CostEstimate(
            MetricStatus.UNAVAILABLE,
            None,
            f"no pricing entry for model '{model}' (pricing version {PRICING_VERSION})",
        )
    amount = (
        input_tokens * prices["input"] + output_tokens * prices["output"]
    ) / 1_000_000
    return CostEstimate(MetricStatus.COMPUTED, amount)


def pricing_table() -> dict:
    """Public descriptor of the pricing table (for the /metrics surface)."""
    return {
        "version": PRICING_VERSION,
        "currency": "USD",
        "unit": "per_1m_tokens",
        "models": dict(_TOKEN_PRICES),
    }
