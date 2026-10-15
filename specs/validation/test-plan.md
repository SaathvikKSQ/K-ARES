# K-AERS — Test Plan & Validation Strategy

**Version:** 1.0.0 · **Status:** Draft for review

## 1. Principles

- Tests never call paid APIs. LLM judges and embedding models are stubbed/mocked.
- Deterministic fixtures: the mock adapter returns fixed outputs for known inputs.
- Every metric is validated against hand-computed expected values ("golden" fixtures).
- Failure paths are first-class tests, not afterthoughts.

## 2. Unit Tests (backend, pytest)

| Area | Cases |
|---|---|
| Metrics (each) | Known inputs → expected outputs; missing-reference → `unavailable` + reason; empty vs absent distinction; edge values (0, 1, empty lists); K bounds for @K metrics |
| Retrieval metrics | Hand-built rankings (e.g., 3 relevant of 10, known positions) → exact P@K, R@K, MRR, NDCG@K values; graded relevance variant |
| Cost | Known tokens × versioned pricing; missing tokens → partial coverage + label; unknown model → unavailable |
| Latency | Mean/median/P90/P95 with linear interpolation on crafted samples; excludes failed invocations |
| Dataset parsing/validation | Valid files; malformed JSONL line; CSV missing header; oversized file; duplicate ids; empty-input row; unknown columns → warnings; absent vs empty |
| Registry | Register/duplicate-id/version listing; applicability resolution vs capabilities + dataset fields |
| Engine | Timeout → `timeout` outcome; app error → isolated per-case failure; retry policy; cancel between cases; one evaluator crash → that metric unavailable, run continues |
| Aggregation | Known per-case scores → expected aggregates with n_computable |
| Comparison | Metric deltas, regression flags, newly failing / resolved case detection |
| Security utils | Redaction filter; Fernet round-trip; SSRF validator (private/loopback/scheme cases) |

## 3. Integration Tests (backend, TestClient + temp DB)

- App registration → credentials encrypted at rest, never in responses/logs.
- Connection test: success, failure, SSRF-blocked URL.
- Dataset upload → version creation; re-upload same bytes → same version id.
- Full evaluation run against mock app (small dataset, seeded randomness disabled) → results persisted, aggregates correct, reproducible re-run matches per-case ordering and versions.
- Cancellation mid-run → status `cancelled`, partial results retained and clearly marked.
- Worker/infrastructure failure simulation → run marked `failed` with infrastructure error class.
- Export JSON/CSV → schema and content match stored data; no secrets present.
- Auth: unauthenticated request → 401; viewer cannot create; role matrix.
- API error handling: 404 unknown ids, 422 incompatible metric selection, 409 duplicate name.

## 4. Failure-Handling Matrix (from Blueprint §18.4)

Application unavailable · timeout · invalid response schema · rate limit · worker failure · DB failure · evaluator failure · partially completed run · cancelled run · missing token usage. Each must map to the correct outcome/error classification without corrupting other results.

## 5. Frontend Tests (Vitest + React Testing Library)

- Applications: register form validation, connection-test states (running/success/failure), disabled state.
- Datasets: upload flow, validation error display with row numbers, version list, case preview with filters.
- Evaluation config: metric pickers disable/show reasons for inapplicable metrics; config bounds.
- Run pages: loading, empty, error states; progress polling; unavailable metrics render as "Unavailable — reason", provenance tags visible.
- Comparison: regression highlighting renders correctly.
- Security page: category results, verdicts, disclaimer present.
- Export buttons trigger downloads.

## 6. End-to-End Acceptance Test (critical workflow — Phase 6, Playwright)

1. Launch via Docker Compose; 2. Login; 3. Register mock application; 4. Connection test passes; 5. Download + upload sample dataset; 6. Validation report clean; 7. Configure + start evaluation (core metrics); 8. Progress reaches completed; 9. Aggregate + per-case results visible with explanations; 10. Open a failing case (expected vs actual shown); 11. Compare with second run (regression flagged); 12. Export JSON + CSV. **Runs entirely on mock services — no paid APIs.**

## 7. Acceptance Criteria per Phase

- P1: compose up healthy; auth works; health endpoint verifies DB; lint + tests green.
- P2: mock app registered + tested; secrets never visible; sample dataset validated with per-row errors; version dedupe works.
- P3: full run completes on mock app; case isolation verified; aggregates match golden fixtures; cancel works.
- P4: E2E steps 1–10 navigable in UI; comparison detects injected regression; exports match stored data.
- P5: retrieval metrics pass golden rankings; security suite produces per-category verdicts incl. `inconclusive`; judge metadata persisted.
- P6: failure-handling matrix green; NFR-2 benchmarked; clean-machine deployment documented; Definition of Done checklist verified.

## 8. Quality Gates

- `ruff check` + `mypy` (new code) + `pytest` (coverage ≥ 85% on evaluation/ and services/) backend.
- `tsc --noEmit` + `vitest` frontend.
- No TODO/FIXME in merged phase code without a tracking note in the phase report.
