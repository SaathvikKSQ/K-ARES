import { api } from "./api";
import type {
  ApplicationType,
  Dataset,
  DatasetVersionDetail,
  SampleDatasetInfo,
  TestCase,
  ValidationReport,
} from "../types/api";

/** Dataset service (Phase 2): upload, validation, versions, cases, samples. */

export async function listDatasets(): Promise<Dataset[]> {
  const { data } = await api.get<Dataset[]>("/datasets");
  return data;
}

export async function getDatasetVersion(
  datasetId: string,
  versionNumber?: number,
): Promise<DatasetVersionDetail> {
  const { data } = await api.get<DatasetVersionDetail>(`/datasets/${datasetId}`, {
    params: versionNumber ? { version_number: versionNumber } : {},
  });
  return data;
}

export async function listDatasetCases(
  datasetId: string,
  versionNumber: number,
  params: { case_status?: "valid" | "invalid"; category?: string; limit?: number; offset?: number } = {},
): Promise<TestCase[]> {
  const { data } = await api.get<TestCase[]>(
    `/datasets/${datasetId}/versions/${versionNumber}/cases`,
    { params },
  );
  return data;
}

export async function validateDatasetFile(
  file: File,
  applicationType: ApplicationType,
): Promise<ValidationReport> {
  const form = new FormData();
  form.append("file", file);
  form.append("application_type", applicationType);
  const { data } = await api.post<ValidationReport>("/datasets/validate", form);
  return data;
}

export async function uploadDataset(
  file: File,
  meta: { name: string; application_type: ApplicationType; description?: string },
): Promise<DatasetVersionDetail> {
  const form = new FormData();
  form.append("file", file);
  form.append("name", meta.name);
  form.append("application_type", meta.application_type);
  if (meta.description) form.append("description", meta.description);
  const { data } = await api.post<DatasetVersionDetail>("/datasets", form);
  return data;
}

export async function listSampleDatasets(): Promise<SampleDatasetInfo[]> {
  const { data } = await api.get<SampleDatasetInfo[]>("/datasets/samples");
  return data;
}

export async function installSampleDatasets(): Promise<DatasetVersionDetail[]> {
  const { data } = await api.post<DatasetVersionDetail[]>("/datasets/samples/install");
  return data;
}
