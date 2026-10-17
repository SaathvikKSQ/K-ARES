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
export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}
