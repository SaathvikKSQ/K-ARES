/** API contract types mirrored from backend schemas (Phase 1 subset). */

export interface HealthResponse {
  status: string;
  database: string;
  version: string;
  environment: string;
}

export interface User {
  id: string;
  email: string;
  role: "admin" | "editor" | "viewer";
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: { field?: string | null; message: string }[];
  };
  request_id: string;
}

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

// ---- Phase 2: Applications & Datasets ----

export type ApplicationType = "rag" | "llm" | "agent";
export type IntegrationType = "mock" | "rest_api";

export interface CapabilityFlags {
  exposes_retrieved_docs: boolean;
  exposes_citations: boolean;
  exposes_traces: boolean;
  exposes_token_usage: boolean;
  streaming: boolean;
}

export interface Application {
  id: string;
  name: string;
  description: string;
  application_type: ApplicationType;
  integration_type: IntegrationType;
  base_url: string | null;
  invoke_path: string;
  has_credentials: boolean;
  capabilities: CapabilityFlags;
  current_version_label: string | null;
  is_enabled: boolean;
  owner: string | null;
  last_connection_test: {
    success: boolean;
    message: string;
    latency_ms: number | null;
    checked_at: string | null;
  } | null;
}

export interface ApplicationCreateInput {
  name: string;
  description?: string;
  application_type: ApplicationType;
  integration_type: IntegrationType;
  base_url?: string | null;
  invoke_path?: string;
  credentials?: Record<string, string> | null;
  capabilities?: CapabilityFlags;
  version_label?: string | null;
  model_name?: string | null;
  prompt_version?: string | null;
  code_revision?: string | null;
  owner?: string | null;
}

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  latency_ms: number | null;
}

export interface ValidationIssue {
  row: number;
  field: string;
  message: string;
}

export interface ValidationReport {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  issues: ValidationIssue[];
  warnings: ValidationIssue[];
}

export interface Dataset {
  id: string;
  name: string;
  description: string;
  application_type: ApplicationType;
  owner: string | null;
  version_count: number;
}

export interface DatasetVersion {
  id: string;
  version_number: number;
  content_hash: string;
  case_count: number;
  valid_case_count: number;
  invalid_case_count: number;
  created_by: string | null;
  created_at?: string | null;
}

export interface DatasetVersionDetail {
  dataset: Dataset;
  version: DatasetVersion;
  validation_report: ValidationReport | null;
}

export interface TestCase {
  id: string;
  position: number;
  external_id: string | null;
  status: "valid" | "invalid";
  validation_errors: ValidationIssue[];
  input: Record<string, unknown>;
  expected_output: string | null;
  reference_context: string | null;
  relevant_doc_ids: string[] | null;
  expected_tool: { name: string } | null;
  expected_action_sequence: string[] | null;
  expected_structured_output: Record<string, unknown> | null;
  application_type: ApplicationType;
  category: string | null;
  tags: string[];
  is_security_case: boolean;
}

export interface SampleDatasetInfo {
  key: string;
  name: string;
  description: string;
  application_type: ApplicationType;
  case_count: number;
}

// ---- Phase 3: Evaluations ----

export type MetricProvenance = "measured" | "estimated" | "model_judged";
export type MetricValueKind = "score" | "rate" | "ms" | "tokens" | "currency" | "count";
export type MetricStatus = "computed" | "unavailable";
export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface MetricSpec {
  id: string;
  name: string;
  description: string;
  version: string;
  provenance: MetricProvenance;
  value_kind: MetricValueKind;
  scope: "case" | "run";
  application_types: string[];
  required_fields: string[];
  capabilities_required: string[];
  config_schema: Record<string, unknown>;
}

export interface MetricValue {
  evaluator_id: string;
  evaluator_version: string;
  provenance: MetricProvenance;
  value_kind: MetricValueKind;
  status: MetricStatus;
  score: number | null;
  unavailable_reason: string | null;
  explanation: string | null;
  details: Record<string, unknown>;
}

export interface RunConfigInput {
  concurrency: number;
  timeout_ms: number;
  max_retries: number;
  repeats: number;
  rate_limit_rps: number;
}

export interface RunProgress {
  total?: number;
  completed?: number;
  failed?: number;
  skipped?: number;
}

export interface RunSummary {
  id: string;
  application_id: string;
  dataset_id: string;
  dataset_version_id: string;
  status: RunStatus;
  progress: RunProgress;
  metric_ids: string[];
  triggered_by: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
}

export interface CostSummary {
  currency: string;
  pricing_version?: string;
  total_usd?: number | null;
  per_case_usd?: number | null;
}

export interface RunDetail extends RunSummary {
  run_config: RunConfigInput;
  configuration_snapshot: Record<string, unknown>;
  summary_metrics: MetricValue[];
  error_summary: Record<string, unknown> | null;
  model_metadata: Record<string, unknown> | null;
  cost_summary: CostSummary | null;
}

export interface RunCreateInput {
  application_id: string;
  dataset_id: string;
  dataset_version_id?: string | null;
  metric_ids: string[];
  run_config?: Partial<RunConfigInput>;
  include_security_suite?: boolean;
}

export interface ValidateConfigInput {
  application_id: string;
  dataset_id: string;
  dataset_version_id?: string | null;
  metric_ids: string[];
}

export interface ValidateConfigResult {
  applicable: string[];
  inapplicable: { id: string; reason: string }[];
  estimated_cases: number;
}

export interface CaseResult {
  id: string;
  run_id: string;
  test_case_id: string;
  external_id: string | null;
  repeat_index: number;
  outcome: string;
  actual_output: string | null;
  latency_ms: number | null;
  ttft_ms: number | null;
  token_usage: Record<string, number> | null;
  error_type: string | null;
  error_message: string | null;
  metrics: MetricValue[];
}

// ---- Phase 4: Reports & Dashboard ----

export interface RunStatusCount {
  status: string;
  count: number;
}

export interface RecentFailure {
  result_id: string;
  run_id: string;
  external_id: string | null;
  outcome: string;
  error_type: string | null;
  error_message: string | null;
  created_at: string | null;
}

export interface KeyMetricSummary {
  run_id: string;
  application_name: string | null;
  completed_at: string | null;
  success_rate: number | null;
  latency_mean_ms: number | null;
  total_cost_usd: number | null;
  success_rate_status: string;
  latency_status: string;
  cost_status: string;
}

export interface OverviewOut {
  totals: Record<string, number>;
  status_breakdown: RunStatusCount[];
  recent_runs: RunSummary[];
  key_metrics: KeyMetricSummary[];
  recent_failures: RecentFailure[];
}

export interface MetricDelta {
  evaluator_id: string;
  baseline: number | null;
  candidate: number | null;
  delta: number | null;
  regression: boolean | null;
  provenance: string;
  value_kind: string;
  unavailable_reason: string | null;
}

export interface LatencyDelta {
  baseline_mean_ms: number | null;
  candidate_mean_ms: number | null;
  delta_ms: number | null;
  baseline_p95_ms: number | null;
  candidate_p95_ms: number | null;
}

export interface CostDelta {
  baseline_total_usd: number | null;
  candidate_total_usd: number | null;
  delta_usd: number | null;
  unavailable_reason: string | null;
}

export interface CompareOut {
  baseline_run_id: string;
  candidate_run_id: string;
  dataset_compatible: boolean;
  metric_deltas: MetricDelta[];
  newly_failing_case_ids: string[];
  resolved_case_ids: string[];
  latency_delta: LatencyDelta | null;
  cost_delta: CostDelta | null;
  baseline: Record<string, unknown>;
  candidate: Record<string, unknown>;
}

export interface CaseResultDetail extends CaseResult {
  case_input: Record<string, unknown>;
  expected_output: string | null;
  retrieved_document_ids: string[] | null;
  agent_trace: Record<string, unknown> | null;
  category: string | null;
}

// --- Phase 5: security suite catalog (T5.5) ---

export interface SecuritySuiteCase {
  id: string;
  expected_behavior: string;
}

export interface SecuritySuiteCategory {
  category: string;
  case_count: number;
  cases: SecuritySuiteCase[];
}

export interface SecurityCatalog {
  suite_id: string;
  version: string;
  description: string;
  disclaimer: string;
  case_count: number;
  categories: SecuritySuiteCategory[];
}
