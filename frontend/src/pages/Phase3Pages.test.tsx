import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Application,
  Dataset,
  MetricSpec,
  RunDetail,
  RunSummary,
  ValidateConfigResult,
} from "../types/api";

vi.mock("../services/evaluations", () => ({
  listMetricSpecs: vi.fn(async () => mockMetricSpecs),
  validateRunConfig: vi.fn(async () => mockValidation),
  createRun: vi.fn(async () => mockRunSummary),
  listRuns: vi.fn(async () => ({ items: [mockRunSummary], page: 1, page_size: 25, total: 1 })),
  getRun: vi.fn(async () => mockRunDetail),
  listRunResults: vi.fn(async () => ({ items: [], page: 1, page_size: 25, total: 0 })),
  getRunResult: vi.fn(),
  cancelRun: vi.fn(),
}));

vi.mock("../features/auth/useAuth", () => ({
  useAuth: vi.fn(() => ({ user: { email: "admin@kaers.dev", role: "admin" }, logout: vi.fn() })),
}));

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
  listSampleDatasets: vi.fn(),
  installSampleDatasets: vi.fn(),
}));

const mockMetricSpecs: MetricSpec[] = [
  {
    id: "answer.exact_match",
    name: "Exact Match",
    description: "Fraction of successful repeats matching the expected output.",
    version: "1.0.0",
    provenance: "measured",
    value_kind: "score",
    scope: "case",
    application_types: [],
    required_fields: ["expected_output"],
    capabilities_required: [],
    config_schema: {},
  },
  {
    id: "reliability.success_rate",
    name: "Success Rate",
    description: "Fraction of invocations that succeeded.",
    version: "1.0.0",
    provenance: "measured",
    value_kind: "rate",
    scope: "run",
    application_types: [],
    required_fields: [],
    capabilities_required: [],
    config_schema: {},
  },
];

const mockApplications: Application[] = [
  {
    id: "app-1",
    name: "Support RAG v1",
    description: "",
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
    last_connection_test: null,
  },
];

const mockDatasets: Dataset[] = [
  {
    id: "ds-1",
    name: "support-qa-v1",
    description: "",
    application_type: "rag",
    owner: null,
    version_count: 1,
  },
];

const mockRunSummary: RunSummary = {
  id: "11111111-2222-3333-4444-555555555555",
  application_id: "app-1",
  dataset_id: "ds-1",
  dataset_version_id: "v-1",
  status: "completed",
  progress: { total: 3, completed: 3, failed: 0, skipped: 0 },
  metric_ids: ["answer.exact_match", "reliability.success_rate"],
  triggered_by: "admin@kaers.dev",
  created_at: "2026-10-17T00:00:00+00:00",
  started_at: "2026-10-17T00:00:01+00:00",
  completed_at: "2026-10-17T00:00:05+00:00",
  duration_ms: 4000,
};

const mockRunDetail: RunDetail = {
  ...mockRunSummary,
  run_config: {
    concurrency: 4,
    timeout_ms: 30000,
    max_retries: 1,
    repeats: 1,
    rate_limit_rps: 0,
  },
  configuration_snapshot: {},
  summary_metrics: [
    {
      evaluator_id: "reliability.success_rate",
      evaluator_version: "1.0.0",
      provenance: "measured",
      value_kind: "rate",
      status: "computed",
      score: 1,
      unavailable_reason: null,
      explanation: "3 of 3 invocations",
      details: { hits: 3, total: 3 },
    },
    {
      evaluator_id: "performance.token_usage",
      evaluator_version: "1.0.0",
      provenance: "measured",
      value_kind: "tokens",
      status: "unavailable",
      score: null,
      unavailable_reason: "application did not report token usage",
      explanation: null,
      details: {},
    },
  ],
  error_summary: null,
  model_metadata: null,
  cost_summary: null,
};

const mockValidation: ValidateConfigResult = {
  applicable: ["answer.exact_match"],
  inapplicable: [
    {
      id: "performance.token_usage",
      reason: "application does not expose capability 'exposes_token_usage'",
    },
  ],
  estimated_cases: 3,
};

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EvaluationsPage", () => {
  it("renders run history with status and progress", async () => {
    const { default: EvaluationsPage } = await import("./EvaluationsPage");
    renderWithProviders(<EvaluationsPage />);
    // Await on data-flagged content: the status filter select also contains
    // the literal "completed", so await something only present after load.
    expect(await screen.findByText("3/3 cases")).toBeInTheDocument();
    expect(screen.getByText(/answer.exact_match, reliability.success_rate/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /new evaluation/i })).toBeInTheDocument();
  });
});

describe("NewEvaluationPage", () => {
  it("renders application/dataset selects and metric checkboxes", async () => {
    const { default: NewEvaluationPage } = await import("./NewEvaluationPage");
    renderWithProviders(<NewEvaluationPage />);
    expect(await screen.findByLabelText(/application/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/dataset/i)).toBeInTheDocument();
    expect(
      await screen.findByRole("checkbox", { name: "answer.exact_match" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "reliability.success_rate" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /check applicability/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /start evaluation/i }),
    ).toBeInTheDocument();
  });
});

describe("RunDetailPage", () => {
  it("renders aggregates and unavailable reasons for completed runs", async () => {
    const { default: RunDetailPage } = await import("./RunDetailPage");
    const { Routes, Route } = await import("react-router-dom");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <MemoryRouter initialEntries={["/evaluations/11111111-2222-3333-4444-555555555555"]}>
        <QueryClientProvider client={queryClient}>
          <Routes>
            <Route path="/evaluations/:runId" element={<RunDetailPage />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText(/run 11111111/i)).toBeInTheDocument();
    expect(screen.getByText("3/3")).toBeInTheDocument();
    // The summary appears twice (bar-chart axis + metric row) now that
    // a Recharts bar chart accompanies the metric list.
    const section = screen.getByText("Aggregate metrics").closest("div") as HTMLElement;
    expect(within(section).getAllByText("reliability.success_rate").length).toBeGreaterThanOrEqual(1);
    expect(
      within(section).getByText(/application did not report token usage/),
    ).toBeInTheDocument();
    expect(within(section).getByText("unavailable")).toBeInTheDocument();
  });
});