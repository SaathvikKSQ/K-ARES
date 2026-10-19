import { api } from "./api";
import type { CompareOut, OverviewOut } from "../types/api";

/** Reports service (Phase 4): dashboard overview, run comparison, exports. */

export async function getOverview(): Promise<OverviewOut> {
  const { data } = await api.get<OverviewOut>("/dashboard/overview");
  return data;
}

export async function compareRuns(
  baselineRunId: string,
  candidateRunId: string,
): Promise<CompareOut> {
  const { data } = await api.post<CompareOut>("/evaluations/compare", {
    baseline_run_id: baselineRunId,
    candidate_run_id: candidateRunId,
  });
  return data;
}

export type ExportFormat = "json" | "csv";

export const EXPORT_MIME: Record<ExportFormat, string> = {
  json: "application/json",
  csv: "text/csv",
};

/** Downloads the export; returns { filename, blob } so callers can save it. */
export async function exportRun(
  runId: string,
  format: ExportFormat,
): Promise<{ filename: string; blob: Blob }> {
  const response = await api.get<Blob>(`/evaluations/${runId}/export`, {
    params: { format },
    responseType: "blob",
  });
  const disposition = String(
    response.headers["content-disposition"] ?? "",
  );
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const filename = match ? match[1] : `run-${runId}.${format}`;
  return { filename, blob: response.data };
}