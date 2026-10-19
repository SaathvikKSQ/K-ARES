"""Semantic similarity evaluator (T5.6, FR-D; metrics.md §1).

``answer.semantic_similarity``: cosine similarity between embeddings of the
actual and expected output, reported in [0, 1] via (s + 1) / 2. Gated: the
metric is ``unavailable`` unless an embedding model is configured
(``EMBEDDING_MODEL`` setting or per-run config ``embedding_model``).
Embeddings are provided by an injectable ``embedding_fn`` (config) used by
tests with deterministic stubs; when configured for real runs the function
must map text -> vector. The platform never fabricates vectors (constitution
§2.2).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.core.config import get_settings
from app.evaluation.base import CaseEvalInput, EvaluatorSpec, MetricValue
from app.evaluation.registry import register
from app.models.enums import MetricStatus, Provenance, ValueKind


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


_SIMILARITY = EvaluatorSpec(
    id="answer.semantic_similarity",
    name="Semantic Similarity",
    description=(
        "Cosine similarity between embeddings of the actual and expected "
        "output, mapped to [0, 1] via (s + 1) / 2. Requires a configured "
        "embedding model (EMBEDDING_MODEL); similarity is not correctness. "
        "Tests use deterministic stub embeddings."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.SCORE,
    scope="case",
    application_types=("rag", "llm", "agent"),
    required_fields=("expected_output",),
    config_schema={
        "embedding_model": {"type": "string", "required": False},
        "embedding_fn": {"type": "object", "required": False, "internal": True},
    },
)


def _resolve_embedding_fn(inp: CaseEvalInput):
    """Injectable embedding function (tests/CI) or None when disabled."""
    fn = inp.config.get("embedding_fn")
    if callable(fn):
        return fn
    return None


def _similarity(inp: CaseEvalInput) -> MetricValue:
    if inp.case.expected_output is None:
        return MetricValue.unavailable(_SIMILARITY, "case has no expected_output label")
    configured = inp.config.get("embedding_model") or get_settings().embedding_model
    if not configured:
        return MetricValue.unavailable(
            _SIMILARITY, "embedding model not configured (EMBEDDING_MODEL)"
        )
    embedding_fn = _resolve_embedding_fn(inp)
    if embedding_fn is None:
        return MetricValue.unavailable(
            _SIMILARITY, "no embedding provider available in this deployment"
        )
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_SIMILARITY, "case execution did not succeed")
    expected_vec = embedding_fn(inp.case.expected_output)
    scores = []
    for r in successes:
        actual_vec = embedding_fn(r.output or "")
        sim = cosine_similarity(expected_vec, actual_vec)
        scores.append((sim + 1) / 2)
    return MetricValue(
        evaluator_id=_SIMILARITY.id,
        evaluator_version=_SIMILARITY.version,
        provenance=_SIMILARITY.provenance,
        value_kind=_SIMILARITY.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(sum(scores) / len(scores), 6),
        explanation=(
            f"mean cosine similarity (mapped to [0,1]) over {len(scores)} "
            f"successful repeat(s); model '{configured}'"
        ),
        details={
            "embedding_model": configured,
            "per_repeat": [round(s, 6) for s in scores],
        },
    )


register(_SIMILARITY, _similarity)
