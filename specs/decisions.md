# K-AERS — Architecture Decision Records

**Version:** 1.0.0 · **Status:** Draft for review

Format: decision / context / decision / rationale / consequences.

---

## D1 — Backend: FastAPI + Python 3.11+
**Context:** Evaluation logic benefits from the Python AI ecosystem; blueprint proposes FastAPI.
**Decision:** FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic; PostgreSQL 16 (SQLite profile for unit tests/dev).
**Rationale:** Matches blueprint; typed schemas double as API contract; relational integrity is required for the run/dataset/application version graph.
**Consequences:** Async I/O for adapters; JSONB for flexible payloads; Alembic discipline required.

## D2 — Background execution: in-process thread runner now, Celery later
**Context:** Evaluations can be long-running; blueprint advises against adding a broker without justification.
**Decision:** Run state lives in PostgreSQL (`queued → running → …`); a worker claims queued runs via row lock. MVP worker runs as a thread pool inside the api container (separate worker container optional in compose). Celery+Redis is a future swap.
**Rationale:** Simplest design meeting MVP workload; DB-claim pattern makes worker process isolation a config change, not a rewrite.
**Consequences:** Scale ceiling bounded by one process; acceptable for MVP; documented upgrade path.

## D3 — Frontend: React 18 + TypeScript + Vite + TanStack Query + Tailwind + Recharts
**Context:** Modern responsive dashboard with tables, forms, limited charts.
**Decision:** As stated; shadcn/ui-style components over a heavy UI kit.
**Rationale:** Fast DX, full styling control, chart library only where comparisons benefit; TanStack Query handles polling for live run progress.
**Consequences:** Component discipline needed to keep UI consistent.

## D4 — Metrics as registered evaluators; engine never hardcodes metrics
**Decision:** `EvaluatorSpec` + registry; applicability resolved from declared adapter capabilities + dataset field availability.
**Rationale:** FR-E; future metrics register without engine changes (constitution §3.1).
**Consequences:** Every metric needs a spec (id, inputs, config, version); UI metric list is registry-driven.

## D5 — "Unavailable" is a first-class result state
**Decision:** Metric results have `status: computed | unavailable` + reason; aggregates exclude unavailable and record coverage.
**Rationale:** Honesty requirements (constitution §2); prevents zero-baseline distortions.
**Consequences:** All aggregations and UI must handle two-state results.

## D6 — Cost is always estimated; pricing is versioned configuration
**Decision:** `pricing.json` (per provider/model, per 1K tokens) in repo, overridable via env/DB config; costs labeled `estimated` with coverage ratio.
**Rationale:** Token counts may be absent; pricing drifts; estimates must never be presented as exact.
**Consequences:** Cost UI/report must show currency + coverage; unknown model ⇒ unavailable.

## D7 — LLM-as-a-judge is optional and pluggable
**Decision:** Judge provider (OpenAI-compatible endpoint) configured via env; judge evaluators disabled unless configured; all judge metadata (model, prompt version, scores, explanation) persisted; judge failure ⇒ metric unavailable, run unaffected.
**Rationale:** No paid-API dependency for core workflows (NFR-1); testability via mock judge.
**Consequences:** Some quality metrics exist only when configured; UI must explain this.

## D8 — Auth MVP: local users + session/bearer, roles admin/editor/viewer
**Context:** No Ksquare IdP integration confirmed.
**Decision:** Local auth with bcrypt; 3 roles; service-layer enforcement; SSO hooks left open.
**Rationale:** Minimal viable access control without blocking future IdP (Blueprint §16.1).
**Consequences:** Multi-team isolation is out of scope for MVP.

## D9 — Security suites are static, code-versioned, and verdict-based
**Decision:** Payload sets live in code (`evaluation/security/suites/v1/`); verdicts `pass | fail | inconclusive`; disclaimers mandatory in UI/reports.
**Rationale:** Controlled, reviewable, non-destructive (SR-23–SR-25); deterministic tests.
**Consequences:** New scenarios require a suite version bump + review.

## D10 — Datasets immutable per version; runs pin versions
**Decision:** Edits create new versions; runs store `dataset_version_id` + application config snapshot + evaluator versions.
**Rationale:** Reproducibility and fair comparison (FR-F3).
**Consequences:** Storage grows with versions; retention policy (NFR-8) handles cleanup of artifacts.

## D11 — Failure taxonomy stored per case
**Decision:** Four classes: application failure, metric-calculation failure, invalid test case, infrastructure failure; stored on results; run fails only on infrastructure errors or explicit cancellation.
**Rationale:** Master brief Module C; failure isolation is a hard requirement.
**Consequences:** Engine wraps every case and evaluator in classified error handling.

## D12 — Explicitly out of scope
Activation-space anomaly detection and any research-specific modules; scheduled evaluations; release gates; multi-tenancy; SSO; PDF/HTML reports. Interfaces must not preclude these, but nothing speculative is built now.

## Open Questions (require stakeholder input before Phase 2)

1. **KODI integration target:** is KODI reachable via a documented REST API at MVP, or should Phase 2 ship only mock + generic REST adapters and defer a KODI-specific adapter?
answer -  KODI is reachable via a documented REST API at mvp
2. **Judge provider:** which LLM provider/endpoint is approved for LLM-as-a-judge (affects defaults in pricing and judge config)?
answer - GLM 5.4 flash
3. **Deployment target:** single Docker host for MVP, or is a Ksquare-managed environment (with an existing identity provider) available for Phase 6?
answer single 
4. **Retention defaults:** acceptable defaults for run/artifact retention (proposal: artifacts 90 days, exports 7 days, runs indefinite)?
5. **Auth seeding:** preferred initial-admin bootstrap (env-seeded admin vs first-user-becomes-admin)?

## Open Questions — Decisions

1. **KODI integration target**
   - **Decision:** KODI is reachable through a documented REST API at MVP.
   - **Implementation:** Build a dedicated KODI adapter using the documented API contracts. Retain the generic REST adapter for other AI applications and a mock adapter for deterministic testing.
   - **Validation:** Test connection handling, authentication, request/response mapping, timeouts, errors, and evaluation result capture against KODI.

2. **Judge provider**
   - **Decision:** Use GLM-5.4-Flash as the default LLM-as-a-judge provider, subject to verification of the exact model identifier and supported API endpoint.
   - **Implementation:** Keep the provider, endpoint, model identifier, API key, timeout, and judge configuration externalized. Do not hardcode credentials or assume pricing.
   - **Validation:** Verify API compatibility, structured scoring, error handling, and cost calculation using the provider's current pricing. Keep the judge provider replaceable.

3. **Deployment target**
   - **Decision:** Single Docker host for MVP.
   - **Implementation:** Use Docker Compose for the frontend, backend, database, and any required background worker. Persist database data and required artifacts in appropriately managed volumes. Keep configuration environment-based.
   - **Validation:** Document installation, startup, upgrades, backup, restore, health checks, and recovery. Do not introduce Kubernetes or external identity-provider dependencies for MVP.

4. **Retention defaults**
   - **Decision:** Retain evaluation runs and aggregate metrics indefinitely by default; retain large artifacts and debug payloads for 90 days; retain generated exports for 7 days.
   - **Implementation:** Make retention configurable. Implement scheduled cleanup, document deletion behavior, and apply appropriate privacy and access controls. Preserve historical aggregate results when associated artifacts expire.
   - **Validation:** Test expiration, cleanup failures, retention configuration, and preservation of historical metrics.

5. **Auth seeding**
   - **Decision:** Use environment-seeded initial administrator bootstrap.
   - **Implementation:** Create the initial admin only when no administrator exists and valid bootstrap configuration is supplied. Hash passwords securely, never use default credentials, and never reset existing credentials on restart. Document secure password recovery and bootstrap disabling.
   - **Validation:** Test first startup, repeated startup, missing configuration, invalid configuration, existing-admin behavior, and unauthorized access.