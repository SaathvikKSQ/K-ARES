import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { cancelRun, getRun, getRunResult, listRunResults } from "../services/evaluations";
import { exportRun } from "../services/reports";
import { useAuth } from "../features/auth/useAuth";
import type { MetricValue, RunStatus } from "../types/api";
import { EmptyState } from "./OverviewPage";

function MetricRow({ metric }: { metric: MetricValue }) {
  return (
    <li className="rounded-md border border-slate-100 bg-slate-50 p-3 text-sm">
      <div className="flex items-center gap-2">
        <span className="font-medium text-slate-800">{metric.evaluator_id}</span>
        <span className="rounded bg-slate-200 px-1.5 py-0.5 text-xs text-slate-600">
          {metric.provenance}
        </span>
        {metric.status === "computed" && metric.score != null ? (
          <span className="font-mono text-sm text-slate-900">{metric.score}</span>
        ) : (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
            unavailable
          </span>
        )}
      </div>
      {metric.status === "unavailable" && metric.unavailable_reason && (
        <p className="mt-1 text-xs text-amber-700">
          Unavailable: {metric.unavailable_reason}
        </p>
      )}
      {metric.explanation && (
        <p className="mt-1 text-xs text-slate-500">{metric.explanation}</p>
      )}
    </li>
  );
}

function ResultRow({ result }: { result: import("../types/api").CaseResult }) {
  return (
    <li className="rounded-md border border-slate-200 bg-white p-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="font-medium text-slate-700">
          {result.external_id ?? result.test_case_id.slice(0, 8)}
        </span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 uppercase text-slate-600">
          {result.outcome}
        </span>
        {result.latency_ms != null && (
          <span className="text-slate-400">{result.latency_ms} ms</span>
        )}
        {result.error_type && (
          <span className="text-rose-600">{result.error_type}</span>
        )}
      </div>
      {result.actual_output && (
        <p className="mt-1 truncate text-slate-500">{result.actual_output}</p>
      )}
      {result.metrics.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-2">
          {result.metrics.map((m) => (
            <li key={m.evaluator_id} className="text-slate-500">
              {m.evaluator_id}:{" "}
              {m.status === "computed" && m.score != null ? m.score : "n/a"}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

const ACTIVE_STATUSES: RunStatus[] = ["queued", "running"];

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canCancel = user?.role === "admin" || user?.role === "editor";

  const { data: run, isLoading, isError, error } = useQuery({
    queryKey: ["evaluation", runId],
    queryFn: () => getRun(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      query.state.data && ACTIVE_STATUSES.includes(query.state.data.status) ? 2000 : false,
  });

  const [resultPage, setResultPage] = useState(1);
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [expandedResultId, setExpandedResultId] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const results = useQuery({
    queryKey: ["evaluation-results", runId, resultPage, outcomeFilter],
    queryFn: () =>
      listRunResults(runId as string, {
        page: resultPage,
        page_size: 25,
        ...(outcomeFilter ? { outcome: outcomeFilter } : {}),
      }),
    enabled: Boolean(runId) && run?.status === "completed",
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(runId as string),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["evaluation", runId] });
    },
  });

  const downloadExport = async (format: "json" | "csv") => {
    setExportError(null);
    try {
      const { filename, blob } = await exportRun(runId as string, format);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setExportError(`Export (${format}) failed.`);
    }
  };

  if (isLoading) return <p className="text-sm text-slate-500">Loading run...</p>;
  if (isError || !run) {
    const message =
      typeof error === "object" && error !== null && "message" in error
        ? String((error as { message: unknown }).message)
        : "Run not found or failed to load.";
    return (
      <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
        {message}
      </p>
    );
  }

  const progress = run.progress;

  return (
    <section>
      <div className="mb-4 flex items-center gap-3">
        <Link to="/evaluations" className="text-xs text-blue-700 hover:underline">
          &larr; All runs
        </Link>
        <h1 className="text-xl font-semibold">Run {run.id.slice(0, 8)}</h1>
        <span className="rounded px-2 py-0.5 text-xs font-medium uppercase text-slate-700">
          {run.status}
        </span>
        {canCancel && ACTIVE_STATUSES.includes(run.status) && (
          <button
            type="button"
            onClick={() => cancel.mutate()}
            disabled={cancel.isPending}
            className="rounded-md border border-rose-300 px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50"
          >
            {cancel.isPending ? "Cancelling..." : "Cancel run"}
          </button>
        )}
        {run.status === "completed" && (
          <>
            <button
              type="button"
              onClick={() => void downloadExport("json")}
              className="ml-auto rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Export JSON
            </button>
            <button
              type="button"
              onClick={() => void downloadExport("csv")}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Export CSV
            </button>
          </>
        )}
      </div>
      {exportError && (
        <p role="alert" className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {exportError}
        </p>
      )}

      {cancel.isError && (
        <p role="alert" className="mb-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
          {typeof cancel.error === "object" && cancel.error !== null && "message" in cancel.error
            ? String((cancel.error as { message: unknown }).message)
            : "Cancellation failed."}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <h2 className="mb-2 text-xs font-semibold uppercase text-slate-500">Progress</h2>
          <p className="text-2xl font-semibold">
            {progress.completed ?? 0}/{progress.total ?? 0}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {progress.failed ? `${progress.failed} failed - ` : ""}
            {progress.skipped ? `${progress.skipped} skipped` : ""}
            {run.duration_ms != null ? `- ${(run.duration_ms / 1000).toFixed(1)}s` : ""}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <h2 className="mb-2 text-xs font-semibold uppercase text-slate-500">Config</h2>
          <ul className="space-y-0.5 text-xs text-slate-600">
            <li>concurrency: {run.run_config.concurrency}</li>
            <li>timeout: {run.run_config.timeout_ms} ms</li>
            <li>repeats: {run.run_config.repeats}</li>
            <li>retries: {run.run_config.max_retries}</li>
            <li>rate limit: {run.run_config.rate_limit_rps} rps</li>
          </ul>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <h2 className="mb-2 text-xs font-semibold uppercase text-slate-500">Cost estimate</h2>
          {run.cost_summary ? (
            <p className="text-xs text-slate-600">
              {run.cost_summary.total_usd != null
                ? `${run.cost_summary.total_usd} ${run.cost_summary.currency} total`
                : "unavailable"}
              {run.cost_summary.pricing_version
                ? ` (pricing v${run.cost_summary.pricing_version})`
                : ""}
            </p>
          ) : (
            <p className="text-xs text-slate-500">No cost metrics selected.</p>
          )}
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Aggregate metrics</h2>
          <SummaryChart metrics={run.summary_metrics} />
          {run.summary_metrics.length === 0 ? (
            <EmptyState title="No aggregate metrics yet" hint="Available once the run completes." />
          ) : (
            <ul className="space-y-2">
              {run.summary_metrics.map((m) => (
                <MetricRow key={m.evaluator_id} metric={m} />
              ))}
            </ul>
          )}
        </div>
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Case results</h2>
          {run.status !== "completed" ? (
            <p className="text-xs text-slate-500">
              Results appear as cases are recorded.
            </p>
          ) : results.isLoading ? (
            <p className="text-xs text-slate-500">Loading results...</p>
          ) : results.data && results.data.items.length === 0 ? (
            <EmptyState title="No case results" />
          ) : results.data ? (
            <>
              <div className="mb-2 flex items-center gap-2">
                <label className="text-xs text-slate-600">
                  Outcome
                  <select
                    value={outcomeFilter}
                    onChange={(e) => {
                      setOutcomeFilter(e.target.value);
                      setResultPage(1);
                    }}
                    className="ml-2 rounded-md border border-slate-300 px-2 py-1 text-xs"
                  >
                    <option value="">All</option>
                    <option value="success">success</option>
                    <option value="application_error">application_error</option>
                    <option value="timeout">timeout</option>
                    <option value="invalid_case">invalid_case</option>
                    <option value="skipped">skipped</option>
                  </select>
                </label>
                <div className="ml-auto flex items-center gap-2 text-xs text-slate-600">
                  <button
                    type="button"
                    disabled={results.data.page <= 1}
                    onClick={() => setResultPage((p) => Math.max(1, p - 1))}
                    className="rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                  >
                    Prev
                  </button>
                  <span>
                    {results.data.page}/
                    {Math.max(1, Math.ceil(results.data.total / results.data.page_size))}
                    {" "}
                    ({results.data.total} cases)
                  </span>
                  <button
                    type="button"
                    disabled={results.data.page * results.data.page_size >= results.data.total}
                    onClick={() => setResultPage((p) => p + 1)}
                    className="rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
              <ul className="space-y-2">
                {results.data.items.map((r) => (
                  <li key={r.id}>
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => setExpandedResultId(expandedResultId === r.id ? null : r.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          setExpandedResultId(expandedResultId === r.id ? null : r.id);
                        }
                      }}
                      className="cursor-pointer"
                    >
                      <ResultRow result={r} />
                    </div>
                    {expandedResultId === r.id && (
                      <ResultDetail runId={runId as string} resultId={r.id} />
                    )}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/** Bar chart of computed aggregate metrics (T4.4) — hidden when nothing is computed. */
function SummaryChart({ metrics }: { metrics: MetricValue[] }) {
  const data = metrics
    .filter((m) => m.status === "computed" && m.score != null)
    .map((m) => ({ name: m.evaluator_id, score: m.score as number }));
  if (data.length === 0) return null;
  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">
        Aggregate scores
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 10 }}
            interval={0}
            angle={-25}
            textAnchor="end"
            height={60}
          />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="score" fill="#2563eb" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Expandable per-case detail (T4.2): expected vs actual, references, traces,
 * per-metric explanations, provenance tags. Loaded on demand per result. */
function ResultDetail({ runId, resultId }: { runId: string; resultId: string }) {
  const detail = useQuery({
    queryKey: ["run-result-detail", runId, resultId],
    queryFn: () => getRunResult(runId, resultId),
  });

  if (detail.isLoading) {
    return <p className="mt-1 px-3 text-xs text-slate-500">Loading detail…</p>;
  }
  if (detail.isError || !detail.data) {
    return <p className="mt-1 px-3 text-xs text-rose-600">Could not load result detail.</p>;
  }
  const d = detail.data;

  return (
    <div className="mt-1 rounded-md border border-blue-100 bg-blue-50/50 p-3 text-xs">
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <h3 className="text-[11px] font-semibold uppercase text-slate-500">Expected</h3>
          <p className="mt-0.5 whitespace-pre-wrap text-slate-700">
            {d.expected_output ?? "—"}
          </p>
        </div>
        <div>
          <h3 className="text-[11px] font-semibold uppercase text-slate-500">Actual</h3>
          <p className="mt-0.5 whitespace-pre-wrap text-slate-700">
            {d.actual_output ?? "—"}
          </p>
        </div>
      </div>
      <p className="mt-1 text-slate-500">
        {d.category ? `Category: ${d.category}` : null}
        {d.repeat_index > 0 ? ` repeat #${d.repeat_index}` : ""}
      </p>

      {Object.keys(d.case_input).length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-slate-600">Case input</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-white p-2 text-[11px] text-slate-700">
            {JSON.stringify(d.case_input, null, 2)}
          </pre>
        </details>
      )}

      {d.retrieved_document_ids && d.retrieved_document_ids.length > 0 && (
        <div className="mt-2">
          <h3 className="text-[11px] font-semibold uppercase text-slate-500">
            Retrieved documents (references)
          </h3>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {d.retrieved_document_ids.map((id) => (
              <li
                key={id}
                className="rounded bg-white px-1.5 py-0.5 font-mono text-[11px] shadow-sm"
              >
                {id}
              </li>
            ))}
          </ul>
        </div>
      )}

      {d.agent_trace && (
        <details className="mt-2">
          <summary className="cursor-pointer text-slate-600">Agent trace</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-white p-2 text-[11px] text-slate-700">
            {JSON.stringify(d.agent_trace, null, 2)}
          </pre>
        </details>
      )}

      <div className="mt-2">
        <h3 className="text-[11px] font-semibold uppercase text-slate-500">Case metrics</h3>
        <ul className="mt-1 space-y-1">
          {d.metrics.map((m) => (
            <li key={m.evaluator_id} className="rounded bg-white p-2">
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-800">{m.evaluator_id}</span>
                <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] uppercase text-blue-700">
                  {m.provenance}
                </span>
                {m.status === "computed" && m.score != null ? (
                  <span className="font-mono text-slate-900">{m.score}</span>
                ) : (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">
                    unavailable
                  </span>
                )}
              </div>
              {m.status === "unavailable" && m.unavailable_reason && (
                <p className="mt-0.5 text-amber-700">Unavailable: {m.unavailable_reason}</p>
              )}
              {m.explanation && <p className="mt-0.5 text-slate-500">{m.explanation}</p>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}