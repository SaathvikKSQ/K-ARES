import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cancelRun, getRun, listRunResults } from "../services/evaluations";
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

  const results = useQuery({
    queryKey: ["evaluation-results", runId],
    queryFn: () => listRunResults(runId as string, { page_size: 25 }),
    enabled: Boolean(runId) && run?.status === "completed",
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(runId as string),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["evaluation", runId] });
    },
  });

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
      </div>

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
            <ul className="space-y-2">
              {results.data.items.map((r) => (
                <ResultRow key={r.id} result={r} />
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </section>
  );
}