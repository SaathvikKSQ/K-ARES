# K-AERS — Implementation Tasks

**Version:** 1.0.0 · **Status:** Draft for review

Ordered tasks with dependencies. Each phase ends with passing tests + a working app + phase report. IDs map to FRs in requirements.md.

## Phase 1 — Foundation (no dependencies)
- T1.1 Repository scaffolding: backend (uv/pip + pyproject.toml, ruff, pytest) and frontend (Vite + React + TS) skeletons; `.env.example`; Makefile/scripts. [FR-*]
- T1.2 Core modules: settings (pydantic-settings), structured logging + redaction filter, request-id middleware, exception handlers → standard error envelope. [NFR-4, NFR-6]
- T1.3 DB: SQLAlchemy models per data-model.md, Alembic initial migration, session management; SQLite profile for tests. [FR-F1]
- T1.4 Auth MVP: users table, login/logout/me, role dependency, seeding script for initial admin. [SR-1–SR-4]
- T1.5 API skeleton + `GET /health`; CORS; frontend shell with routing, layout, navigation, design tokens. [FR-G]
- T1.6 Docker Compose: api, db, web; healthchecks; README quickstart. [NFR-1]
- T1.7 Test infrastructure: pytest fixtures (temp DB, TestClient), Vitest setup; CI-able commands.
- **Acceptance P1:** compose up → healthy api/db/web; login works; health returns DB status; lint+tests green; skeleton pages render.

## Phase 2 — Applications & Datasets (depends P1)
- T2.1 Application service + API: register/list/get/patch/enable-disable; capability flags; credential encryption (Fernet) + write-only semantics. [FR-A1–A6, SR-8–SR-9]
- T2.2 Integration contract: `TargetAdapter` protocol + capabilities; `MockAdapter` (deterministic, configurable latency/failures); SSRF-validated `RestAdapter` with timeouts/retries/limits. [FR-A5, SR-15–SR-17]
- T2.3 Connection test endpoint (safe check + sanitized result). [FR-A3]
- T2.4 Dataset service + API: upload (JSONL/CSV), parser, validator (row-level errors), versioning (immutable, content-hash dedupe), sample datasets bundled. [FR-B1–B6]
- T2.5 Storage layer: local artifact store (`DATA_DIR`), sha256, size/row caps. [SR-12–SR-14]
- T2.6 Frontend: Applications pages (list, register wizard, connection test, detail), Datasets pages (list, upload with validation report, version list, case preview table with filters). [FR-G]
- **Acceptance P2:** register mock app; test-connection succeeds/fails sanely; secrets never visible in API/logs; upload sample-rag-qa → validation report; invalid rows visible as invalid; second upload of same file reuses version.

## Phase 3 — Evaluation Engine Core (depends P2)
- T3.1 Evaluator registry + EvaluatorSpec + applicability resolver (capabilities + dataset fields). [FR-E]
- T3.2 Core evaluators: reliability.*, performance.latency/throughput, answer.exact_match, answer.token_f1, answer.correctness. [FR-D]
- T3.3 Engine orchestration: plan → execute (concurrency, timeout, retry, rate limit, repeats) → evaluate → persist via ports; error taxonomy; cooperative cancellation; progress events. [FR-C]
- T3.4 Background runner (thread pool + DB claim of queued runs); run lifecycle statuses. [FR-C]
- T3.5 Cost module: versioned pricing table, per-case/total estimates, coverage reporting. [FR-D6]
- T3.6 Runs API: start (validate + 202), list/filter, detail, results, cancel; aggregation into summary_metrics. [FR-F]
- T3.7 Frontend: Evaluation configuration page (app/dataset/metric pickers with applicability preview + config), Run detail with live progress + aggregate cards + failed-case list. [FR-G]
- **Acceptance P3:** full run against mock app completes; one failing case does not affect others; unavailable metrics shown as unavailable; cancel works; aggregates match hand-computed fixture values.

## Phase 4 — Dashboard Completion (depends P3)
- T4.1 Overview page: counts, recent runs, status breakdown, key metric summaries, recent failures — all from real data. [FR-G1]
- T4.2 Result detail views: expected vs actual, references, traces, per-metric explanations, provenance tags. [FR-G5]
- T4.3 Run comparison: select two runs → metric deltas w/ regression highlighting, newly failing/resolved cases, latency/cost deltas. [FR-F3]
- T4.4 Charts (Recharts) where they aid comparison (metric bars, latency trend); tables with search/filter/pagination everywhere. [FR-G]
- T4.5 Export JSON/CSV from UI + API; report structure per FR-H. [FR-H]
- **Acceptance P4:** E2E flow §8 steps 1–10 passable in UI; comparison flags an injected regression correctly; exports download and match stored data.

## Phase 5 — Advanced Evaluators (depends P3)
- T5.1 RAG retrieval metrics (precision/recall@K, MRR, NDCG@K) + retrieval-exposure handling. [FR-D]
- T5.2 RAG response metrics: faithfulness, context relevance, answer relevance (judge-based with mockable judge; deterministic fallback where defined), citation correctness/coverage. [FR-D]
- T5.3 LLM-as-a-judge module: pluggable provider (OpenAI-compatible), prompt versions, persistence of judge metadata; disabled unless configured. [FR-D]
- T5.4 Agent metrics: task completion, tool selection accuracy, tool-call success, invalid/unnecessary calls, sequence match, duration/count. [FR-D]
- T5.5 Security suites: static versioned payload sets (8 categories), execution integration, verdict rules incl. `inconclusive`, Security page UI with covered/untested disclosure. [FR-D8, SR-23–SR-25]
- T5.6 Semantic similarity evaluator (gated on configured embedding model; stub in tests). [FR-D]
- **Acceptance P5:** retrieval metrics verified against hand-built rankings; judge mocked in CI; security suite runs against mock app with per-category verdicts; unavailable paths all report reasons.

## Phase 6 — Hardening & Deployment (depends P3–P5)
- T6.1 Auth hardening: rate limiting, security headers, CORS lockdown, session expiry. [SR-4, SR-26, SR-27]
- T6.2 Performance checks: pagination benchmarks, concurrency limits, NFR-2 validation.
- T6.3 Regression test pack: golden fixtures for all metrics; failure-handling matrix (timeout, app down, malformed, worker kill, cancel). [test-plan §4]
- T6.4 Production docs: deployment guide, env reference, data-flow/privacy statement, security limitations. [SR-19, SR-25, SR-30]
- T6.5 Final SDD review: spec-vs-implementation traceability pass.
- **Acceptance P6:** Definition of Done checklist green; compose deployment from clean machine documented and verified.

## Dependency Graph

P1 → P2 → P3 → {P4, P5} → P6. P4 and P5 may proceed in parallel after P3.
