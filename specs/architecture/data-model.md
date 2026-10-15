# K-AERS — Data Model

**Version:** 1.0.0 · **Status:** Draft for review

PostgreSQL schema (Alembic-managed). All timestamps `timestamptz` (UTC). UUID primary keys. JSONB for flexible payloads. Aligned with `Blueprint.txt` §10.

## Entity-Relationship Summary

```text
applications 1--* application_configs (versioned, sanitized)
applications 1--* evaluation_runs *--1 dataset_versions *--1 datasets
dataset_versions 1--* test_cases
evaluation_runs 1--* test_results 1--* metric_results
evaluation_runs 1--* run_events (progress/audit log)
security_suites 1--* security_test_cases (static, code-versioned)
```

## Tables

### applications
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | varchar(120) UNIQUE | |
| description | text | |
| application_type | enum(`rag`,`llm`,`agent`) | |
| integration_type | enum(`mock`,`rest_api`) | extensible |
| connection_config_encrypted | bytea | Fernet-encrypted JSON (auth fields only) |
| capabilities | jsonb | declared capability flags |
| current_version_label | varchar(120) NULL | |
| is_enabled | bool default true | disable preserves history |
| owner | varchar(120) | |
| created_at / updated_at | timestamptz | |

### application_configs (version snapshots)
id PK; application_id FK; version_label; model_name; prompt_version; code_revision; config_hash (sha256 of sanitized config); created_at. **Never contains credentials.**

### datasets
id PK; name UNIQUE; description; application_type; owner; created_at; updated_at.

### dataset_versions (immutable)
id PK; dataset_id FK; version_number int; content_hash; file_storage_key; case_count; valid_case_count; invalid_case_count; created_by; created_at. Rows are never mutated; edits create a new version.

### test_cases
id PK; dataset_version_id FK; position int (row order); external_id varchar(120) (unique per version); status enum(`valid`,`invalid`); validation_errors jsonb (array of {field, message, row}); input jsonb (question/prompt); expected_output text NULL; reference_context text NULL; relevant_doc_ids jsonb (list; NULL = not provided); expected_tool jsonb NULL; expected_action_sequence jsonb NULL; expected_structured_output jsonb NULL; application_type; category varchar(80); tags jsonb; metadata jsonb; is_security_case bool; created_at.

**Semantics:** a field absent from the source row = NULL ("unavailable"); an explicitly empty string = "" ("provided but empty"). Metrics must treat these differently where relevant.

### evaluation_runs
id PK; application_id FK; application_config_id FK; dataset_id FK; dataset_version_id FK; status enum(`queued`,`running`,`completed`,`failed`,`cancelled`); selected_metrics jsonb (list of {evaluator_id, version, config}); run_config jsonb (concurrency, timeout_ms, max_retries, repeats, rate_limit_rps); configuration_snapshot jsonb (sanitized); summary_metrics jsonb (aggregate scores + provenance labels); cost_summary jsonb; model_metadata jsonb (target model/provider info reported by adapter); triggered_by varchar(120); progress jsonb ({total, completed, failed}); error_summary jsonb; started_at; completed_at; duration_ms; created_at.

### test_results
id PK; evaluation_run_id FK; test_case_id FK; repeat_index int default 0; outcome enum(`success`,`application_error`,`timeout`,`invalid_case`,`skipped`); actual_output text NULL; retrieved_documents jsonb NULL; citations jsonb NULL; agent_trace jsonb NULL (tool_calls[] with name/args/success/duration); token_usage jsonb NULL ({input, output}); ttft_ms int NULL; latency_ms int; estimated_cost numeric(12,6) NULL; error_type varchar(40) NULL; error_message text NULL (sanitized); started_at; created_at.

UNIQUE (evaluation_run_id, test_case_id, repeat_index).

### metric_results
id PK; test_result_id FK (NULL for run-level aggregates, which live in summary_metrics); evaluator_id varchar(80); evaluator_version varchar(20); score numeric(12,6) NULL; value_kind enum(`score`,`rate`,`count`,`ms`,`tokens`,`currency`,`boolean`); status enum(`computed`,`unavailable`); unavailable_reason text NULL; provenance enum(`measured`,`estimated`,`model_judged`); explanation text; details jsonb (per-claim/per-doc breakdowns, judge prompt version, judge model); created_at.

### run_events
id PK; evaluation_run_id FK; event_type enum(`started`,`case_completed`,`progress`,`cancelled`,`failed`,`completed`,`warning`); payload jsonb; created_at. Powers progress UI and audit.

### users (MVP auth)
id PK; email UNIQUE; password_hash (bcrypt); role enum(`admin`,`editor`,`viewer`); is_active; created_at. Sessions via signed cookie or bearer token (see decisions.md).

### security_suites / security_test_cases
Suites are versioned static definitions in code (not user-editable at MVP): suite id (varchar), version; test cases: suite_id; case_key; category enum(`prompt_injection`,`instruction_override`,`sensitive_disclosure`,`unsafe_tool_use`,`untrusted_content`,`output_policy`,`robustness_input`,`robustness_output`); payload jsonb; expected_behavior text; evaluation_rule jsonb (how observed behavior is judged). Executed security cases are stored as test_cases (is_security_case=true) plus test_results/metric_results with provenance=`measured` and verdict fields in details.

### artifacts (storage index)
id PK; kind enum(`dataset_file`,`export`,`artifact`); storage_key; content_type; size_bytes; sha256; created_at. Local filesystem storage at MVP (`DATA_DIR`), S3-compatible later.

## Integrity Rules

1. FK constraints on all relations; `ON DELETE RESTRICT` for datasets/versions referenced by runs (history preservation); `ON DELETE CASCADE` from run → results.
2. dataset_versions immutable (no UPDATE path in the service layer).
3. Content hash on dataset files: identical hash on re-upload reuses the existing version.
4. Enum validation at both Pydantic and DB level.
5. Retention: `RETENTION_DAYS` for artifacts/exports; runs retained unless explicitly deleted (cascade documented).
