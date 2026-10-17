"""Generic REST adapter with SSRF protection and strict outbound limits.

Spec references: SR-15..SR-17 (SSRF, timeouts, size/concurrency limits).
Expected target contract (documented): POST {base_url}{invoke_path} with
``{"input": ...}``; response must contain a string ``output`` (aliases:
``answer``/``response``). Optional fields are passed through only when the
application declares the matching capability — never fabricated.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.security import URLValidationError, validate_target_url
from app.integrations.base import (
    AdapterCapabilities,
    AdapterResponse,
    ConnectionTestResult,
    TargetAdapter,
)

MAX_REDIRECTS = 2


class RestAdapterError(RuntimeError):
    """Transport/application failure; message is safe for storage/display."""


class RestAdapter(TargetAdapter):
    """HTTP adapter for applications exposing a JSON endpoint."""

    integration_type = "rest_api"

    def __init__(
        self,
        base_url: str,
        auth: dict[str, Any] | None = None,
        capabilities: dict[str, bool] | None = None,
        invoke_path: str = "",
    ):
        self.base_url = validate_target_url(
            base_url, allow_private_targets=get_settings().allow_private_targets
        )
        self.auth = auth or {}
        self.invoke_path = invoke_path or ""
        self._capabilities = AdapterCapabilities(**(capabilities or {}))

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth_type = self.auth.get("type")
        if auth_type == "api_key":
            header_name = str(self.auth.get("header", "X-API-Key"))
            headers[header_name] = str(self.auth.get("value", ""))
        elif auth_type == "bearer":
            headers["Authorization"] = f"Bearer {self.auth.get('value', '')}"
        elif auth_type == "basic":
            import base64

            raw = f"{self.auth.get('username', '')}:{self.auth.get('password', '')}"
            headers["Authorization"] = "Basic " + base64.b64encode(raw.encode()).decode()
        return headers

    def _client(self, timeout_s: float) -> httpx.AsyncClient:
        settings = get_settings()
        return httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.adapter_connect_timeout_s,
                read=timeout_s,
                write=settings.adapter_connect_timeout_s,
                pool=5.0,
            ),
            follow_redirects=False,
            headers=self._headers(),
        )

    async def test_connection(self) -> ConnectionTestResult:
        """GET the target root — a lightweight, safe check only."""
        started = time.perf_counter()
        try:
            async with self._client(timeout_s=15) as client:
                resp = await client.get(self.base_url)
            latency = int((time.perf_counter() - started) * 1000)
            if resp.status_code < 400:
                return ConnectionTestResult(
                    success=True, message="Connection successful", latency_ms=latency
                )
            return ConnectionTestResult(
                success=False,
                message=f"Target responded with HTTP {resp.status_code}",
                latency_ms=latency,
            )
        except httpx.HTTPError:
            return ConnectionTestResult(success=False, message="Connection failed (network error)")

    async def invoke(self, case_input: dict[str, Any], timeout_s: float) -> AdapterResponse:
        settings = get_settings()
        payload = {
            "input": case_input.get("input", ""),
            "metadata": case_input.get("metadata", {}),
        }
        started = time.perf_counter()
        try:
            async with self._client(timeout_s=timeout_s) as client:
                resp = await client.post(f"{self.base_url}{self.invoke_path}", json=payload)
            # Manual redirect handling with re-validation and a hard cap (SR-16).
            for _ in range(MAX_REDIRECTS):
                if resp.status_code not in (301, 302, 307, 308):
                    break
                location = resp.headers.get("Location", "")
                if not location:
                    break
                next_url = validate_target_url(
                    str(resp.url.join(location)),
                    allow_private_targets=settings.allow_private_targets,
                )
                async with self._client(timeout_s=timeout_s) as client:
                    resp = await client.post(next_url, json=payload)
        except URLValidationError as exc:
            raise RestAdapterError(str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"request exceeded {timeout_s}s timeout") from exc
        except httpx.HTTPError as exc:
            raise RestAdapterError(f"transport error: {type(exc).__name__}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        content = resp.content
        if len(content) > settings.adapter_max_response_bytes:
            raise RestAdapterError("response exceeded maximum allowed size")
        if resp.status_code >= 400:
            raise RestAdapterError(f"application returned HTTP {resp.status_code}")
        return self._parse(resp.json(), latency_ms)

    def _parse(self, body: dict[str, Any], latency_ms: int) -> AdapterResponse:
        if not isinstance(body, dict):
            raise RestAdapterError("response body must be a JSON object")
        output = body.get("output", body.get("answer", body.get("response")))
        if not isinstance(output, str):
            raise RestAdapterError("response is missing a string 'output' field")
        caps = self._capabilities
        return AdapterResponse(
            output=output,
            retrieved_documents=(
                body.get("retrieved_documents") if caps.exposes_retrieved_docs else None
            ),
            citations=body.get("citations") if caps.exposes_citations else None,
            agent_trace=(
                {"tool_calls": body.get("tool_calls", [])}
                if caps.exposes_traces and "tool_calls" in body
                else None
            ),
            token_usage=body.get("token_usage") if caps.exposes_token_usage else None,
            ttft_ms=body.get("ttft_ms"),
        )

