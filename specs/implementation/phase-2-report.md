# K-AERS — Phase 2 Report (Applications & Datasets)

**Date:** 2026-10-17 · **Status:** Complete · **Scope:** T2.1–T2.6 per `specs/implementation/tasks.md`

## Delivered

### Backend
- **Credential crypto** (`app/core/crypto.py`): Fernet `encrypt_json`/`decrypt_json` with `EncryptionError`; key from `SECRET_ENCRYPTION_KEY` (new Settings field, falls back to `SECRET_KEY`).
- **Integration contract** (`app/integrations/`): `TargetAdapter` ABC + `AdapterCapabilities`/`AdapterResponse`/`ConnectionTestResult`; deterministic `MockAdapter` (echo output, `trigger_error`/`trigger_timeout` input markers, no fabricated fields — absent data stays `None` per constitution §2.2/D4); SSRF-guarded `RestAdapter` (URL validation incl. DNS resolution + private-range blocklist, manual redirects ≤2 with re-validation, timeout/size caps, errors carry exception *type names* only). Registry factory map with `register_adapter` extension point.
- **Application service + API** (`app/services/application_service.py`, `app/api/routes/applications.py`): register/list/get/patch/delete/enable-disable with role gates (Editor+ for mutations); Fernet-encrypted credential storage; responses expose `has_credentials` only (write-only schemas); sanitized config snapshots + SHA-256 `config_hash` recorded in `ApplicationConfig` per change; `POST /{id}/connection-test` persists a sanitized result to `last_connection_test`.
- **Dataset service + API** (`app/services/dataset_service.py`, `routes/datasets.py`): JSONL/CSV upload with row-level validation; **invalid rows are retained** with `status=invalid` + `validation_errors` (never dropped); `relevant_doc_ids` preserves absent-vs-empty semantics (`None` = unlabeled, `[]` = labeled, no relevant docs); immutable versioning with SHA-256 content-hash dedupe (identical re-upload reuses the version, changed content bumps `max+1`); `POST /datasets/validate` dry-run; paginated `cases` with `case_status`/`category` filters via `dataset_status`/`category` query params.
- **Storage layer** (`app/storage/local_store.py`): content-addressed sha256 keys under `DATA_DIR`, path-traversal guard, 10 MB size cap (`max_dataset_rows` row cap enforced in upload).
- **Sample datasets** (`app/services/sample_datasets.py`): 4 bundled, idempotently installable samples — `sample-rag-qa` (10), `sample-llm-basic` (8), `sample-agent-tools` (6), `sample-security-core` (8).
- **Model/migration**: `applications.invoke_path` + `applications.last_connection_test` added; Alembic migration `51e03153ff3e` generated and applied.

### Frontend
- Typed services `src/services/{applications,datasets}.ts` + extended `src/types/api.ts`.
- `ApplicationsPage`: register form (type/integration/capabilities/optional secret), list with badges, enable/disable, delete, connection test with persisted result display.
- `DatasetsPage`: upload form with validate-only + validation report panel (issues/warnings), bundled-samples panel with idempotent install, dataset list with version counts.
- Placeholder pages reduced to Phase 3+ entries; routes wired in `App.tsx`.

### Infra/config
- `backend/pyproject.toml`: added runtime dependency `httpx>=0.27` (was test-only; API image failed on import) and ruff per-file-ignores for sample data lines.
- `.env.example`: `SECRET_ENCRYPTION_KEY` documented.
- Docker Compose rebuilt + live smoke test passed (see below).

## Commands run (verification)
| Command | Result |
| --- | --- |
| `pytest tests/ -q` | **44 passed** (Phase 1's 20 + 24 new) |
| `ruff check .` | All checks passed |
| `npm run test -- --run` | 6/6 passed (AppShell 3 + Phase2 pages 3) |
| `npx tsc --noEmit` | clean |
| `npm run build` | built in ~2 s |
| `docker compose up -d --build` | api/db/web up |
| Live smoke (curl) | health ok; login ok; register mock app (`has_credentials=true`, secret never echoed); connection test `success=true`, sanitized message; 4 samples installed + idempotent re-install returned identical version IDs; JSONL upload with 1 invalid row → `cases=2 invalid=1` (row retained); delete → 204; web proxy `GET /api/v1/health` via :5173 → 200 |

## Acceptance P2 status
- ✅ Register mock app; test-connection succeeds; failure path returns sanitized failure (`example.com:9` → connection failed, no internals leaked).
- ✅ Secrets never visible in API responses or logs (`has_credentials` + write-only schema asserted by tests and live smoke).
- ✅ `sample-rag-qa` installs with a clean validation report.
- ✅ Invalid rows visible as `invalid` with row-level errors.
- ✅ Identical re-upload reuses the version (content-hash dedupe verified in tests + live smoke).

## Known limitations / decisions
- Rest adapter ships without retries by design for MVP (single attempt, timeouts + size caps enforced); retry policy is Phase 3 engine territory.
- `POST /{id}/connection-test` endpoint currently performs the request test only via registered adapters (`mock`/`rest_api`); KODI-specific adapter deferred per open decision question.
- Spec decision questions 1–4 from `specs/decisions.md` remain open with the agreed conservative defaults.
- Live smoke reset the seeded admin's password to the current `.env` value (the 46h-old dev DB had an older seed).

## Remaining tasks (next phase)
- Phase 3 — Evaluation engine core (T3.1–T3.4): evaluator registry, core evaluators, orchestration, background runner.