"""RAG retrieval-quality evaluators (T5.1, FR-D; metrics.md §2).

All metrics are deterministic, case-scope, and compare the rank list R of
retrieved doc ids against the labeled relevant set G (``relevant_doc_ids``).
Per repeat computation, averaged over successful repeats. Unavailable paths
record explicit reasons (universal rule 1): missing labels, no exposed
documents, or failed execution — unavailable never counts as zero.

Config: ``k`` (default 5). Gain scheme: binary (v1); the dataset format stores
plain doc-id labels without graded relevance.
"""

from __future__ import annotations

import math

from app.evaluation.base import CaseEvalInput, EvaluatorSpec, MetricValue
from app.evaluation.registry import register
from app.models.enums import MetricStatus, Provenance, ValueKind

DEFAULT_K = 5


def _labels_and_rankings(inp: CaseEvalInput, spec: EvaluatorSpec, k: int):
    """Resolve (relevant_set, [(ranked_ids), ...]) or an unavailable reason."""
    if inp.case.relevant_doc_ids is None:
        return None, None, "case has no relevance labels (relevant_doc_ids)"
    successes = inp.successful_repeats()
    if not successes:
        return None, None, "case execution did not succeed"
    rankings = []
    missing_docs = False
    for r in successes:
        if r.retrieved_document_ids is None:
            missing_docs = True
        else:
            rankings.append(r.retrieved_document_ids)
    if not rankings:
        return None, None, "application did not expose retrieved documents"
    note = (
        "some successful repeats did not expose retrieved documents"
        if missing_docs
        else None
    )
    return set(inp.case.relevant_doc_ids), rankings, note


def _mean_over_rankings(values: list[float]) -> float:
    return round(sum(values) / len(values), 6)


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    top = ranked[:k]
    return sum(1 for d in top if d in relevant) / k


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    top = ranked[:k]
    return sum(1 for d in top if d in relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: set[str], k: int = DEFAULT_K) -> float:
    for i, d in enumerate(ranked, start=1):
        if d in relevant:
            return 1 / i
    return 0.0


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    def dcg(ids: list[str]) -> float:
        return sum(
            (1.0 / math.log2(i + 1))
            for i, d in enumerate(ids[:k], start=1)
            if d in relevant
        )

    ideal = sorted(ranked, key=lambda d: 0 if d in relevant else 1)
    idcg = dcg(ideal)
    if idcg == 0:
        return 0.0
    return dcg(ranked) / idcg


def _make_k_spec(metric: str, name: str, description: str, required: bool) -> EvaluatorSpec:
    return EvaluatorSpec(
        id=metric,
        name=name,
        description=description,
        version="1.0.0",
        provenance=Provenance.MEASURED,
        value_kind=ValueKind.SCORE,
        scope="case",
        application_types=("rag",),
        required_fields=("relevant_doc_ids",) if required else (),
        capabilities_required=("exposes_retrieved_docs",) if required else (),
        config_schema={"k": {"type": "integer", "required": False, "default": DEFAULT_K}},
    )


def _k_of(inp: CaseEvalInput) -> int:
    k = inp.config.get("k", DEFAULT_K)
    try:
        return max(1, int(k))
    except (TypeError, ValueError):
        return DEFAULT_K


def _compute(
    inp: CaseEvalInput,
    spec: EvaluatorSpec,
    fn,
    *,
    needs_nonempty_labels: bool,
) -> MetricValue:
    k = _k_of(inp)
    relevant, rankings, note = _labels_and_rankings(inp, spec, k)
    if relevant is None or rankings is None:
        return MetricValue.unavailable(spec, note or "")
    if needs_nonempty_labels and not relevant:
        return MetricValue.unavailable(
            spec, "case is labeled as having no relevant docs (empty relevant_doc_ids)"
        )
    scores = [fn(r, relevant, k) for r in rankings]
    details: dict = {
        "k": k,
        "per_repeat": [round(s, 6) for s in scores],
        "relevant_count": len(relevant),
    }
    if note:
        details["coverage_note"] = note
    return MetricValue(
        evaluator_id=spec.id,
        evaluator_version=spec.version,
        provenance=spec.provenance,
        value_kind=spec.value_kind,
        status=MetricStatus.COMPUTED,
        score=_mean_over_rankings(scores),
        explanation=f"mean over {len(rankings)} successful repeat(s), k={k}",
        details=details,
    )


_PRECISION = _make_k_spec(
    "retrieval.precision_at_k",
    "Precision@K",
    "Fraction of the top-K retrieved documents that are labeled relevant. "
    "A labeled-empty relevant set yields 0.0.",
    True,
)


def _precision(inp: CaseEvalInput) -> MetricValue:
    return _compute(inp, _PRECISION, precision_at_k, needs_nonempty_labels=False)


_RECALL = _make_k_spec(
    "retrieval.recall_at_k",
    "Recall@K",
    "Fraction of labeled relevant documents present in the top-K retrieved. "
    "Unavailable when the relevant set is empty.",
    True,
)


def _recall(inp: CaseEvalInput) -> MetricValue:
    return _compute(inp, _RECALL, recall_at_k, needs_nonempty_labels=True)


_MRR = _make_k_spec(
    "retrieval.mrr",
    "Mean Reciprocal Rank",
    "Reciprocal rank of the first relevant retrieved document (0 if none "
    "appears at any position).",
    True,
)


def _mrr(inp: CaseEvalInput) -> MetricValue:
    # Empty relevant set is meaningful here: RR = 0 (no relevant doc retrieved).
    return _compute(inp, _MRR, reciprocal_rank, needs_nonempty_labels=False)


_NDCG = _make_k_spec(
    "retrieval.ndcg_at_k",
    "NDCG@K",
    "Normalized discounted cumulative gain at K with binary gains "
    "(graded labels are not represented in the v1 dataset format). "
    "Unavailable when the relevant set is empty.",
    True,
)


def _ndcg(inp: CaseEvalInput) -> MetricValue:
    return _compute(inp, _NDCG, ndcg_at_k, needs_nonempty_labels=True)


register(_PRECISION, _precision)
register(_RECALL, _recall)
register(_MRR, _mrr)
register(_NDCG, _ndcg)
