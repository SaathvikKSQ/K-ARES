"""RAG response-quality evaluators (T5.2, FR-D; metrics.md Â§3).

Judge-based metrics use the pluggable judge module (T5.3). Where the metric
definition defines a deterministic fallback (faithfulness claim-check,
context_relevance overlap), the fallback runs when no judge is configured and
is labeled ``estimated`` â€” never ``model_judged``. ``answer_relevance`` has no
defined fallback and is ``unavailable`` without a judge.

Citation metrics are measured: they compare cited doc ids against the labeled
relevant set and are unavailable with explicit reasons when citations or
labels are missing (universal rule 1).
"""

from __future__ import annotations

import re

from app.evaluation.base import CaseEvalInput, EvaluatorSpec, MetricValue
from app.evaluation.judge import (
    ACTIVE_PROMPT_VERSION,
    JudgeRequest,
    JudgeUnavailableError,
    build_judge,
)
from app.evaluation.registry import register
from app.models.enums import MetricStatus, Provenance, ValueKind

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CLAIM_SUPPORT_THRESHOLD = 0.6


def _tokens(text: str | None) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6)


def _contexts(inp: CaseEvalInput) -> tuple[list[str], bool]:
    """Context strings from successful repeats; second element = all present."""
    contexts: list[str] = []
    complete = True
    for r in inp.successful_repeats():
        if not r.retrieved_documents:
            complete = False
            continue
        for doc in r.retrieved_documents:
            content = (doc or {}).get("content")
            if content:
                contexts.append(str(content))
    return contexts, complete


def _judge_call(inp: CaseEvalInput, request: JudgeRequest, spec: EvaluatorSpec) -> MetricValue:
    """Run the judge; any failure becomes an explicit unavailable result."""
    judge = build_judge(inp.config)
    if judge is None:
        return MetricValue.unavailable(spec, "LLM judge not configured")
    try:
        result = judge.evaluate(request)
    except JudgeUnavailableError as exc:
        return MetricValue.unavailable(spec, str(exc))
    if result.overall is None:
        return MetricValue.unavailable(spec, "judge returned no score")
    details = result.metadata()
    details["judge_prompt_version_active"] = ACTIVE_PROMPT_VERSION
    if result.explanation:
        details["judge_explanation"] = result.explanation
    return MetricValue(
        evaluator_id=spec.id,
        evaluator_version=spec.version,
        provenance=Provenance.MODEL_JUDGED,
        value_kind=spec.value_kind,
        status=MetricStatus.COMPUTED,
        score=round(result.overall, 6),
        explanation=result.explanation,
        details=details,
    )


# --- faithfulness ---------------------------------------------------------


def _claim_check_faithfulness(inp: CaseEvalInput, spec: EvaluatorSpec) -> MetricValue:
    """Deterministic fallback: sentence-level token support against context."""
    contexts, complete = _contexts(inp)
    if not contexts:
        return MetricValue.unavailable(
            spec, "retrieved context content not available for claim check"
        )
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(spec, "case execution did not succeed")
    context_tokens = _tokens(" ".join(contexts))
    scores: list[float] = []
    claims_all: list[dict] = []
    for r in successes:
        sentences = [s for s in _SENT_SPLIT_RE.split(r.output or "") if s.strip()]
        if not sentences:
            scores.append(1.0)
            continue
        supported = 0
        for sentence in sentences:
            toks = _tokens(sentence)
            overlap = len(toks & context_tokens) / len(toks) if toks else 1.0
            is_supported = overlap >= _CLAIM_SUPPORT_THRESHOLD
            supported += is_supported
            claims_all.append({"text": sentence[:200], "supported": is_supported})
        scores.append(supported / len(sentences))
    details: dict = {
        "method": "claim_check_fallback",
        "claims": claims_all,
        "judge_model": None,
        "per_repeat": [round(s, 6) for s in scores],
    }
    if not complete:
        details["coverage_note"] = "some repeats lacked document content"
    return MetricValue(
        evaluator_id=spec.id,
        evaluator_version=spec.version,
        provenance=Provenance.ESTIMATED,
        value_kind=spec.value_kind,
        status=MetricStatus.COMPUTED,
        score=_mean(scores),
        explanation=(
            "deterministic claim-check fallback (sentence token support "
            f">= {_CLAIM_SUPPORT_THRESHOLD}); LLM judge not configured"
        ),
        details=details,
    )


_FAITHFULNESS = EvaluatorSpec(
    id="rag.faithfulness",
    name="RAG Faithfulness",
    description=(
        "Fraction of answer claims supported by the retrieved context. "
        "Model-judged when a judge provider is configured; otherwise a "
        "deterministic claim-check fallback labeled 'estimated'."
    ),
    version="1.0.0",
    provenance=Provenance.MODEL_JUDGED,
    value_kind=ValueKind.SCORE,
    scope="case",
    application_types=("rag",),
    capabilities_required=("exposes_retrieved_docs",),
)


def _faithfulness(inp: CaseEvalInput) -> MetricValue:
    judge = build_judge(inp.config)
    if judge is None:
        return _claim_check_faithfulness(inp, _FAITHFULNESS)
    contexts, _ = _contexts(inp)
    if not contexts:
        return MetricValue.unavailable(
            _FAITHFULNESS, "retrieved context content not available for judging"
        )
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_FAITHFULNESS, "case execution did not succeed")
    per_repeat: list[float] = []
    details: dict = {"judge_model": None}
    for r in successes:
        value = _judge_call(
            inp,
            JudgeRequest(kind="faithfulness", output=r.output, contexts=contexts),
            _FAITHFULNESS,
        )
        if value.status != MetricStatus.COMPUTED:
            return value
        per_repeat.append(value.score or 0.0)
        if value.details.get("judge_model"):
            details["judge_model"] = value.details["judge_model"]
            details["judge_prompt_version"] = value.details.get("judge_prompt_version")
            details["judge_scores"] = value.details.get("judge_scores")
    details["per_repeat"] = [round(s, 6) for s in per_repeat]
    return MetricValue(
        evaluator_id=_FAITHFULNESS.id,
        evaluator_version=_FAITHFULNESS.version,
        provenance=Provenance.MODEL_JUDGED,
        value_kind=_FAITHFULNESS.value_kind,
        status=MetricStatus.COMPUTED,
        score=_mean(per_repeat),
        explanation=f"model-judged faithfulness over {len(per_repeat)} repeat(s)",
        details=details,
    )


# --- context relevance ----------------------------------------------------


_CONTEXT_RELEVANCE = EvaluatorSpec(
    id="rag.context_relevance",
    name="RAG Context Relevance",
    description=(
        "Mean relevance of retrieved context chunks to the question. "
        "Model-judged when a judge provider is configured; otherwise a "
        "deterministic lexical-overlap fallback labeled 'estimated'."
    ),
    version="1.0.0",
    provenance=Provenance.MODEL_JUDGED,
    value_kind=ValueKind.SCORE,
    scope="case",
    application_types=("rag",),
    capabilities_required=("exposes_retrieved_docs",),
)


def _overlap_context_relevance(inp: CaseEvalInput, spec: EvaluatorSpec) -> MetricValue:
    contexts, complete = _contexts(inp)
    if not contexts:
        return MetricValue.unavailable(
            spec, "retrieved context content not available for overlap fallback"
        )
    question = str(inp.case.case_input.get("input", ""))
    q_tokens = _tokens(question)
    if not q_tokens:
        return MetricValue.unavailable(spec, "case input is empty")
    per_chunk = []
    for c in contexts:
        c_tokens = _tokens(c)
        per_chunk.append(round(len(q_tokens & c_tokens) / len(q_tokens), 6))
    details: dict = {
        "method": "token_overlap_fallback",
        "per_chunk": per_chunk,
        "judge_model": None,
    }
    if not complete:
        details["coverage_note"] = "some repeats lacked document content"
    return MetricValue(
        evaluator_id=spec.id,
        evaluator_version=spec.version,
        provenance=Provenance.ESTIMATED,
        value_kind=spec.value_kind,
        status=MetricStatus.COMPUTED,
        score=_mean(per_chunk),
        explanation=(
            "deterministic overlap fallback (question tokens found in each "
            "chunk); LLM judge not configured"
        ),
        details=details,
    )


def _context_relevance(inp: CaseEvalInput) -> MetricValue:
    judge = build_judge(inp.config)
    if judge is None:
        return _overlap_context_relevance(inp, _CONTEXT_RELEVANCE)
    contexts, _ = _contexts(inp)
    if not contexts:
        return MetricValue.unavailable(
            _CONTEXT_RELEVANCE, "retrieved context content not available for judging"
        )
    question = str(inp.case.case_input.get("input", ""))
    return _judge_call(
        inp,
        JudgeRequest(kind="context_relevance", input=question, contexts=contexts),
        _CONTEXT_RELEVANCE,
    )


# --- answer relevance + LLM judge (Â§1) ------------------------------------


_ANSWER_RELEVANCE = EvaluatorSpec(
    id="rag.answer_relevance",
    name="RAG Answer Relevance",
    description=(
        "Does the answer address the question? Model-judged only; no "
        "deterministic fallback is defined for this metric, so it reports "
        "'unavailable' when no judge provider is configured."
    ),
    version="1.0.0",
    provenance=Provenance.MODEL_JUDGED,
    value_kind=ValueKind.SCORE,
    scope="case",
    application_types=("rag",),
)


def _answer_relevance(inp: CaseEvalInput) -> MetricValue:
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_ANSWER_RELEVANCE, "case execution did not succeed")
    question = str(inp.case.case_input.get("input", ""))
    output = successes[0].output or ""
    return _judge_call(
        inp,
        JudgeRequest(kind="answer_relevance", input=question, output=output),
        _ANSWER_RELEVANCE,
    )


_ANSWER_LLM_JUDGE = EvaluatorSpec(
    id="answer.llm_judge",
    name="LLM Judge Answer Quality",
    description=(
        "Judge-scored answer quality across configurable criteria "
        "(correctness, relevance, completeness, clarity), normalized to "
        "[0, 1]. Requires a configured judge provider; judge metadata "
        "(model, prompt version, per-criterion scores) is recorded. Judge "
        "outages produce 'unavailable', never a failed run."
    ),
    version="1.0.0",
    provenance=Provenance.MODEL_JUDGED,
    value_kind=ValueKind.SCORE,
    scope="case",
    application_types=("rag", "llm", "agent"),
    required_fields=("expected_output",),
    config_schema={"judge_model": {"type": "string", "required": False}},
)


def _answer_llm_judge(inp: CaseEvalInput) -> MetricValue:
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(_ANSWER_LLM_JUDGE, "case execution did not succeed")
    return _judge_call(
        inp,
        JudgeRequest(
            kind="answer_quality",
            input=str(inp.case.case_input.get("input", "")),
            output=successes[0].output or "",
            expected_output=inp.case.expected_output,
            contexts=[inp.case.reference_context] if inp.case.reference_context else None,
        ),
        _ANSWER_LLM_JUDGE,
    )


# --- citation metrics (measured) ------------------------------------------


def _citations(inp: CaseEvalInput) -> tuple[list[str], bool]:
    """Cited doc ids from successful repeats; second element = all reported."""
    cited: list[str] = []
    complete = True
    for r in inp.successful_repeats():
        if r.citations is None:
            complete = False
            continue
        cited.extend(r.citations)
    return cited, complete


def _citation_metric(inp: CaseEvalInput, spec: EvaluatorSpec, kind: str) -> MetricValue:
    if inp.case.relevant_doc_ids is None:
        return MetricValue.unavailable(spec, "case has no relevance labels (relevant_doc_ids)")
    relevant = set(inp.case.relevant_doc_ids)
    if kind == "coverage" and not relevant:
        return MetricValue.unavailable(
            spec, "case is labeled as having no relevant docs (empty relevant_doc_ids)"
        )
    successes = inp.successful_repeats()
    if not successes:
        return MetricValue.unavailable(spec, "case execution did not succeed")
    cited, complete = _citations(inp)
    if all(r.citations is None for r in successes):
        return MetricValue.unavailable(
            spec, "application did not report citations for this case"
        )
    scores = []
    per_repeat = []
    for r in successes:
        r_cited = set(r.citations or [])
        if kind == "precision":
            scores.append(len(r_cited & relevant) / len(r_cited) if r_cited else 0.0)
        else:
            scores.append(len(relevant & r_cited) / len(relevant))
        per_repeat.append(round(scores[-1], 6))
    details: dict = {
        "cited_doc_ids": cited,
        "relevant_count": len(relevant),
        "per_repeat": per_repeat,
    }
    if not complete:
        details["coverage_note"] = "some successful repeats did not report citations"
    return MetricValue(
        evaluator_id=spec.id,
        evaluator_version=spec.version,
        provenance=spec.provenance,
        value_kind=spec.value_kind,
        status=MetricStatus.COMPUTED,
        score=_mean(scores),
        explanation=(
            f"cited ids vs {len(relevant)} labeled relevant doc(s) over "
            f"{len(scores)} successful repeat(s)"
        ),
        details=details,
    )


_CITATION_CORRECTNESS = EvaluatorSpec(
    id="rag.citation_correctness",
    name="Citation Correctness",
    description=(
        "Precision of cited document ids against the labeled relevant set "
        "(fraction of citations that are relevant). Measured; unavailable "
        "without citations or relevance labels."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.SCORE,
    scope="case",
    application_types=("rag",),
    required_fields=("relevant_doc_ids",),
    capabilities_required=("exposes_citations",),
)


_CITATION_COVERAGE = EvaluatorSpec(
    id="rag.citation_coverage",
    name="Citation Coverage",
    description=(
        "Fraction of labeled relevant documents that are cited. Measured; "
        "unavailable when the relevant set is empty or citations are missing."
    ),
    version="1.0.0",
    provenance=Provenance.MEASURED,
    value_kind=ValueKind.SCORE,
    scope="case",
    application_types=("rag",),
    required_fields=("relevant_doc_ids",),
    capabilities_required=("exposes_citations",),
)


register(_FAITHFULNESS, _faithfulness)
register(_CONTEXT_RELEVANCE, _context_relevance)
register(_ANSWER_RELEVANCE, _answer_relevance)
register(_ANSWER_LLM_JUDGE, _answer_llm_judge)
register(
    _CITATION_CORRECTNESS,
    lambda inp: _citation_metric(inp, _CITATION_CORRECTNESS, "precision"),
)
register(
    _CITATION_COVERAGE,
    lambda inp: _citation_metric(inp, _CITATION_COVERAGE, "coverage"),
)
