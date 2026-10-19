import { api } from "./api";
import type { SecurityCatalog } from "../types/api";

/** Security suite service (Phase 5): static code-versioned suite catalog. */

export async function getSecurityCatalog(): Promise<SecurityCatalog> {
  const { data } = await api.get<SecurityCatalog>("/security/suites");
  return data;
}