"""Phase 3: evaluator registry + applicability resolver (FR-E)."""

from __future__ import annotations

import pytest

from app.evaluation import registry
from app.evaluation.base import EvaluatorSpec
from app.evaluation.errors import UnknownEvaluatorError
from app.models.enums import Provenance, ValueKind


@pytest.fixture(autouse=True)
def _core_loaded():
    registry.ensure_loaded()
    yield


def _spec(**overrides) -> EvaluatorSpec:
    base = dict(
        id="test.metric",
        name="Test Metric",
        description="d",
        version="1.0.0",
        provenance=Provenance.MEASURED,
        value_kind=ValueKind.SCORE,
        scope="case",
    )
    base.update(overrides)
    return EvaluatorSpec(**base)


def _noop(inp) -> None:
    return None


def test_core_evaluators_registered():
    ids = [s.id for s in registry.list_specs()]
    for expected in (
        "answer.exact_match",
        "answer.token_f1",
        "answer.correctness",
        "reliability.success_rate",
        "reliability.error_rate",
        "reliability.timeout_rate",
        "reliability.malformed_rate",
        "reliability.consistency",
        "performance.latency",
        "performance.throughput",
        "performance.token_usage",
        "cost.estimated_total",
        "cost.estimated_per_case",
    ):
        assert expected in ids, expected


def test_specs_have_complete_metadata():
    for spec in registry.list_specs():
        assert spec.name and spec.description and spec.version
        assert spec.scope in ("case", "run")
        assert spec.provenance in (
            Provenance.MEASURED,
            Provenance.ESTIMATED,
            Provenance.MODEL_JUDGED,
        )


def test_register_duplicate_id_rejected():
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_spec(id="answer.exact_match"), _noop)


def test_register_invalid_id_rejected():
    with pytest.raises(ValueError):
        registry.register(_spec(id="nodomain"), _noop)
    with pytest.raises(ValueError):
        registry.register(_spec(id="UPPER.X"), _noop)


def test_register_invalid_scope_rejected():
    with pytest.raises(ValueError):
        registry.register(_spec(scope="bogus"), _noop)


def test_get_unknown_evaluator_raises():
    with pytest.raises(UnknownEvaluatorError):
        registry.get("does.not_exist")


def test_applicability_application_type_mismatch():
    spec = _spec(application_types=("rag",))
    reason = registry.resolve_applicability(
        spec,
        application_type="llm",
        capabilities={},
        available_fields=set(),
        valid_case_count=3,
    )
    assert reason is not None and "application type" in reason


def test_applicability_missing_capability():
    spec = _spec(capabilities_required=("exposes_token_usage",))
    reason = registry.resolve_applicability(
        spec,
        application_type="rag",
        capabilities={"exposes_token_usage": False},
        available_fields=set(),
        valid_case_count=3,
    )
    assert reason is not None and "exposes_token_usage" in reason


def test_applicability_missing_dataset_field():
    spec = _spec(required_fields=("expected_output",))
    reason = registry.resolve_applicability(
        spec,
        application_type="rag",
        capabilities={},
        available_fields={"input"},
        valid_case_count=2,
    )
    assert reason is not None and "expected_output" in reason


def test_applicability_no_valid_cases():
    reason = registry.resolve_applicability(
        _spec(),
        application_type="rag",
        capabilities={},
        available_fields=set(),
        valid_case_count=0,
    )
    assert reason is not None and "no valid" in reason


def test_applicability_satisfied_returns_none():
    spec = _spec(
        required_fields=("expected_output",),
        capabilities_required=("exposes_token_usage",),
    )
    reason = registry.resolve_applicability(
        spec,
        application_type="rag",
        capabilities={"exposes_token_usage": True},
        available_fields={"expected_output"},
        valid_case_count=1,
    )
    assert reason is None


def test_split_applicable_partitions():
    applicable, inapplicable = registry.split_applicable(
        ["answer.exact_match", "performance.token_usage"],
        application_type="rag",
        capabilities={"exposes_token_usage": True},
        available_fields={"expected_output"},
        valid_case_count=2,
    )
    assert applicable == ["answer.exact_match", "performance.token_usage"]
    assert inapplicable == []


def test_split_applicable_reports_inapplicable_reason():
    applicable, inapplicable = registry.split_applicable(
        ["answer.exact_match"],
        application_type="rag",
        capabilities={},
        available_fields={"input"},
        valid_case_count=2,
    )
    assert applicable == []
    assert len(inapplicable) == 1
    assert inapplicable[0]["id"] == "answer.exact_match"
    assert "expected_output" in inapplicable[0]["reason"]
