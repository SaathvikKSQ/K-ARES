import { render, screen } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import SecurityPage from "./SecurityPage";
import type { SecurityCatalog } from "../types/api";

const mockCatalog: SecurityCatalog = {
  suite_id: "core",
  version: "v1",
  description: "Core controlled security suite",
  disclaimer: "Passing this security suite does not prove the application is secure.",
  case_count: 2,
  categories: [
    {
      category: "prompt_injection",
      case_count: 1,
      cases: [{ id: "sec-pi-01", expected_behavior: "Refuse or stay on task" }],
    },
    {
      category: "sensitive_disclosure",
      case_count: 1,
      cases: [{ id: "sec-sd-01", expected_behavior: "Refuse; no sensitive content" }],
    },
  ],
};

vi.mock("../services/security", () => ({
  getSecurityCatalog: vi.fn(async () => mockCatalog),
}));

describe("SecurityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the catalog with disclaimer and untested disclosure", async () => {
    render(<SecurityPage />);
    expect(await screen.findByText("prompt_injection")).toBeInTheDocument();
    expect(screen.getByText(/does not prove the application is secure/i)).toBeInTheDocument();
    expect(screen.getByText("Not covered by this suite")).toBeInTheDocument();
    expect(screen.getByText(/Multi-turn and adaptive attacks/i)).toBeInTheDocument();
  });
});