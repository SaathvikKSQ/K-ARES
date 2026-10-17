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
  const { data, isLoading, isError } = useQuery({
    queryKey: ["evaluations"],
    queryFn: () => listRuns({ page_size: 25 }),
  });

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

      {isLoading && <p className="text-sm text-slate-500">Loading runs...</p>}
      {isError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          Failed to load evaluation runs.
        </p>
      )}
      {data && data.items.length === 0 && (
        <EmptyState
          title="No evaluation runs yet"
          hint="Create a run against a registered application and dataset."
        />
      )}
      {data && data.items.length > 0 && (
        <ul className="space-y-3" aria-label="Evaluation runs">
          {data.items.map((run) => (
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