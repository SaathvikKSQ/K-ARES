# K-AERS — Product Requirements

**Version:** 1.0.0 · **Status:** Draft for review

Source inputs: `Blueprint.txt` (K-ARES proposal) and the K-AERS master brief. Every requirement has an ID and is testable. **M** = mandatory for initial release; **F** = future enhancement (interface hooks only, not implemented now).

## 1. Goals

1. Provide a standardized, repeatable way to evaluate Ksquare AI applications instead of ad-hoc manual testing.
2. Measure answer quality, retrieval quality, reliability, latency, cost, and security, with honest provenance labeling (measured / estimated / model_judged).
3. Surface weaknesses (retrieval misses, ungrounded answers, wrong tool calls, security leaks) through a web dashboard with clear explanations.
4. Enable regression detection by comparing evaluation runs over time.
5. Remain extensible: new metrics, adapters, and evaluators plug in without engine rewrites.

## 2. Users & Use Cases

| User | Primary use cases |
|---|---|
| AI/ML engineer | Register apps, build datasets, run evaluations, inspect failures, iterate |
| Tech lead / QA | Review run results, compare versions, gate releases |
| Manager / stakeholder | Overview dashboard, trends, cost and reliability summaries |

## 3. Functional Requirements

### FR-A — AI Application Management (M)
- FR-A1: Register an application with name, description, application type (`rag` | `llm` | `agent`), integration type (`mock` | `rest_api` at MVP), connection configuration, and optional version label.
- FR-A2: Store authentication configuration securely (write-only via API; encrypted at rest; never returned in responses).
- FR-A3: Connection test endpoint that performs a safe, bounded connectivity check and reports success/failure with a sanitized reason.
- FR-A4: Enable/disable an application without deleting its evaluation history.
- FR-A5: Record declared capabilities per application (e.g., `exposes_retrieved_docs`, `exposes_traces`, `exposes_token_usage`, `streaming`, `exposes_citations`) derived from the adapter type + user confirmation; the engine uses capabilities to decide which metrics apply.
- FR-A6: Application versions (label, model name, prompt version, config hash) recorded per evaluation run.

### FR-B — Evaluation Dataset Management (M)
- FR-B1: Create, upload (JSONL/CSV), validate, edit (via new version), and version datasets.
- FR-B2: Test-case fields per specs/evaluation/dataset-format.md: id, input, expected answer (optional), reference context (optional), relevant source documents (optional), application type, category, expected tool/action (optional), expected structured output (optional), metadata/tags.
- FR-B3: Validation reports malformed rows with row numbers and reasons; invalid rows are stored with status `invalid`, never silently dropped.
- FR-B4: Evaluation is possible without reference answers where the selected metrics allow.
- FR-B5: Dataset versions are immutable; a run references the exact dataset version.
- FR-B6: Provide downloadable sample datasets (per application type) and a documented schema.

### FR-C — Evaluation Engine (M)
- FR-C1: Start a run with {application, dataset version, selected metrics, config: concurrency, per-case timeout, retries, repeat count, rate limit}.
- FR-C2: Validate configuration before execution; reject incompatible metric selections with an explanatory error.
- FR-C3: Execute cases with bounded concurrency, timeouts, and retries; capture inputs, outputs, references, errors, timings, token usage (if reported).
- FR-C4: Progress tracking (completed/total) and cancellation support.
- FR-C5: Per-case results and aggregates persisted; failures isolated per case.
- FR-C6: Run summary includes failure breakdown and improvement observations.

### FR-D — Metrics (M) — full definitions in specs/evaluation/metrics.md
Answer quality (exact match, token P/R/F1, semantic similarity when embeddings configured, reference-based correctness, LLM-judge), RAG retrieval (Precision@K, Recall@K, MRR, NDCG@K), RAG response (faithfulness, context relevance, answer relevance, citation correctness/coverage when citations exposed), reliability (success/error/timeout/malformed rates, consistency), performance (latency avg/median/P90/P95, TTFT if available, throughput, token usage), cost (estimated input/output/per-case/total from configurable pricing), agent (task completion, tool-selection accuracy, tool-call success, invalid/unnecessary calls, sequence match, final answer quality, duration & call count — only when traces are exposed), security (controlled suite: prompt injection, instruction override, sensitive-data disclosure, unsafe tool-use attempts, untrusted-content handling, output policy violations, robustness).
- FR-D1: Metrics with missing inputs are reported `unavailable`, never zero.
- FR-D2: Security results record category, expected behavior, observed behavior, verdict.

### FR-E — Metric & Evaluator Registry (M)
- FR-E1: Each evaluator declares: unique ID, name, description, applicable application types, required inputs, output schema, configuration options, error behavior, version.
- FR-E2: Engine computes applicability from adapter capabilities + dataset fields before running.
- FR-E3: New evaluators register via a single registration point; no engine edits required.

### FR-F — Runs & History (M)
- FR-F1: Persist runs with application/config version, dataset version, selected metrics + evaluator versions, timestamps, duration, status, aggregates, per-case results, errors, model/provider metadata, estimated cost.
- FR-F2: List runs with filtering (application, status, date range) and pagination.
- FR-F3: Compare two runs: metric deltas, regressions, newly failing / resolved cases.
- FR-F4: Export a run as JSON and CSV (per-case rows + aggregate section); reporting layer extensible to HTML/PDF (F).

### FR-G — Dashboard & UI (M)
Pages: Overview, Applications, Datasets, Evaluation Configuration, Evaluation Results, Run Comparison, Security Evaluation — per the master brief Module G, including progress states, unavailable-metric display, provenance labels, metric explanations, tables with search/filter/pagination, and charts only where they aid comparison. No hardcoded results (see constitution §2).

### FR-H — Reports & Export (M)
- FR-H1: JSON export: full structured run report.
- FR-H2: CSV export: one row per test case with metrics and outcomes.
- FR-H3: Reports include app/dataset info, config, metric definitions+results, failed cases, error summary, duration, cost estimates, versions.

## 4. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | Full local workflow runs via Docker Compose with a mock app; **no paid APIs required**. |
| NFR-2 | API p95 < 300 ms for list/detail endpoints at demo scale (<10k cases). |
| NFR-3 | Evaluation concurrency default 4, max 16; per-case timeout default 30 s (configurable). |
| NFR-4 | All secrets encrypted/masked; no secret appears in logs, API responses, or exports. |
| NFR-5 | Dataset upload limit 10 MB / 20,000 rows (configurable). |
| NFR-6 | Structured JSON logs with request IDs; health endpoints for API + worker. |
| NFR-7 | Frontend responsive down to 1280px desktop; usable at 1024px. |
| NFR-8 | Data retention configurable (days) for runs and artifacts; deletion cascades documented. |

## 5. Acceptance Snapshot (detailed criteria in specs/validation/test-plan.md)

A user can: launch locally → register mock app (connection test passes) → upload + validate a sample dataset → configure & start an evaluation → watch progress → view aggregate + per-case results with explanations → inspect failures (expected vs actual) → compare two runs → export JSON/CSV. All without paid external services.
