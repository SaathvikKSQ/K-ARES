import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Application, Dataset, SampleDatasetInfo } from "../types/api";

vi.mock("../services/applications", () => ({
  listApplications: vi.fn(async () => mockApplications),
  createApplication: vi.fn(),
  updateApplication: vi.fn(),
  deleteApplication: vi.fn(),
  testApplicationConnection: vi.fn(),
  getApplication: vi.fn(),
}));

vi.mock("../services/datasets", () => ({
  listDatasets: vi.fn(async () => mockDatasets),
  getDatasetVersion: vi.fn(),
  listDatasetCases: vi.fn(),
  validateDatasetFile: vi.fn(),
  uploadDataset: vi.fn(),
  listSampleDatasets: vi.fn(async () => mockSamples),
  installSampleDatasets: vi.fn(),
}));

const mockApplications: Application[] = [
  {
    id: "app-1",
    name: "Support RAG v1",
    description: "Mock RAG application",
    application_type: "rag",
    integration_type: "mock",
    base_url: null,
    invoke_path: "",
    has_credentials: false,
    capabilities: {
      exposes_retrieved_docs: true,
      exposes_citations: false,
      exposes_traces: false,
      exposes_token_usage: true,
      streaming: false,
    },
    current_version_label: null,
    is_enabled: true,
    owner: null,
    last_connection_test: { success: true, message: "ok", latency_ms: 3, checked_at: null },
  },
];

const mockDatasets: Dataset[] = [
  {
    id: "ds-1",
    name: "support-qa-v1",
    description: "",
    application_type: "rag",
    owner: null,
    version_count: 2,
  },
];

const mockSamples: SampleDatasetInfo[] = [
  {
    key: "sample-rag-qa",
    name: "RAG QA sample",
    description: "Ten RAG question/answer pairs",
    application_type: "rag",
    case_count: 10,
  },
];

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ApplicationsPage", () => {
  it("renders registered applications with capability masking info", async () => {
    const { default: ApplicationsPage } = await import("./ApplicationsPage");
    renderWithProviders(<ApplicationsPage />);
    expect(await screen.findByText("Support RAG v1")).toBeInTheDocument();
    expect(screen.getByText(/credentials stored|no credentials/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /test connection/i })).toBeInTheDocument();
  });

  it("renders the registration form", async () => {
    const { default: ApplicationsPage } = await import("./ApplicationsPage");
    renderWithProviders(<ApplicationsPage />);
    expect(
      await screen.findByRole("heading", { name: "Register application" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
  });
});

describe("DatasetsPage", () => {
  it("renders datasets, upload form and samples", async () => {
    const { default: DatasetsPage } = await import("./DatasetsPage");
    renderWithProviders(<DatasetsPage />);
    expect(await screen.findByText("support-qa-v1")).toBeInTheDocument();
    const section = screen.getByText("Registered datasets").closest("section") as HTMLElement;
    expect(within(section).getByText(/2 version/i)).toBeInTheDocument();
    expect(await screen.findByText("Bundled sample datasets")).toBeInTheDocument();
    expect(screen.getByText(/RAG QA sample/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upload dataset/i })).toBeInTheDocument();
  });
});