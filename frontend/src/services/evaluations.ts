import { api } from "./api";
import type {
  CaseResult,
  CaseResultDetail,
  MetricSpec,
  Page,
  RunCreateInput,
  RunDetail,
  RunSummary,
  ValidateConfigInput,
  ValidateConfigResult,
} from "../types/api";

/** Evaluations service (Phase 3): metrics, run lifecycle, results. */

export async function listMetricSpecs(): Promise<MetricSpec[]> {
  const { data } = await api.get<MetricSpec[]>("/metrics");
  return data;
}

export async function validateRunConfig(
  payload: ValidateConfigInput,
): Promise<ValidateConfigResult> {
  const { data } = await api.post<ValidateConfigResult>(
    "/evaluations/validate-config",
    payload,
  );
  return data;
}

export async function createRun(payload: RunCreateInput): Promise<RunSummary> {
  const { data } = await api.post<RunSummary>("/evaluations", payload);
  return data;
}

export async function listRuns(
  params: {
    page?: number;
    page_size?: number;
    status?: string;
    application_id?: string;
  } = {},
): Promise<Page<RunSummary>> {
  const { data } = await api.get<Page<RunSummary>>("/evaluations", { params });
  return data;
}

export async function getRun(runId: string): Promise<RunDetail> {
  const { data } = await api.get<RunDetail>(`/evaluations/${runId}`);
  return data;
}

export async function listRunResults(
  runId: string,
  params: {
    page?: number;
    page_size?: number;
    outcome?: string;
    evaluator_id?: string;
  } = {},
): Promise<Page<CaseResult>> {
  const { data } = await api.get<Page<CaseResult>>(
    `/evaluations/${runId}/results`,
    { params },
  );
  return data;
}

export async function getRunResult(
  runId: string,
  resultId: string,
): Promise<CaseResultDetail> {
  const { data } = await api.get<CaseResultDetail>(
    `/evaluations/${runId}/results/${resultId}`,
  );
  return data;
}

export async function cancelRun(runId: string): Promise<RunSummary> {
  const { data } = await api.post<RunSummary>(`/evaluations/${runId}/cancel`);
  return data;
}