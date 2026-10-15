# K-AERS Constitution — Project Principles & Standards

**Version:** 1.0.0 · **Status:** Draft for review · **Date:** 2026-10-15

K-AERS (Ksquare AI Evaluation, Reliability & Security Platform) is a modular platform for evaluating AI applications (RAG apps such as KODI, general LLM apps, and AI agents) on answer quality, retrieval quality, reliability, latency, cost, and security.

This constitution is binding for all implementation phases. Conflicts are resolved in this order: constitution → decisions.md → specs → code review judgment.

---

## 1. Development Process

1. **Spec-driven development (SDD).** No feature is implemented before a specification exists in `specs/`. Specs are versioned documents; changes require updating the spec first.
2. **Phase discipline.** Work proceeds in the phases defined in `specs/implementation/tasks.md`. Each phase ends with passing tests, a working application, and a written report (files changed, commands run, tests passed, known limitations, remaining tasks).
3. **No unreviewed mega-changes.** Never implement the whole application in a single unreviewed change.
4. **Inspect before modifying.** Read the code, conventions, and specs before editing anything.

## 2. Evidence & Honesty Rules (non-negotiable)

1. **No fabricated data.** The dashboard shows only computed results from real evaluation runs. Development fixtures, if any, must live behind an explicitly labeled demo/seed mechanism.
2. **No invented capabilities.** Never assume an application exposes retrieved documents, traces, token counts, or citations. Metrics that lack required inputs are reported as `unavailable`, never as `0` and never estimated silently.
3. **Labeled provenance.** Every displayed number is visibly classified as `measured`, `estimated` (e.g., costs from configurable pricing), or `model_judged` (LLM-as-a-judge).
4. **No fabricated traces.** Agent traces, tool calls, and citations are only what the target application actually reports.
5. **Judge humility.** LLM-as-a-judge scores are estimates, not ground truth. Judge model, prompt version, score, and explanation must be persisted and displayed.

## 3. Architecture Principles

1. **Modular evaluation engine.** The engine is independent of HTTP routes and the database layer. Metrics/evaluators are plugins registered in a registry; adding a metric must not require modifying the engine core.
2. **Adapter pattern for targets.** All target applications implement one common integration contract (`TargetAdapter`) with declared capabilities. Adapters never assume capabilities that are not declared.
3. **Business logic lives in services/evaluation modules**, not in API routes or UI components. Routes validate and delegate; UI renders.
4. **Simplest maintainable design.** No message broker, cache, vector DB, or extra service unless a concrete requirement justifies it (per the K-ARES blueprint).
5. **Explicit failure taxonomy.** The platform distinguishes: application failure, metric-calculation failure, invalid test case, and infrastructure failure — in storage, results, and UI. One failed test case must never crash a run.
6. **Reproducibility.** Every run records application config version, dataset version, evaluator versions, and a configuration snapshot, so runs can be reproduced and compared.

## 4. Security Principles

1. **Secrets hygiene.** No hardcoded keys, passwords, or tokens. Secrets come from environment variables or a secrets manager. Secrets are never returned by the API, never logged, and never shown in the UI (write-only fields; masked display only).
2. **Sensitive configuration persisted by K-AERS is encrypted at rest** (see specs/security/security-requirements.md).
3. **SSRF protection.** User-supplied URLs are validated (scheme, host policy, private-address blocking) before any server-side request. All outbound calls have timeouts, size limits, and concurrency limits.
4. **Controlled security tests only.** Security payloads are harmless, non-destructive, and fixed in the codebase. No destructive actions, no uncontrolled attacks on external systems.
5. **Validate all inputs.** Uploaded files: format, size limits, row-level validation with explicit error reporting. Invalid test cases are reported, never silently dropped.
6. **Honest security claims.** Passing the controlled security suite does not prove an application is secure; the UI and reports must state this.

## 5. Coding Standards

**Backend (Python 3.11+)**
- Formatting/linting: `ruff` (format + lint). Type hints required on public functions.
- Pydantic v2 for all API schemas; SQLAlchemy 2.0 style models; Alembic migrations.
- Async-first for I/O; CPU-bound metric work in executors.
- Docstrings on every public module/class/function.

**Frontend (React 18 + TypeScript)**
- Strict TypeScript. No `any` in new code.
- Functional components + hooks; feature-folder structure (`src/features/*`).
- Data fetching via typed API service layer; loading/empty/error states are mandatory per page.
- Shared design tokens; responsive layout; accessible components.

**General**
- Keep dependencies minimal; justify every new dependency in the phase report.
- Configuration via environment variables with a single settings module.
- Structured (JSON) logging with secret redaction; request IDs on all log lines.
- Health checks for API and worker processes.

## 6. Testing Standards

- Every metric has unit tests with known inputs/expected outputs, including unavailable-input cases.
- Automated tests never call paid APIs; LLM-judge evaluators are mockable and mocked in tests.
- Integration tests use deterministic mock adapters and fixtures.
- Every phase ships tests; a phase is not done while any test fails.

## 7. Out of Scope (this version)

- Activation-space anomaly detection or any research-specific analysis. Do not add it.
- Multi-tenant enterprise RBAC (design hooks only; simple auth for MVP).
- Scheduled evaluations, CI/CD release gates, experiment tracking (future extensions; interfaces must not preclude them).

## 8. Definition of Done (project level)

See specs/validation/test-plan.md. Highlights: full local workflow works with a mock application and no paid services; results persisted and reproducible; run comparison and export work; dashboard shows only real computed data; Docker-based setup documented; security limitations documented.
