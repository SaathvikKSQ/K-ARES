# K-AERS — Phase 3 Report (Evaluation Engine Core)

**Date:** 2026-10-17 · **Status:** Complete · **Scope:** T3.1–T3.4 + runs/results API + frontend per `specs/implementation/tasks.md`

## Delivered

### Backend — evaluation core (`app/evaluation/`)
- **Value objects** (`base.py`): `EvaluatorSpec` (id/name/version/provenance/value_kind/scope/application_types/required_fields/capabilities_required/config_schema), `MetricValue` (status computed/unavailable, `unavailable_reason`, explanation, details; `to_dict()` for persistence), `RepeatRecord` (one adapter invocation: outcome, output, latency, ttft, token usage, retrieved doc ids, agent trace, sanitized error), `CaseData`, `CaseEvalInput`/`RunEvalInput`, `EvaluatorFn` protocol. Missing inputs yield `status=unavailable` — the engine never fabricates values (constitution §2.2/D4).
- **Error taxonomy** (`errors.py`): `UnknownEvaluatorError`/`RunConfigError` → 400, `ApplicabilityError` → 422, `InvalidRunStateError` → 409; engine-internal failures are caught, logged, and reduced to `{error_type, "unexpected engine error"}` (no internals leaked).
- **Registry** (`registry.py`): single registration point `register(spec, fn)` with id-format (`domain.name`), scope and duplicate validation; `resolve_applicability` (FR-E2: application-type match → valid-case count → capability flags → dataset field availability with absent-vs-empty semantics); `split_applicable` partitions a selection into applicable ids and `{id, reason}` entries; `ensure_loaded()` imports the evaluators package.

- **Core evaluators** (`evaluators/`, T3.2, 13 metrics, all version 1.0.0):
  - `answer.exact_match` (measured; normalized fraction of successful repeats), `answer.token_f1` (measured; mean token-level F1), `answer.correctness` (**estimated** heuristic token-F1 until an LLM judge model is configured; requesting `judge_model` config makes it explicitly unavailable rather than heuristic).
  - `reliability.success_rate` / `error_rate` / `timeout_rate` (over all invocations), `reliability.malformed_rate` (over successful invocations), `reliability.consistency` (unavailable unless some case has >1 successful repeat).
  - `performance.latency` (mean + p50/p95/min/max nearest-rank), `performance.throughput` (executions/second of wall time), `performance.token_usage` (requires `exposes_token_usage`).
  - `cost.estimated_total` / `cost.estimated_per_case` (**estimated**; versioned pricing table `pricing.py` `PRICING_VERSION=2026-10`, USD per 1M tokens; unavailable without usage/model/pricing entry — no invented numbers).
- **Engine** (`engine.py`, T3.3): plan → execute → evaluate → persist over hexagonal ports (`ports.py`: `RunPlan`, `EnginePorts`). Per case: `repeats` invocations × timeout (`asyncio.wait_for`) × `max_retries` retries on timeout/application error, global rate limiter, concurrency semaphore. Case-scope evaluators run per case and are persisted immediately; run-scope evaluators compute aggregates over all recorded cases at finish. Failure isolation: a failing case's metrics become unavailable, other cases proceed. Cooperative cancellation (FR-C5): cancel checked before each case; remaining cases recorded as skipped and the run finishes `cancelled` (no summary). Progress persisted after every case (FR-C6). Engine failures finish the run `failed` with a sanitized error summary.
- **Runner** (`runner.py`, T3.4): single daemon thread polling for the oldest `queued` run, claiming it with a conditional `UPDATE ... WHERE status='queued'` (no double execution), then executing via the engine. Lifespan-managed (`start_worker` before `yield`, `stop_worker` on shutdown); `RUN_WORKER_ENABLED` / `RUN_POLL_INTERVAL_S` settings (disabled in tests for determinism).

### Backend — service + API
- **`app/schemas/run.py`**: `RunConfigIn` (concurrency 1–16, timeout 1000–300000 ms, retries 0–3, repeats 1–5, rate limit 0–100 rps), `RunCreate`, `ValidateConfigIn`, `MetricSpecOut`, `MetricValueOut`, `RunSummaryOut`, `RunDetailOut`, `CaseResultOut`/`CaseResultDetailOut`, `PageOut`.
- **`app/services/run_service.py`**: run creation validates application (enabled), dataset version (latest when unspecified), metric ids (registry), and applicability → **422 with per-metric reasons**; pins `configuration_snapshot` (sanitized app config incl. capabilities, dataset version + content hash, metric versions) and `application_config_id` so runs are reproducible (D10); list/detail/results/detail-result serialization; `cancel_run` (queued → cancelled directly; running → sets `error_summary.cancel_requested` flag + warning event; terminal runs → 409); `claim_next_queued_run`; `DbEnginePorts` (per-call short-lived sessions; per-case `TestResult`+`MetricResult` persistence with progress updates + `run_events`; terminal `finish` persists `summary_metrics`, `cost_summary`, `model_metadata`, duration, terminal event).
- **`app/api/routes/evaluations.py`** (contract routes, auth-gated): `GET /metrics`, `POST /evaluations/validate-config` (editor+), `POST /evaluations` → **202 + queued** (editor+), `GET /evaluations` (page/status/date filters, `?status=` alias), `GET /evaluations/{id}`, `GET /evaluations/{id}/results` (outcome/evaluator/search filters), `GET /evaluations/{id}/results/{id}`, `POST /evaluations/{id}/cancel` → 202 (editor+). Wired in `main.py`.
- **No migration needed**: `evaluation_runs`/`test_results`/`metric_results`/`run_events` existed in the Phase 0 initial schema and proved complete for T3.1–T3.4.

### Frontend
- Typed service `src/services/evaluations.ts` + Phase 3 types in `src/types/api.ts` (removed the duplicated `Page<T>` block).
- **`EvaluationsPage`** (replaces Phase 2 placeholder): run history with status badges, progress (`completed/total`), metric list, trigger/duration; link to run detail; "New evaluation" CTA.
- **`NewEvaluationPage`**: application/dataset selects, metric checkboxes (scope + provenance + required fields shown), "Check applicability" preview (applicable list, per-metric inapplicable reasons, estimated cases), "Start evaluation" → navigates to run detail (202 + polling).
- **`RunDetailPage`**: 2 s polling while queued/running; progress/config/cost cards; aggregate metrics with **provenance badges and explicit unavailable reasons**; per-case results (outcome, output, latency, errors, per-metric scores); role-gated Cancel (admin/editor).
- Routes `/evaluations`, `/evaluations/new`, `/evaluations/:runId` wired in `App.tsx`; placeholder `EvaluationsPage` removed (SecurityPage remains for Phase 5).
- Vitest suite `Phase3Pages.test.tsx` (3 tests, mocked services).

### Infra/config
- `.env.example`: `RUN_WORKER_ENABLED`, `RUN_POLL_INTERVAL_S` documented.
- Docker Compose `api` rebuilt; live smoke passed (below). One deployment bug found & fixed during smoke: `start_worker()` had been inserted **after** the lifespan `yield` (only ran at shutdown); also the engine now self-registers evaluators (`registry.ensure_loaded()` at `_execute` start) so it cannot fail with `UnknownEvaluatorError` in a fresh process.

## Commands run (verification)
| Command | Result |
| --- | --- |
| `pytest -q` (backend) | **102 passed** (Phase 2's 44 + 58 new: registry 14, evaluators 26, engine 7, runs API 11) |
| `ruff check .` (backend) | All checks passed |
| `npx vitest run` (frontend) | 9/9 passed (AppShell 3 + Phase2 3 + Phase3 3) |
| `npx tsc --noEmit` | clean |
| `npm run build` | built (~1.3 s) |
| Docker live smoke | login ok → mock app created → 3-case JSONL dataset (3 valid) → `validate-config` all 5 metrics applicable → `POST /evaluations` **202 queued** → worker claimed & executed → **completed**, progress 3/3, `reliability.success_rate=1.0`, `performance.latency` mean 38 ms (p50 41/p95 52), `performance.token_usage` mean 6.333 tokens, `cost.estimated_total` **unavailable** ("no model metadata reported by application" — honest, not fabricated) → results: 3 rows, `q1` success, `exact_match=0.0` (mock echo ≠ expected, correctly measured) |

## Acceptance Phase 3 status
- ✅ Registry + `register(spec, fn)` extension point (T3.1); core evaluators per `metrics.md` with exact id naming (T3.2).
- ✅ Engine: plan/execute/evaluate/persist with failure isolation, repeats, retries, timeouts, rate limiting, concurrency, cancellation, progress persistence (T3.3).
- ✅ Background run execution via worker claiming queued runs; runs persist status/progress (T3.4).
- ✅ Runs/results API per `interface-contract.md` incl. 422 inapplicable-config rejection and 202 async start.
- ✅ Evaluations UI: list/create/results with polling, provenance and unavailable reasons surfaced.

## Known limitations / decisions
- `answer.correctness` ships as an **estimated** heuristic (token F1) — true model-judged correctness requires an LLM judge (flagged unavailable when `judge_model` configured); provenance makes this explicit everywhere.
- Case-scope metric values are attached to `repeat_index=0` results only (they are computed over all repeats of a case); duplicates avoided by design.
- Worker executes runs one at a time in-process (matches MVP scale); multiple uvicorn workers are safe (conditional-claim guard) but throughput scales per-process.
- `GET /metrics` returns raw spec dicts (response typed loosely) — full schema typing can be tightened later.
- Cost estimates come from the code-defined pricing table `2026-10`; unknown models are honestly unavailable, never guessed.
- Run result detail currently returns `retrieved_document_ids: null` (mock adapter supplies doc ids; surfacing them end-to-end via `retrieved_documents` JSON is Phase 4 polish).
- Compare (FR-F3) / export (FR-F4) endpoints and Phase 4+ features remain per `tasks.md`.

## Remaining tasks (next phase)
- Phase 4 — Reporting & comparison: run compare endpoint (FR-F3), CSV/JSON export (FR-F4), aggregated dashboards.