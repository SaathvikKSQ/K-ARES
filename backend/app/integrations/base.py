"""Target application integration contract.

Every AI application under evaluation is reached through a ``TargetAdapter``
that declares its capabilities. Adapters NEVER fabricate response fields: data
the target does not report stays ``None`` (constitution §2.2, decisions D4).

Extension point: register new adapters in ``app.integrations.registry``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class AdapterCapabilities(BaseModel):
    """What a target application exposes. Drives metric applicability."""

    exposes_retrieved_docs: bool = False
    exposes_citations: bool = False
    exposes_traces: bool = False
    exposes_token_usage: bool = False
    streaming: bool = False


class ConnectionTestResult(BaseModel):
    """Sanitized connectivity check outcome (never contains credentials)."""

    success: bool
    message: str
    latency_ms: int | None = None
    checked_at: str | None = None


class ToolCall(BaseModel):
    """One observed tool invocation (agent traces only)."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    success: bool | None = None
    duration_ms: int | None = None
    order: int = 0


class RetrievedDocument(BaseModel):
    doc_id: str
    title: str | None = None
    content: str | None = None
    score: float | None = None


class Citation(BaseModel):
    doc_id: str
    position: int | None = None


class AdapterResponse(BaseModel):
    """Normalized response from a target application."""

    output: str
    retrieved_documents: list[RetrievedDocument] | None = None
    citations: list[Citation] | None = None
    agent_trace: dict[str, Any] | None = None  # {"tool_calls": [ToolCall-like dicts]}
    token_usage: dict[str, int] | None = None  # {"input": n, "output": m}
    ttft_ms: int | None = None
    raw: dict[str, Any] | None = None


class TargetAdapter(ABC):
    """Common interface for all target applications."""

    integration_type: str = "abstract"

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    async def test_connection(self) -> ConnectionTestResult:
        """Safe, bounded connectivity check. Must never raise credentials."""

    @abstractmethod
    async def invoke(self, case_input: dict[str, Any], timeout_s: float) -> AdapterResponse:
        """Execute one test case. Raises on transport/application failure."""
