# Phase 5 Implementation Report — Advanced Evaluators

**Tasks:** T5.1–T5.6 · **Status:** Complete · **Tests:** backend 177 pytest passed
(69 new), ruff clean; frontend vitest 10/10, `tsc -b` + `npm run build` clean.

## Backend (`backend/app/evaluation/`)

- **T5.3 Judge module (`judge.py`)**: `JudgeProvider` protocol, versioned prompts
  (`PROMPTS`, `ACTIVE_PROMPT_VERSION="1.0.0"`), `OpenAICompatibleJudge`
  (chat/completions, temperature 0, JSON-only, bounded prompt sizes) with
  strict payload normalization; `JudgeUnavailableError` → evaluators emit
  `unavailable` (judge outage never fails a run). `build_judge(config)`
  resolution: injected provider (tests/CI) → `JUDGE_MODEL`+`JUDGE_PROVIDER_URL`
  settings → disabled (`None`). Judge metadata (model, prompt version,
  per-criterion scores, explanation) persisted in metric `details`.
  New settings: `judge_model`, `judge_provider_url`, `judge_api_key`,
  `embedding_model`.
- **T5.1 Retrieval (`evaluators/retrieval.py`)**: `precision_at_k`,
  `recall_at_k`, `mrr`, `ndcg_at_k` (binary gains; graded labels not in the v1
  dataset format — documented). Per successful repeat, mean over repeats,
  `k` configurable (default 5). Exposure handling: labels absent → unavailable
  `relevant_doc_ids`; docs not exposed → unavailable; labeled-empty set →
  precision 0.0 / MRR 0.0, recall + NDCG explicitly unavailable.
- **T5.2 RAG response (`evaluators/rag.py`)**: `rag.faithfulness` (judge →
  `model_judged`; deterministic sentence-level claim-check fallback →
  `estimated`), `rag.context_relevance` (judge → token-overlap fallback →
  `estimated`), `rag.answer_relevance` (judge only; unavailable without), and
  `answer.llm_judge` (§1 criteria scoring). Measured citation metrics:
  `rag.citation_correctness` (precision of cited ids vs relevant set) and
  `rag.citation_coverage`. All unavailable paths carry explicit reasons.
- **T5.4 Agent (`evaluators/agent.py`)**: `task_completion` (output match
  and/or expected final action), `tool_selection_accuracy` (position tolerance
  config), `tool_call_success_rate`, `invalid_tool_calls` (allowed set =
  expected tool ∪ `tool_allowlist`), `unnecessary_tool_calls`
  (`allow_exploratory` default true; details report both counts),
  `action_sequence_match` (LCS ratio), `execution_duration`,
  `tool_call_count`. Traces-not-exposed → unavailable (never fabricated).
- **T5.6 Similarity (`evaluators/similarity.py`)**: `answer.semantic_similarity`
  — cosine mapped to [0,1]; gated on `EMBEDDING_MODEL`/per-run
  `embedding_model`; embeddings via injectable `embedding_fn` (deterministic
  stubs in tests). Engine passes per-evaluator config
  (`{**run_config, **selection.config}`) to case evaluators now.
- **T5.5 Security suite (`evaluation/security/`)**: static versioned payload
  set `suites/v1.py` (suite `core` v1: 14 payloads across 8 categories,
  harmless/synthetic), deterministic verdict rules in `suite.py`
  (pass/fail/**inconclusive**; ambiguous never passes; failed execution →
  fail for robustness_input, inconclusive otherwise), `security.verdict`
  registered evaluator (score 1.0/0.0/null), `build_security_cases()` and
  engine auto-append when `run_config.include_security_suite` (RunConfigIn
  field added; `security.verdict` auto-selected). `security.verdict` example
  results against the mock adapter include all three verdict kinds.
  **`GET /api/v1/security/suites`** serves the catalog + mandatory disclaimer
  (auth-gated, registered in `main.py`).

## Plumbing

- `RepeatRecord` gained `retrieved_documents` (doc_id+content) and `citations`;
  engine persists them from `AdapterResponse`; mock adapter emits doc content
  and citations only under the respective capabilities (nothing fabricated).
- `CaseData` gained `reference_context`, `expected_action_sequence` (mapped in
  `DbEnginePorts.load_plan`).

## Frontend

- **`SecurityPage.tsx`** (replaces the Phase-3 placeholder, route `/security`),
  phase 5 disclaimer banner, "Not covered by this suite" static disclosure
  (SR-25). `services/security.ts` + `SecurityCatalog` types.
  **NewEvaluationPage**: "Include controlled security suite" checkbox →
  `include_security_suite` in the run payload.

## Verification

- Retrieval metrics verified against hand-built rankings (T5.1 fixtures);
  judge mocked in CI via injected providers (no network); security suite runs
  against the mock adapter per-category including `inconclusive` verdicts;
  every unavailable path asserts an explicit reason.
- New test files: `test_retrieval_evaluators.py`, `test_rag_evaluators.py`,
  `test_agent_evaluators.py`, `test_judge_and_similarity.py`,
  `test_security_suite.py` (incl. API + engine-integration tests);
  `SecurityPage.test.tsx`.

## Notes / Deferred

- Graded NDCG gains need richer dataset labels (v1 format is binary).
- Real (non-mock) judge/embedding providers require external endpoints;
  unit tests stay deterministic via injection.
- Bundle-size warning from Phase 4 still deferred.