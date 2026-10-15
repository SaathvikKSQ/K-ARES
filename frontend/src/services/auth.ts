import { api } from "./api";
import type { HealthResponse, LoginResponse, User } from "../types/api";

/** Auth service (Phase 1): login/logout/me against the MVP auth endpoints. */

export async function login(email: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/auth/login", { email, password });
  localStorage.setItem("kaers_token", data.access_token);
  api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
  return data;
}

export async function logout(): Promise<void> {
  try {
    await api.post("/auth/logout");
  } finally {
    localStorage.removeItem("kaers_token");
    delete api.defaults.headers.common.Authorization;
  }
}

export async function fetchMe(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>("/health");
  return data;
}

/** Re-attach a stored token on app start (session continuity). */
export function restoreToken(): void {
  const token = localStorage.getItem("kaers_token");
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  }
}
