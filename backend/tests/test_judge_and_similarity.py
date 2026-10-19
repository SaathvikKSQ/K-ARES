"""Phase 5: semantic similarity + judge module (T5.6, T5.3)."""

from __future__ import annotations

import pytest

from app.evaluation import registry
from app.evaluation.base import CaseData, CaseEvalInput, RepeatRecord
from app.evaluation.judge import (
    ACTIVE_PROMPT_VERSION,
    JudgeRequest,
    JudgeResult,
    JudgeUnavailableError,
)
from app.models.enums import CaseOutcome, MetricStatus, Provenance

registry.ensure_loaded()


def _case(expected="Paris is the capital") -> CaseData:
    return CaseData(
        id="case-1", position=1, case_input={"input": "q"}, expected_output=expected
    )


def _repeat(output="Paris is the capital", outcome=CaseOutcome.SUCCESS) -> RepeatRecord:
    return RepeatRecord(repeat_index=0, outcome=outcome, output=output)


# --- similarity ------------------------------------------------------------


def _embed(text: str) -> list[float]:
    # Deterministic stub: bag-of-char-bigrams unit vector space (simple + stable).
    text = text.lower()
    return [
        1.0 if c in text else 0.0
        for c in "pariscapitalberlinvalid"
    ]


def test_similarity_identical_outputs():
    _, fn = registry.get("answer.semantic_similarity")
    value = fn(
        CaseEvalInput(
            case=_case(),
            repeats=[_repeat()],
            config={"embedding_model": "stub", "embedding_fn": _embed},
        )
    )
    assert value.status == MetricStatus.COMPUTED
    assert value.score == 1.0


def test_similarity_partial_overlap():
    _, fn = registry.get("answer.semantic_similarity")
    value = fn(
        CaseEvalInput(
            case=_case(),
            repeats=[_repeat(output="Berlin is the capital")],
            config={"embedding_model": "stub", "embedding_fn": _embed},
        )
    )
    assert 0.0 < value.score < 1.0


def test_similarity_gated_without_embedding_model():
    _, fn = registry.get("answer.semantic_similarity")
    value = fn(CaseEvalInput(case=_case(), repeats=[_repeat()]))
    assert value.status == MetricStatus.UNAVAILABLE
    assert "embedding model not configured" in value.unavailable_reason


def test_similarity_unavailable_without_label():
    _, fn = registry.get("answer.semantic_similarity")
    value = fn(
        CaseEvalInput(
            case=_case(expected=None),
            repeats=[_repeat()],
            config={"embedding_model": "stub", "embedding_fn": _embed},
        )
    )
    assert value.status == MetricStatus.UNAVAILABLE


# --- judge module ----------------------------------------------------------


class MockJudge:
    """Deterministic mock judge (used in CI; no network)."""

    def __init__(self, overall=0.8, fail=False):
        self.overall = overall
        self.fail = fail

    def evaluate(self, request: JudgeRequest) -> JudgeResult:
        if self.fail:
            raise JudgeUnavailableError("judge outage")
        return JudgeResult(
            overall=self.overall,
            explanation="mock",
            model="mock-judge-1",
            prompt_version=ACTIVE_PROMPT_VERSION,
            scores={"chunk_scores": [4]},
        )


def test_judge_request_prompt_selection():
    from app.evaluation.judge import PROMPTS

    for kind in ("faithfulness", "context_relevance", "answer_relevance", "answer_quality"):
        assert kind in PROMPTS[ACTIVE_PROMPT_VERSION]


def test_mock_judge_metadata():
    result = MockJudge().evaluate(JudgeRequest(kind="context_relevance"))
    meta = result.metadata()
    assert meta["judge_model"] == "mock-judge-1"
    assert meta["judge_prompt_version"] == ACTIVE_PROMPT_VERSION
    assert "judge_scores" in meta


def test_openai_judge_normalizes_faithfulness():
    from app.evaluation.judge import OpenAICompatibleJudge

    judge = OpenAICompatibleJudge(base_url="http://x", model="m")
    parsed = {
        "claims": [{"text": "a", "supported": True}, {"text": "b", "supported": False}],
        "explanation": "half",
    }
    result = judge._normalize("faithfulness", parsed, raw={})
    assert result.overall == 0.5
    assert result.model == "m"


def test_openai_judge_malformed_payload_raises():
    from app.evaluation.judge import OpenAICompatibleJudge

    judge = OpenAICompatibleJudge(base_url="http://x", model="m")
    with pytest.raises(JudgeUnavailableError):
        judge._normalize("context_relevance", {"chunk_scores": ["abc"]}, raw={})


@pytest.mark.parametrize("provenance_expected", [Provenance.MODEL_JUDGED])
def test_llm_judge_metric_uses_injected_provider(provenance_expected):
    _, fn = registry.get("answer.llm_judge")
    value = fn(
        CaseEvalInput(
            case=_case(),
            repeats=[_repeat()],
            config={"judge_provider": MockJudge(overall=0.9)},
        )
    )
    assert value.status == MetricStatus.COMPUTED
    assert value.provenance == Provenance.MODEL_JUDGED
    assert abs(value.score - 0.9) < 1e-9
    assert value.details["judge_model"] == "mock-judge-1"


def test_llm_judge_unavailable_without_provider():
    _, fn = registry.get("answer.llm_judge")
    value = fn(CaseEvalInput(case=_case(), repeats=[_repeat()]))
    assert value.status == MetricStatus.UNAVAILABLE
    assert "judge not configured" in value.unavailable_reason


def test_llm_judge_unavailable_on_outage():
    _, fn = registry.get("answer.llm_judge")
    value = fn(
        CaseEvalInput(
            case=_case(),
            repeats=[_repeat()],
            config={"judge_provider": MockJudge(fail=True)},
        )
    )
    assert value.status == MetricStatus.UNAVAILABLE
    assert "outage" in value.unavailable_reason
