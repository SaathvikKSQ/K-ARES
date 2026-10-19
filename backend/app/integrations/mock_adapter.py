"""Deterministic mock adapter (for local development and automated tests).

Behavior is fully deterministic — no randomness, no network:
- Output echoes a structured transformation of the input (stable across runs).
- ``retrieved_documents`` / ``token_usage`` / ``agent_trace`` are emitted only
  when explicitly enabled via adapter config (never fabricated silently).
- Failure simulation is input-triggered: input containing ``trigger_error``
  raises an application error; ``trigger_timeout`` sleeps ``timeout_s``+.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.integrations.base import (
    AdapterCapabilities,
    AdapterResponse,
    ConnectionTestResult,
    TargetAdapter,
)


class MockAdapter(TargetAdapter):
    """Configurable deterministic mock for rag/llm/agent app types."""

    integration_type = "mock"

    def __init__(self, config: dict[str, Any], capabilities: dict[str, bool] | None = None):
        self.config = config or {}
        self._capabilities = AdapterCapabilities(**(capabilities or {}))

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(success=True, message="Mock application is always reachable")

    async def invoke(self, case_input: dict[str, Any], timeout_s: float) -> AdapterResponse:
        question = str(case_input.get("input", ""))
        started = time.perf_counter()

        delay_ms = int(self.config.get("latency_ms", 20))
        if delay_ms > 0:
            await asyncio.sleep(min(delay_ms, timeout_s) / 1000)

        if "trigger_timeout" in question:
            await asyncio.sleep(timeout_s + 1)
        if "trigger_error" in question:
            raise RuntimeError("Mock application simulated failure (trigger_error)")

        prefix = self.config.get("output_prefix", "")
        output = f"{prefix}{question}" if prefix else f"MOCK-ANSWER: {question}"

        docs = self._mock_documents(case_input)
        usage = None
        if self._capabilities.exposes_token_usage:
            usage = {"input": max(1, len(question.split())), "output": max(1, len(output.split()))}

        return AdapterResponse(
            output=output,
            retrieved_documents=docs,
            citations=self._mock_citations(docs),
            agent_trace=self._mock_trace(case_input),
            token_usage=usage,
            ttft_ms=max(1, int((time.perf_counter() - started) * 1000) // 2)
            if self._capabilities.streaming
            else None,
        )

    def _mock_documents(self, case_input: dict[str, Any]) -> list[dict[str, Any]] | None:
        if not self._capabilities.exposes_retrieved_docs:
            return None
        labels = case_input.get("relevant_doc_ids") or []
        # Echo labeled doc ids as retrieved (deterministic, labeled fixtures only).
        docs = [
            {
                "doc_id": str(doc_id),
                "content": f"MOCK-DOC: {doc_id}",
                "score": 0.9 - i * 0.1,
            }
            for i, doc_id in enumerate(labels)
        ]
        return docs or [{"doc_id": "mock-doc-1", "content": "MOCK-DOC: mock-doc-1", "score": 0.5}]

    def _mock_citations(self, docs: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if not self._capabilities.exposes_citations:
            return None
        return [{"doc_id": d["doc_id"], "position": i} for i, d in enumerate(docs or [])]

    def _mock_trace(self, case_input: dict[str, Any]) -> dict[str, Any] | None:
        if not self._capabilities.exposes_traces:
            return None
        expected = case_input.get("expected_tool")
        calls: list[dict[str, Any]] = []
        if expected:
            tool = expected if isinstance(expected, str) else expected.get("name", "unknown")
            calls.append({"name": tool, "args": {}, "success": True, "order": 1})
        return {"tool_calls": calls}
