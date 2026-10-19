"""Phase 5: retrieval metrics verified against hand-built rankings (T5.1)."""

from __future__ import annotations

import math

from app.evaluation import registry
from app.evaluation.base import CaseData, CaseEvalInput, RepeatRecord
from app.models.enums import CaseOutcome, MetricStatus

registry.ensure_loaded()


def _case(doc_ids) -> CaseData:
    return CaseData(
        id="case-1", position=1, case_input={"input": "q"}, relevant_doc_ids=doc_ids
    )


def _repeat(ranked=None, outcome=CaseOutcome.SUCCESS) -> RepeatRecord:
    return RepeatRecord(repeat_index=0, outcome=outcome, retrieved_document_ids=ranked)


def _value(metric_id, case, repeats, config=None):
    _, fn = registry.get(metric_id)
    return fn(CaseEvalInput(case=case, repeats=repeats, config=config or {}))


def test_precision_at_k_hand_computed():
    # ranking [d1,d3,d2,d4,d5,d6], relevant {d1,d2}, k=5 -> 2/5
    value = _value(
        "retrieval.precision_at_k",
        _case(["d1", "d2"]),
        [_repeat(["d1", "d3", "d2", "d4", "d5", "d6"])],
        config={"k": 5},
    )
    assert value.status == MetricStatus.COMPUTED
    assert abs(value.score - 0.4) < 1e-9


def test_recall_at_k_hand_computed():
    value = _value(
        "retrieval.recall_at_k",
        _case(["d1", "d2", "d9"]),
        [_repeat(["d1", "d3", "d2", "d4", "d5"])],
        config={"k": 5},
    )
    assert abs(value.score - 2 / 3) < 1e-5  # d1, d2 found; d9 missing


def test_mrr_first_position():
    value = _value("retrieval.mrr", _case(["d1"]), [_repeat(["d1", "d2"])])
    assert value.score == 1.0


def test_mrr_second_position():
    value = _value("retrieval.mrr", _case(["d2"]), [_repeat(["d1", "d2", "d3"])])
    assert abs(value.score - 0.5) < 1e-9


def test_mrr_zero_when_no_relevant_retrieved():
    value = _value("retrieval.mrr", _case(["d2"]), [_repeat(["x", "y"])])
    assert value.score == 0.0


def test_ndcg_perfect_ranking():
    value = _value(
        "retrieval.ndcg_at_k",
        _case(["d1", "d2"]),
        [_repeat(["d1", "d2", "d3", "d4", "d5"])],
        config={"k": 5},
    )
    assert abs(value.score - 1.0) < 1e-9


def test_ndcg_imperfect_ranking():
    value = _value(
        "retrieval.ndcg_at_k",
        _case(["d1", "d2"]),
        [_repeat(["d3", "d1", "d2", "d4", "d5"])],
        config={"k": 5},
    )
    expected = (1 / math.log2(3) + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    assert abs(value.score - expected) < 1e-5


def test_mean_over_repeats():
    case = _case(["d1"])
    repeats = [_repeat(["d1", "x"]), _repeat(["x", "y"])]
    value = _value("retrieval.mrr", case, repeats)
    assert abs(value.score - 0.5) < 1e-9
    assert value.details["per_repeat"] == [1.0, 0.0]


def test_unavailable_without_labels():
    value = _value("retrieval.precision_at_k", _case(None), [_repeat(["d1"])])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "relevant_doc_ids" in value.unavailable_reason


def test_unavailable_without_exposed_docs():
    value = _value("retrieval.recall_at_k", _case(["d1"]), [_repeat(ranked=None)])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "did not expose" in value.unavailable_reason


def test_unavailable_when_execution_failed():
    value = _value("retrieval.mrr", _case(["d1"]), [_repeat(outcome=CaseOutcome.TIMEOUT)])
    assert value.status == MetricStatus.UNAVAILABLE
    assert "did not succeed" in value.unavailable_reason


def test_empty_labels_precision_zero_but_recall_unavailable():
    case = _case([])  # labeled empty
    precision = _value("retrieval.precision_at_k", case, [_repeat(["d1"])])
    assert precision.status == MetricStatus.COMPUTED and precision.score == 0.0
    recall = _value("retrieval.recall_at_k", case, [_repeat(["d1"])])
    assert recall.status == MetricStatus.UNAVAILABLE
    assert "no relevant docs" in recall.unavailable_reason
    mrr = _value("retrieval.mrr", case, [_repeat(["d1"])])
    assert mrr.status == MetricStatus.COMPUTED and mrr.score == 0.0
