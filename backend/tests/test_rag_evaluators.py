"""Phase 5: RAG response metrics â€” fallbacks, judge paths, citations (T5.2)."""

from __future__ import annotations

from app.evaluation import registry
from app.evaluation.base import CaseData, CaseEvalInput, RepeatRecord
from app.evaluation.judge import ACTIVE_PROMPT_VERSION, JudgeResult
from app.models.enums import CaseOutcome, MetricStatus, Provenance

registry.ensure_loaded()


def _case(doc_ids=None, expected=None, reference=None) -> CaseData:
    return CaseData(
        id="case-1",
        position=1,
        case_input={"input": "What is the refund window?"},
        expected_output=expected,
        reference_context=reference,
        relevant_doc_ids=doc_ids,
    )


def _repeat(output=None, docs=None, citations=None, outcome=CaseOutcome.SUCCESS):
    return RepeatRecord(
        repeat_index=0,
        outcome=outcome,
        output=output,
        retrieved_documents=docs,
        citations=citations,
    )


def _value(metric_id, case, repeats, config=None):
    _, fn = registry.get(metric_id)
    return fn(CaseEvalInput(case=case, repeats=repeats, config=config or {}))


DOCS = [
    {"doc_id": "d1", "content": "The refund window for premium plans is 30 days."},
    {"doc_id": "d2", "content": "Free plans are not refundable at all."},
]


def test_faithfulness_fallback_supported():
    case = _case(doc_ids=["d1", "d2"])
    value = _value(
        "rag.faithfulness",
        case,
        [_repeat(output="The refund window is 30 days.", docs=DOCS)],
    )
    assert value.status == MetricStatus.COMPUTED
    assert value.provenance == Provenance.ESTIMATED
    assert value.score == 1.0
    assert value.details["method"] == "claim_check_fallback"
    assert value.details["judge_model"] is None


def test_faithfulness_fallback_partial_support():
    case = _case(doc_ids=["d1", "d2"])
    value = _value(
        "rag.faithfulness",
        case,
        [_repeat(output="The refund window is 30 days. Unicorns dance nightly.", docs=DOCS)],
    )
    # sentence 1 supported; sentence 2 has zero overlap -> unsupported
    assert abs(value.score - 0.5) < 1e-9


def test_faithfulness_judged_with_mock_judge():
    class Judge:
        def evaluate(self, request):
            assert request.kind == "faithfulness"
            return JudgeResult(
                overall=0.75,
                explanation="two of three claims",
                model="mock-judge",
                prompt_version=ACTIVE_PROMPT_VERSION,
                scores={"claims": []},
            )

    case = _case(doc_ids=["d1", "d2"])
    value = _value(
        "rag.faithfulness",
        case,
        [_repeat(output="x", docs=DOCS)],
        config={"judge_provider": Judge()},
    )
    assert value.status == MetricStatus.COMPUTED
    assert value.provenance == Provenance.MODEL_JUDGED
    assert abs(value.score - 0.75) < 1e-9
    assert value.details["judge_model"] == "mock-judge"
    assert value.details["judge_prompt_version"] == ACTIVE_PROMPT_VERSION


def test_faithfulness_unavailable_without_context_content():
    case = _case(doc_ids=["d1"])
    value = _value("rag.faithfulness", case, [_repeat(output="x", docs=None)])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "context content not available" in value.unavailable_reason


def test_context_relevance_overlap_fallback():
    case = _case(doc_ids=["d1", "d2"])
    value = _value("rag.context_relevance", case, [_repeat(output="x", docs=DOCS)])
    assert value.status == MetricStatus.COMPUTED
    assert value.provenance == Provenance.ESTIMATED
    assert 0.0 < value.score < 1.0
    assert len(value.details["per_chunk"]) == 2


def test_answer_relevance_unavailable_without_judge():
    value = _value("rag.answer_relevance", _case(), [_repeat(output="x")])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "judge not configured" in value.unavailable_reason


def test_answer_relevance_computed_with_judge():
    class Judge:
        def evaluate(self, request):
            assert request.kind == "answer_relevance"
            return JudgeResult(
                overall=0.8,
                explanation="ok",
                model="m",
                prompt_version="1.0.0",
                scores={"score": 4},
            )

    value = _value(
        "rag.answer_relevance",
        _case(),
        [_repeat(output="x")],
        config={"judge_provider": Judge()},
    )
    assert value.status == MetricStatus.COMPUTED
    assert abs(value.score - 0.8) < 1e-9


def test_failed_execution_unavailable():
    case = _case(doc_ids=["d1"])
    value = _value(
        "rag.faithfulness",
        case,
        [_repeat(outcome=CaseOutcome.APPLICATION_ERROR)],
    )
    assert value.status == MetricStatus.UNAVAILABLE
# --- citation metrics (measured) ---


def test_citation_correctness_hand_computed():
    # cited {d1, d9}; relevant {d1, d2} -> precision 1/2
    case = _case(doc_ids=["d1", "d2"])
    value = _value(
        "rag.citation_correctness",
        case,
        [_repeat(output="x", citations=["d1", "d9"])],
    )
    assert value.status == MetricStatus.COMPUTED
    assert abs(value.score - 0.5) < 1e-9


def test_citation_coverage_hand_computed():
    # cited {d1}; relevant {d1, d2} -> coverage 1/2
    case = _case(doc_ids=["d1", "d2"])
    value = _value("rag.citation_coverage", case, [_repeat(output="x", citations=["d1"])])
    assert abs(value.score - 0.5) < 1e-9


def test_citation_metrics_unavailable_without_labels():
    case = _case(doc_ids=None)
    value = _value("rag.citation_correctness", case, [_repeat(output="x", citations=["d1"])])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "relevant_doc_ids" in value.unavailable_reason


def test_citation_metrics_unavailable_when_not_reported():
    case = _case(doc_ids=["d1"])
    value = _value("rag.citation_coverage", case, [_repeat(output="x", citations=None)])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "did not report citations" in value.unavailable_reason


def test_citation_coverage_unavailable_with_empty_labels():
    case = _case(doc_ids=[])
    value = _value("rag.citation_coverage", case, [_repeat(output="x", citations=["d1"])])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "no relevant docs" in value.unavailable_reason

