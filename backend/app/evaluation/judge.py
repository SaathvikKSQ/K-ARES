"""LLM-as-a-judge module (T5.3, FR-D).

Pluggable judge providers used by rag.* response-quality metrics and optional
model-judged answer metrics. Design constraints (specs/decisions.md, metrics.md):

- ``disabled unless configured``: with no judge model configured the judge
  factory returns ``None`` and dependent metrics report ``unavailable`` (or use
  the deterministic fallback where the metric definition defines one).
- Deterministic fallbacks and heuristic variants must be labeled ``estimated``,
  never ``model_judged``.
- Judge metadata (model, prompt version, per-criterion scores) is persisted in
  the metric result ``details``.
- Judge failures raise ``JudgeUnavailableError``; evaluators translate that into
  a ``status=unavailable`` result — a judge outage must never fail the run.
- Mock/injected providers (``config["judge_provider"]``) are used in tests and
  CI so judged metrics are fully deterministic there.

Prompts are versioned in code (``PROMPTS``); the active version is
``ACTIVE_PROMPT_VERSION``. Changing prompts requires a version bump + review
(same policy as security suites, decision D9).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ACTIVE_PROMPT_VERSION = "1.0.0"
JUDGE_TIMEOUT_S = 30.0
_MAX_CONTEXT_CHARS = 8000  # per context block, keeps prompt bounded
_MAX_OUTPUT_CHARS = 8000

# Versioned prompt templates. Kept short and strict about JSON output.
PROMPTS: dict[str, dict[str, str]] = {
    "1.0.0": {
        "faithfulness": (
            "You evaluate factual grounding. Given an ANSWER and the CONTEXT "
            "used to generate it, decompose the answer into claims and decide "
            "for each claim whether it is fully supported by the context.\n"
            'Respond with JSON only: {"claims": [{"text": str, "supported": bool}], '
            '"explanation": str}.'
        ),
        "context_relevance": (
            "You evaluate retrieval quality. Given a QUESTION and retrieved "
            "CONTEXT chunks, rate each chunk's relevance to the question on a "
            "1-5 scale (5 = essential, 1 = unrelated).\n"
            'Respond with JSON only: {"chunk_scores": [int], "explanation": str}.'
        ),
        "answer_relevance": (
            "You evaluate answer relevance. Given a QUESTION and an ANSWER, "
            "score how well the answer addresses the question on a 1-5 scale.\n"
            'Respond with JSON only: {"score": int, "explanation": str}.'
        ),
        "answer_quality": (
            "You evaluate an answer against criteria. Given the QUESTION, the "
            "ANSWER, an optional EXPECTED answer and optional CONTEXT, score "
            "each criterion (correctness, relevance, completeness, clarity) "
            "1-5.\nRespond with JSON only: "
            '{"scores": {"criterion": int}, "explanation": str}.'
        ),
    }
}


@dataclass(frozen=True)
class JudgeRequest:
    """One judgment request; ``kind`` selects the prompt template."""

    kind: str  # faithfulness | context_relevance | answer_relevance | answer_quality
    input: str | None = None
    output: str | None = None
    expected_output: str | None = None
    contexts: list[str] | None = None
    criteria: tuple[str, ...] = ("correctness", "relevance", "completeness", "clarity")


@dataclass(frozen=True)
class JudgeResult:
    """Normalized judge outcome (provider-agnostic)."""

    overall: float | None
    explanation: str | None
    model: str
    prompt_version: str
    scores: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] | None = None

    def metadata(self) -> dict[str, Any]:
        """Judge metadata merged into metric result ``details``."""
        return {
            "judge_model": self.model,
            "judge_prompt_version": self.prompt_version,
            "judge_scores": self.scores,
        }


class JudgeUnavailableError(Exception):
    """Judge outage/misconfiguration; evaluators must surface, not fail."""


class JudgeProvider(Protocol):
    def evaluate(self, request: JudgeRequest) -> JudgeResult: ...


def _clip(text: str | None, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "…"


def _user_message(request: JudgeRequest) -> str:
    parts = []
    if request.input is not None:
        parts.append(f"QUESTION:\n{_clip(request.input, _MAX_OUTPUT_CHARS)}")
    if request.output is not None:
        parts.append(f"ANSWER:\n{_clip(request.output, _MAX_OUTPUT_CHARS)}")
    if request.expected_output is not None:
        parts.append(f"EXPECTED:\n{_clip(request.expected_output, _MAX_OUTPUT_CHARS)}")
    if request.contexts:
        blocks = "\n---\n".join(_clip(c, _MAX_CONTEXT_CHARS) for c in request.contexts)
        parts.append(f"CONTEXT:\n{blocks}")
    if request.kind == "answer_quality":
        parts.append("CRITERIA: " + ", ".join(request.criteria))
    return "\n\n".join(parts)


class OpenAICompatibleJudge:
    """Judge backed by an OpenAI-compatible chat/completions endpoint.

    Temperature 0 is requested (determinism recommended by metrics.md §1);
    the provider may still be non-deterministic — this is disclosed in UI/reports.
    """

    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    @property
    def prompt_version(self) -> str:
        return ACTIVE_PROMPT_VERSION

    def evaluate(self, request: JudgeRequest) -> JudgeResult:
        system = PROMPTS[ACTIVE_PROMPT_VERSION][request.kind]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": _user_message(request)},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=JUDGE_TIMEOUT_S,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise JudgeUnavailableError(f"judge request failed: {exc}") from None
        content = body.get("choices", [{}])[0].get("message", {}).get("content") or ""
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("not a JSON object")
        except ValueError:
            raise JudgeUnavailableError("judge returned non-JSON content") from None
        return self._normalize(request.kind, parsed, raw=body)

    def _normalize(
        self, kind: str, parsed: dict[str, Any], *, raw: dict[str, Any]
    ) -> JudgeResult:
        try:
            if kind == "faithfulness":
                claims = [c for c in parsed.get("claims", []) if isinstance(c, dict)]
                supported = sum(1 for c in claims if c.get("supported") is True)
                overall = supported / len(claims) if claims else None
                return JudgeResult(
                    overall=overall,
                    explanation=parsed.get("explanation"),
                    model=self.model,
                    prompt_version=self.prompt_version,
                    scores={"claims": parsed.get("claims", [])},
                    raw=raw,
                )
            if kind == "context_relevance":
                chunk_scores = [int(s) for s in parsed.get("chunk_scores", [])]
                overall = (
                    sum(chunk_scores) / (5 * len(chunk_scores))
                    if chunk_scores
                    else None
                )
                return JudgeResult(
                    overall=overall,
                    explanation=parsed.get("explanation"),
                    model=self.model,
                    prompt_version=self.prompt_version,
                    scores={"chunk_scores": chunk_scores},
                    raw=raw,
                )
            if kind in ("answer_relevance", "answer_quality"):
                scores = parsed.get("scores", {}) if kind == "answer_quality" else {}
                score = (
                    int(parsed["score"])
                    if kind == "answer_relevance" and "score" in parsed
                    else None
                )
                overall = None
                if kind == "answer_relevance" and score is not None:
                    overall = score / 5
                elif kind == "answer_quality" and scores:
                    vals = [v for v in scores.values() if isinstance(v, (int, float))]
                    overall = (sum(vals) / (5 * len(vals))) if vals else None
                return JudgeResult(
                    overall=overall,
                    explanation=parsed.get("explanation"),
                    model=self.model,
                    prompt_version=self.prompt_version,
                    scores=scores if kind == "answer_quality" else {"score": score},
                    raw=raw,
                )
        except (TypeError, ValueError) as exc:
            raise JudgeUnavailableError(f"malformed judge payload: {exc}") from None
        raise JudgeUnavailableError(f"unknown judge request kind '{kind}'")


def build_judge(config: dict[str, Any] | None = None) -> JudgeProvider | None:
    """Resolve the judge provider, or ``None`` when disabled (T5.3).

    Resolution order:
    1. Explicitly injected provider in ``config["judge_provider"]`` (tests/CI).
    2. ``JUDGE_MODEL``/``JUDGE_PROVIDER_URL`` settings → OpenAI-compatible judge.
    3. ``None`` → dependent metrics report ``unavailable``.
    """
    cfg = config or {}
    injected = cfg.get("judge_provider")
    if injected is not None and hasattr(injected, "evaluate"):
        return injected  # type: ignore[return-value]
    settings = get_settings()
    model = cfg.get("judge_model") or settings.judge_model
    if not model:
        return None
    base_url = cfg.get("judge_provider_url") or settings.judge_provider_url
    if not base_url:
        raise JudgeUnavailableError("JUDGE_MODEL is set but JUDGE_PROVIDER_URL is not")
    return OpenAICompatibleJudge(
        base_url=base_url,
        model=model,
        api_key=settings.judge_api_key,
    )
