# K-AERS — Dataset Format Specification

**Version:** 1.0.0 · **Status:** Draft for review

## File Formats

- **JSONL** (preferred): one JSON object per line, UTF-8.
- **CSV**: UTF-8 (BOM tolerated), header row required, comma-delimited, RFC 4180 quoting.
- Limits: ≤ 10 MB, ≤ 20,000 rows (configurable via env).

## Test Case Schema (v1)

| Field | Type | Required | Notes |
|---|---|---|---|
| id | string | recommended | Unique within dataset; auto-generated `tc-{n}` if absent (reported in validation output) |
| input | string | **required** | Question/prompt sent to the application |
| expected_output | string | optional | Reference answer; absent ⇒ reference-based metrics unavailable for this case |
| reference_context | string | optional | Grounding text used by judge/faithfulness evaluators |
| relevant_doc_ids | array[string] | optional | Relevance labels for retrieval metrics. **Distinguish:** field absent = not labeled; `[]` = explicitly labeled as "no relevant docs" (enables abstention/no-answer evaluation) |
| application_type | enum(`rag`,`llm`,`agent`) | required | Must match a registered adapter type for evaluation |
| category | string | recommended | e.g., factual, reasoning, refusal, edge_case, security |
| expected_tool | string or object | optional | Agent: tool expected to be called |
| expected_action_sequence | array | optional | Agent: ordered expected actions |
| expected_structured_output | object | optional | JSON schema or exact structure expectation |
| tags | array[string] | optional | Free-form filtering |
| metadata | object | optional | passthrough, never used by metrics |

### Absent vs empty (normative)
- **Absent key** (JSONL) / empty cell (CSV) ⇒ NULL ⇒ *not provided* → dependent metrics `unavailable`.
- **Empty string ""** ⇒ *provided but empty* → usable by metrics (e.g., exact match vs empty output).
- CSV cannot represent the distinction for strings; documented: empty cell = absent. Use JSONL when the distinction matters.

### CSV column mapping
Column names = JSON keys (snake_case). `relevant_doc_ids`, `tags` serialized with `;` separator (e.g., `doc1;doc2`). Unknown columns → warning, stored in `metadata`.

## Validation Rules

Row-level errors reported as `{row, field, message, severity}`; invalid rows are **retained** with status `invalid` and never evaluated:
1. `input` present and non-empty after trim.
2. `application_type` in enum.
3. `expected_structured_output`, if present, must be valid JSON/object.
4. `relevant_doc_ids`, `tags` must be arrays of strings.
5. Duplicate `id`s → error.
6. JSONL parse failure of a line → row-level error with line number; other lines unaffected.
7. Encoding errors → file-level error.
8. Category/tag length caps (≤ 80 chars).

Validation output: `{valid_case_count, invalid_case_count, warnings: [...], errors: [{row, field, message}]}`.

## Versioning

- Every upload/create creates an immutable `dataset_version` (version_number increments per dataset; `content_hash` = sha256 of normalized file bytes).
- Re-uploading byte-identical content returns the existing version (idempotent).
- Runs always reference `dataset_version_id`; runs remain reproducible even after dataset edits.
- Editing a dataset = creating a new version from modified content; diff (added/removed/changed case ids) is returned by the API.

## Sample Datasets (bundled, downloadable)

| Key | App type | Cases | Purpose |
|---|---|---|---|
| `sample-rag-qa` | rag | 10 | QA with references + relevant doc ids; includes 2 no-answer cases |
| `sample-llm-basic` | llm | 10 | Short deterministic answers (exact match / token F1) |
| `sample-agent-tools` | agent | 8 | Tasks with expected_tool and action sequences |
| `sample-security-core` | any | 12 | Core security suite cases (see metrics.md §8) |

All sample content is synthetic and self-contained (no external calls, no real PII).

## Example (JSONL)

```json
{"id":"qa-001","input":"What is the refund window for premium plans?","expected_output":"Premium plans have a 30-day refund window.","reference_context":"Policy v3: Premium refunds are available within 30 days of purchase.","relevant_doc_ids":["policy-v3#refunds"],"application_type":"rag","category":"factual","tags":["refunds"],"metadata":{"source":"handbook"}}
{"id":"qa-002","input":"What is the company's employee count?","expected_output":"I don't have that information.","relevant_doc_ids":[],"application_type":"rag","category":"no_answer"}
{"id":"ag-001","input":"Create a Jira ticket for the login bug.","application_type":"agent","category":"workflow","expected_tool":"jira_create_issue","expected_action_sequence":["search_issue","jira_create_issue"]}
```
