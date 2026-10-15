# K-AERS — Architecture & Design

**Version:** 1.0.0 · **Status:** Draft for review

## 1. System Overview

K-AERS is a single deployable platform: a FastAPI backend (API + evaluation engine + background worker), a React SPA frontend, and PostgreSQL. The first implementation runs as one backend process containing an in-process background runner (thread-based), per the blueprint's advice to avoid extra infrastructure until justified.

```text
+--------------------------------------------------------------+
|                        React SPA (Vite)                       |
|  Pages: Overview / Applications / Datasets / Configure /      |
|         Results / Compare / Security                          |
+------------------------------+-------------------------------+
                               | HTTPS (JSON, /api/v1)
+------------------------------v-------------------------------+
|                     FastAPI Backend (api/)                     |
|  Router layer: validation (Pydantic) -> Services              |
+-----------+-------------------------+------------------------+
           |                         |
+----------v----------+   +----------v---------------------------+
| Services layer      |   | Evaluation subsystem (framework-     |
| applications,       |   | agnostic; no HTTP/DB imports in core)|
| datasets, runs,     |   |  engine.py   - orchestration         |
| exports, security   |   |  registry.py - evaluator registry    |
+----------+----------+   |  metrics/    - metric implementations |
           |              |  security/   - controlled suites      |
+----------v----------+   +----------+---------------------------+
| Persistence (SQLA)  |              |
| + Artifact store    |   +----------v---------------------------+
+----------+----------+   | Background runner (thread pool,       |
           |              | DB-backed run state; Celery later)    |
+----------v----------+   +----------+---------------------------+
|      PostgreSQL     |              |
+---------------------+   +----------v---------------------------+
                          | Target adapters (integrations/)       |
                          |  mock | rest_api (+ KODI later)       |
                          +---------------------------------------+
```

## 2. Technology Choices (rationale in specs/decisions.md)

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2 | Blueprint recommendation; strong AI/eval ecosystem |
| ORM/DB | SQLAlchemy 2.0, Alembic, PostgreSQL 16 | Relational integrity between runs/datasets/apps; SQLite for unit/dev |
| Background | In-process ThreadPool runner with DB-backed state | Simplest design that meets MVP workload; Celery+Redis deferred |
| Frontend | React 18 + TypeScript + Vite | Fast DX, typed API layer |
| UI | Tailwind CSS + shadcn/ui-style components (Radix primitives) | Consistent, professional, low lock-in |
| Data/State | TanStack Query + Axios; Zustand only if needed | Server-state handling, caching, polling for run progress |
| Charts | Recharts | Simple bar/line charts for comparisons and trends |
| Auth (MVP) | Session cookie or bearer token with users table; bcrypt hashing | Minimal viable authn; RBAC hooks for later |
| Testing | pytest (+pytest-asyncio), Vitest + React Testing Library, Playwright (Phase 6) | Per blueprint |
| Packaging | Docker + Docker Compose (api, worker, db, web) | Reproducible local deployment |

## 3. Backend Structure

```
backend/
  app/
    api/            # routers: applications, datasets, evaluations, metrics, security, health
    core/           # settings (pydantic-settings), logging, security utils (crypto, redaction)
    models/         # SQLAlchemy models
    schemas/        # Pydantic request/response schemas
    services/       # business logic: application_service, dataset_service, run_service, export
    integrations/   # TargetAdapter protocol + mock_adapter, rest_adapter (+ kod_adapter later)
    evaluation/
      engine.py     # orchestration: plan -> execute -> evaluate -> persist (via ports)
      registry.py   # evaluator registry + applicability resolution
      metrics/      # answer/, rag/, reliability/, performance/, cost/, agent/
      security/     # controlled test suites (payloads are code/data, non-destructive)
      ports.py      # ResultSink / RunState protocols (DB adapter implements)
    storage/        # dataset file storage + artifact store abstraction
    db/             # session, base, migrations glue
  tests/            # unit, integration, e2e (httpx TestClient)
```

### 3.1 Key abstractions

- **TargetAdapter** (integrations/base.py): `async def invoke(case, timeout) -> AdapterResponse` and `capabilities: AdapterCapabilities`. `AdapterResponse` may include `output`, `retrieved_documents[]`, `citations[]`, `trace{tool_calls[]}`, `token_usage`, `ttft_ms`, `raw`. Adapters never fabricate fields; absent data is `None`.
- **Evaluator** (evaluation/base.py): `EvaluatorSpec` (id, name, description, app_types, required_fields, capabilities_required, config_schema, version) + `evaluate(case_result, config) -> MetricResult | MetricUnavailable(reason)`. Registered via `registry.register(spec)` at import time.
- **Engine ports**: the engine writes through `ResultSink` and `RunState` protocols so it stays testable without a database; the persistence layer implements them.
- **Error taxonomy** (evaluation/errors.py): `ApplicationError`, `MetricCalculationError`, `InvalidTestCaseError`, `InfrastructureError` — each per-case failure is classified and stored; the run continues.

### 3.2 Evaluation execution model

1. `POST /evaluations` validates config, resolves applicability (metrics vs capabilities + dataset fields), creates run row (`status=queued`), returns run id.
2. Background runner picks up queued runs (same process, thread pool; a DB poll makes a separate worker process possible later without code changes).
3. For each case: invoke adapter (timeout, retry w/ backoff, rate limit) → store raw result → run applicable evaluators → store metric results. Repeats (n>1) feed consistency metrics.
4. Aggregates computed at completion; run status: `queued → running → completed | failed | cancelled`. Cancellation is cooperative (checked between cases).
5. Security suite runs as an additional system-generated set of cases appended to the user's dataset selection.

## 4. Frontend Structure

```
frontend/src/
  pages/            # Overview, Applications, ApplicationDetail, Datasets, DatasetDetail,
                    # NewEvaluation, RunDetail, RunComparison, Security, Settings
  components/       # ui primitives, MetricCard, StatusBadge, ProvenanceTag, DataTable, EmptyState
  features/{applications,datasets,evaluations,security,reports}/
  services/         # typed API client (axios), query hooks
  types/            # API contract types mirrored from backend schemas
```

Routing: React Router. Run-progress pages poll run status via TanStack Query (2 s while running).

## 5. Data Flow (evaluation)

dataset_version rows → engine plan → adapter calls (HTTP to target app) → case results → evaluators (pure functions; LLM-judge calls external provider only when configured) → metric_results → aggregates → dashboard/export. Nothing enters the DB unversioned: each run pins `configuration_snapshot` (hash + sanitized config), `dataset_version_id`, and evaluator versions.

## 6. Cross-Cutting

- **Config:** pydantic-settings, `.env` + environment; documented in `.env.example`.
- **Logging:** structured JSON logs; redaction filter for `api_key`, `password`, `token`, `authorization`; request-id middleware.
- **Health:** `GET /api/v1/health` (DB check) and worker heartbeat.
- **Migrations:** Alembic; runs on api container start (idempotent).
- **Seed/demo data:** a clearly labeled `make seed-demo` script creating a mock app + sample dataset, flagged `is_demo` so the UI badges it; never auto-seeded in production mode.
