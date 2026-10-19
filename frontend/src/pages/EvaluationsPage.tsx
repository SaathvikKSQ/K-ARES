import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listRuns } from "../services/evaluations";
import type { RunStatus } from "../types/api";
import { EmptyState } from "./OverviewPage";

const STATUS_CLASSES: Record<RunStatus, string> = {
  queued: "bg-amber-100 text-amber-800",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
  cancelled: "bg-slate-200 text-slate-700",
};

function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium uppercase ${STATUS_CLASSES[status]}`}
    >
      {status}
    </span>
  );
}

export function runStatusLabel(status: RunStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export default function EvaluationsPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["evaluations", page, statusFilter],
    queryFn: () =>
      listRuns({
        page,
        page_size: 25,
        ...(statusFilter ? { status: statusFilter } : {}),
      }),
  });

  const runs = (data?.items ?? []).filter(
    (run) =>
      !search ||
      run.id.toLowerCase().includes(search.toLowerCase()) ||
      (run.triggered_by ?? "").toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Evaluations</h1>
        <Link
          to="/evaluations/new"
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          New evaluation
        </Link>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by run id or user…"
          className="rounded-md border border-slate-300 px-2 py-1 text-xs"
        />
        <label className="text-xs text-slate-600">
          Status
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="ml-1 rounded-md border border-slate-300 px-2 py-1 text-xs"
          >
            <option value="">All</option>
            <option value="queued">queued</option>
            <option value="running">running</option>
            <option value="completed">completed</option>
            <option value="failed">failed</option>
            <option value="cancelled">cancelled</option>
          </select>
        </label>
        {data && data.total > data.page_size && (
          <div className="ml-auto flex items-center gap-2 text-xs text-slate-600">
            <button
              type="button"
              disabled={data.page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
            >
              Prev
            </button>
            <span>
              {data.page}/{Math.max(1, Math.ceil(data.total / data.page_size))} ({data.total}{" "}
              runs)
            </span>
            <button
              type="button"
              disabled={data.page * data.page_size >= data.total}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-500">Loading runs...</p>}
      {isError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          Failed to load evaluation runs.
        </p>
      )}
      {data && runs.length === 0 && (
        <EmptyState
          title="No matching evaluation runs"
          hint="Adjust the filter, search, or create a new run."
        />
      )}
      {data && runs.length > 0 && (
        <ul className="space-y-3" aria-label="Evaluation runs">
          {runs.map((run) => (
            <li key={run.id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex items-center gap-2">
                <Link
                  to={`/evaluations/${run.id}`}
                  className="font-mono text-xs text-blue-700 hover:underline"
                >
                  {run.id.slice(0, 8)}
                </Link>
                <StatusBadge status={run.status} />
                <span className="text-xs text-slate-500">
                  {run.progress.completed ?? 0}/{run.progress.total ?? 0} cases
                </span>
                {run.progress.failed ? (
                  <span className="text-xs text-rose-600">{run.progress.failed} failed</span>
                ) : null}
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {run.metric_ids.join(", ")}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                {run.triggered_by ? `by ${run.triggered_by}` : ""}
                {run.duration_ms != null ? ` - ${(run.duration_ms / 1000).toFixed(1)}s` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}