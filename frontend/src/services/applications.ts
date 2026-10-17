import { api } from "./api";
import type {
  Application,
  ApplicationCreateInput,
  ConnectionTestResult,
} from "../types/api";

/** Application registry service (Phase 2). Credentials are write-only upstream. */

export async function listApplications(enabledOnly = false): Promise<Application[]> {
  const { data } = await api.get<Application[]>("/applications", {
    params: enabledOnly ? { enabled_only: true } : {},
  });
  return data;
}

export async function getApplication(id: string): Promise<Application> {
  const { data } = await api.get<Application>(`/applications/${id}`);
  return data;
}

export async function createApplication(payload: ApplicationCreateInput): Promise<Application> {
  const { data } = await api.post<Application>("/applications", payload);
  return data;
}

export async function updateApplication(
  id: string,
  patch: Partial<ApplicationCreateInput> & { is_enabled?: boolean },
): Promise<Application> {
  const { data } = await api.patch<Application>(`/applications/${id}`, patch);
  return data;
}

export async function deleteApplication(id: string): Promise<void> {
  await api.delete(`/applications/${id}`);
}

export async function testApplicationConnection(id: string): Promise<ConnectionTestResult> {
  const { data } = await api.post<ConnectionTestResult>(`/applications/${id}/connection-test`);
  return data;
}
