# Phase 4 Report — Dashboard Completion (T4.1–T4.5)

Date: 2026-10-17 · Verification: backend `pytest -q` **108 passed**, `ruff check .` clean; frontend `vitest run` **9/9 passed**, `npm run build` (tsc + vite) clean.

## Backend (reports & dashboard endpoints)

### Services
- **`app/services/report_service.py`**
  - `compare_runs(session, baseline_run_id, candidate_run_id)` (FR-F3): validates both runs exist and are `completed` (≠ same id); computes `dataset_compatible` from configuration snapshots; matches cases by case id across repeats; derives **newly failing** and **resolved** case id lists; metric deltas from run-scope `summary_metrics` **plus** case-scope metrics aggregated over matched cases (registry `value_kind` is the single source of truth); regression polarity follows lower-is-better ids (`performance.latency`, `cost.estimated_total`); latency delta (mean + p95) and cost delta with explicit `unavailable_reason` when cost is not measured in both runs. Raises `ApplicabilityError` when the runs share no comparable cases.
  - `overview(session)` (FR-G1): real aggregates only — totals (applications/enabled/datasets/runs/cases executed), status breakdown (grouped query), 5 most recent runs (`run_service.to_summary`), key metric summaries for the 5 latest completed runs (success rate, latency mean, total cost with per-value `status`), 5 most recent failures (application_error/timeout joins with test case + run).
  - `export_run(session, run_id, fmt)`: FR-F4/H — JSON report per FR-H3 (app/dataset info, run config + snapshot, metric definitions w/ evaluator versions, per-case rows, failed cases, error summary, duration, cost, versions) and CSV with one row per case + aggregate section; unknown format/run rejected.

### Endpoints (`app/api/routes/`)
- `POST /evaluations/compare` → `CompareOut` (`evaluations.py`).
- `GET /evaluations/{id}/export?format=json|csv` → file download with `content-disposition` filename; export journal note: no credentials or secrets included (SR-11).
- `GET /dashboard/overview` → `OverviewOut` (`dashboard.py`, registered in `main.py`).

### Schemas (`app/schemas/report.py`)
`CompareRequest`, `MetricDelta`, `LatencyDelta`, `CostDelta`, `CompareOut`, `RunStatusCount`, `RecentFailure`, `KeyMetricSummary`, `OverviewOut`.

### Tests (`backend/tests/test_reports_api.py`, 6 tests)
Injected-regression flagging (success→error case between runs), invalid-run validation, overview from real data, CSV rows + aggregates, JSON round-trip vs stored run, format/run rejection. All against the mocked-adapter fixture flow (run worker disabled in conftest; runs driven to completion directly).

## Frontend (Phase 4 UI)

| File | What changed |
|---|---|
| `src/types/api.ts` | Phase 4 types: `RunStatusCount`, `RecentFailure`, `KeyMetricSummary`, `OverviewOut`, `MetricDelta`, `LatencyDelta`, `CostDelta`, `CompareOut`, `CaseResultDetail` |
| `src/services/reports.ts` (new) | `getOverview`, `compareRuns`, `exportRun` (blob download with content-disposition filename) |
| `src/services/evaluations.ts` | `getRunResult` (per-case detail endpoint) |
| `src/pages/OverviewPage.tsx` (T4.1) | Totals cards, status-breakdown bars, recent runs (linked), key-metric table (latest completed runs, *unavailable* shown as badges, never zero), recent failures list; health strip kept; `EmptyState`/`StatusCard` still exported for reuse |
| `src/pages/RunDetailPage.tsx` (T4.2/T4.4/T4.5) | Recharts **aggregate-scores bar chart**; case-results table with outcome filter + Prev/Next pagination; rows expand to `ResultDetail`: expected vs actual side-by-side, case input JSON, retrieved-document (reference) id chips, agent-trace JSON, per-case metrics with explanations + provenance tags; **Export JSON / Export CSV** buttons (completed runs) with blob download |
| `src/pages/ComparePage.tsx` (new, T4.3/T4.4) | Baseline/candidate selectors (completed runs, cross-exclusion), dataset-incompatibility warning, Recharts grouped **Baseline vs Candidate** bar chart, latency delta card (mean + p95), cost delta card, metric-delta table (rows highlighted rose on regression, improvement emerald, unavailable reasons shown), newly-failing / resolved case chips |
| `src/pages/EvaluationsPage.tsx` (T4.4) | Search (run id / user), status filter, server-driven pagination |
| `src/App.tsx`, `AppLayout.tsx` | `/compare` route + "Compare" nav entry |
| `src/test/setup.ts` | ResizeObserver polyfill (Recharts requires it in jsdom) |
| `src/pages/Phase3Pages.test.tsx` | `getRunResult` added to the service mock; awaited on data-flagged content (status filter select legitimately contains the word "completed"); aggregate assertion updated to `getAllByText` since the chart axis also renders metric ids |

## Acceptance P4 mapping
- **E2E §8 steps 1–10 passable in UI** — register→upload→configure→run→aggregate+per-case→failure detail all viewable; overview dashboard aggregates real data.
- **Comparison flags an injected regression** — covered by `test_compare_flags_injected_regression` and surfaced in the UI via rose-highlighted rows + delta badges.
- **Exports download and match stored data** — `test_export_json_matches_stored_run`, `test_export_csv_rows_and_aggregates`; UI triggers the same endpoints via blob download.

## Notes / limitations
- Result detail surfaces `retrieved_document_ids` (ids as chips); full retrieved passage text remains Phase 4+ polish per phase-3 report.
- The aggregate-scores bar chart mixes value kinds (rate/ms/currency) on one axis; acceptable MVP scope since charts are only used where they aid comparison — values are also in the table right next to it.
- Bundle grows past 500 kB minified due to Recharts (informational Vite warning; code-splitting left to later hardening).
- Merged-run case matching keys on case ids; runs without overlapping case ids are rejected with an explicit applicability error rather than an empty comparison.