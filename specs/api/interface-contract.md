# K-AERS — API Interface Contract

**Version:** 1.0.0 · **Status:** Draft for review

Base URL: `/api/v1`. JSON only. All timestamps ISO-8601 UTC. IDs are UUID strings unless noted.

## Conventions

- **Pagination:** `?page=1&page_size=25` (max 100). Responses: `{"items": [...], "page": 1, "page_size": 25, "total": 42}`.
- **Error format (all non-2xx):**
```json
{
  "error": {
    "code": "validation_error | not_found | conflict | invalid_state | unauthorized | forbidden | unprocessable | internal_error",
    "message": "Human-readable summary",
    "details": [ {"field": "name", "message": "required"} ]
  },
  "request_id": "uuid"
}
```
- **Status codes:** 200 read/update; 201 create; 202 accepted (async start); 400 validation; 401/403 auth; 404 missing; 409 conflict; 422 unprocessable (semantic validation, e.g., incompatible metrics); 500 internal.
- **Secrets:** never present in any response. Credential fields are write-only; read responses contain `has_credentials: bool` and `credentials_updated_at` only.
- **Provenance:** every metric value carries `provenance: measured | estimated | model_judged` and `status: computed | unavailable`.

## Endpoints

### Health
- `GET /health` → 200 `{"status":"ok","database":"ok","version":"x.y.z"}`

### Applications (Module A)
- `POST /applications` — body: `{name, description?, application_type, integration_type, connection: {base_url?, auth: {type: none|api_key|bearer|basic, secret_ref_payload?}}, capabilities?: {...}, version_label?}` → 201 Application
- `GET /applications?application_type=&enabled=&search=` → Page[ApplicationSummary]
- `GET /applications/{id}` → Application (includes capabilities, integration info; never secrets)
- `PATCH /applications/{id}` — update metadata/capabilities/enabled → 200 Application
- `DELETE /applications/{id}` → 409 if runs exist (history preservation); otherwise 204. Prefer disable.
- `POST /applications/{id}/test-connection` → 200 `{"success": bool, "latency_ms": int|null, "message": "sanitized reason", "checked_at": ts}`

### Datasets (Module B)
- `POST /datasets` (multipart: `file` .jsonl/.csv, fields: `name`, `description?`, `application_type`) → 201 DatasetWithVersion (server parses + validates; returns per-row errors)
- `POST /datasets/validate` — validate a file without persisting → `{valid: bool, errors: [{row, field, message}], stats: {...}}`
- `GET /datasets?application_type=&search=` → Page[DatasetSummary]
- `GET /datasets/{id}` → Dataset + versions list
- `GET /datasets/{id}/versions/{version_id}` → version detail
- `GET /datasets/{id}/versions/{version_id}/cases?page=&status=&category=&search=` → Page[TestCase]
- `GET /datasets/{id}/versions/{version_id}/sample-download` → original file
- `GET /datasets/sample-datasets` → list of built-in sample dataset descriptors
- `GET /datasets/sample-datasets/{key}/download` → sample file

### Evaluations (Modules C/E/F)
- `GET /metrics` → list of registered evaluators: `[{id, name, description, application_types, required_fields, capabilities_required, config_schema, version, provenance}]`
- `POST /evaluations/validate-config` — body: `{application_id, dataset_id, dataset_version_id?, metric_ids, run_config?}` → `{applicable: [...], inapplicable: [{id, reason}], estimated_cases, estimated_cost?}` (applicability preview; dry-run)
- `POST /evaluations` → 202 `{run}` — body: `{application_id, dataset_id, dataset_version_id?, metric_ids, include_security_suite?: bool, run_config?: {concurrency?, timeout_ms?, max_retries?, repeats?, rate_limit_rps?}}`
- `GET /evaluations?application_id=&status=&from=&to=` → Page[RunSummary]
- `GET /evaluations/{id}` → RunDetail (status, progress, aggregate metrics with provenance, cost summary, error summary)
- `GET /evaluations/{id}/results?page=&status=&category=&evaluator_id=&search=` → Page[CaseResult] (inputs, outputs, references, per-metric scores, errors)
- `GET /evaluations/{id}/results/{case_result_id}` → CaseResultDetail (full trace, judge explanations)
- `POST /evaluations/{id}/cancel` → 202 `{run}` (cooperative cancel)
- `POST /evaluations/compare` — body: `{baseline_run_id, candidate_run_id}` → comparison report (below)
- `GET /evaluations/{id}/export?format=json|csv` → file download

### Comparison report shape
```json
{
  "baseline_run_id": "...", "candidate_run_id": "...",
  "dataset_compatible": true,
  "metric_deltas": [ {"evaluator_id": "answer.correctness", "baseline": 0.82, "candidate": 0.74, "delta": -0.08, "regression": true, "provenance": "measured"} ],
  "newly_failing_case_ids": [...], "resolved_case_ids": [...],
  "latency_delta": {...}, "cost_delta": {...}
}
```

### Security (Module D-8)
- `GET /security/suites` → suite descriptors + categories + case counts (static, versioned)
- `GET /security/results?application_id=` → Page[SecurityRunSummary]
- Security case results are also visible via run results filtered by `category`.

### Auth (MVP)
- `POST /auth/login` `{email, password}` → sets session cookie / returns bearer token
- `POST /auth/logout` → 204 · `GET /auth/me` → current user

## Validation Rules (representative)
- application name: 1–120 chars, unique; application_type in enum; integration_type must have a registered adapter.
- rest_api connection: `base_url` must be http(s), pass SSRF checks (no private/loopback hosts unless explicitly allowed by env); auth payload shape per auth type.
- dataset file: ≤10 MB, ≤20,000 rows; JSONL: one JSON object per line; CSV: header row required; unknown columns are reported but kept in `metadata`.
- run_config: concurrency 1–16, timeout_ms 1,000–300,000, max_retries 0–3, repeats 1–5, rate_limit_rps 0.1–100.

## Endpoint ↔ Requirement Traceability
FR-A1–A6 → /applications*; FR-B1–B6 → /datasets*; FR-C1–C6, FR-E, FR-F → /evaluations*, /metrics; FR-G consumes all read endpoints; FR-H → /evaluations/{id}/export.
