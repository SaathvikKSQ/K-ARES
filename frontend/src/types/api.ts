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
