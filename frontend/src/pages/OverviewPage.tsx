import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "../services/auth";
import { getOverview } from "../services/reports";
import type { RunStatus } from "../types/api";

/** Reusable empty state (no fabricated data — constitution §2). */
export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

const STATUS_BADGE: Record<string, string> = {
  queued: "bg-amber-100 text-amber-800",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
  cancelled: "bg-slate-200 text-slate-700",
};

export default function OverviewPage() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: 1,
  });

  const overview = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: getOverview,
  });

  const totals = overview.data?.totals;
  const breakdown = overview.data?.status_breakdown ?? [];

  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Overview</h1>
      {health && (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatusCard label="API status" value={health.status} />
          <StatusCard label="Database" value={health.database} />
          <StatusCard label="Version" value={health.version} />
          <StatusCard label="Environment" value={health.environment} />
        </div>
      )}

      {overview.isLoading && (
        <p className="text-sm text-slate-500">Loading dashboard data…</p>
      )}
      {overview.isError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          Could not load dashboard aggregates. Verify the backend is running.
        </p>
      )}

      {totals && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <StatusCard label="Applications" value={String(totals.applications ?? 0)} />
            <StatusCard
              label="Enabled apps"
              value={String(totals.applications_enabled ?? 0)}
            />
            <StatusCard label="Datasets" value={String(totals.datasets ?? 0)} />
            <StatusCard label="Runs" value={String(totals.runs ?? 0)} />
            <StatusCard
              label="Cases executed"
              value={String(totals.cases_executed ?? 0)}
            />
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-2 text-xs font-semibold uppercase text-slate-500">
                Run status breakdown
              </h2>
              {breakdown.length === 0 ? (
                <p className="text-xs text-slate-500">No runs yet.</p>
              ) : (
                <ul className="space-y-1.5">
                  {breakdown.map((b) => {
                    const status = b.status as RunStatus;
                    const countTotal = breakdown.reduce((sum, x) => sum + x.count, 0);
                    return (
                      <li key={b.status} className="flex items-center gap-2 text-sm">
                        <span
                          className={`rounded px-2 py-0.5 text-xs font-medium uppercase ${
                            STATUS_BADGE[status] ?? "bg-slate-100 text-slate-700"
                          }`}
                        >
                          {b.status}
                        </span>
                        <span className="font-mono text-sm">{b.count}</span>
                        <div className="h-1.5 flex-1 overflow-hidden rounded bg-slate-100">
                          <div
                            className="h-full bg-blue-500"
                            style={{ width: `${countTotal ? (b.count / countTotal) * 100 : 0}%` }}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-2 text-xs font-semibold uppercase text-slate-500">
                Recent runs
              </h2>
              {(overview.data?.recent_runs.length ?? 0) === 0 ? (
                <p className="text-xs text-slate-500">No runs yet.</p>
              ) : (
                <ul className="space-y-1.5">
                  {overview.data!.recent_runs.map((run) => (
                    <li key={run.id} className="flex items-center gap-2 text-sm">
                      <Link
                        to={`/evaluations/${run.id}`}
                        className="font-mono text-xs text-blue-700 hover:underline"
                      >
                        {run.id.slice(0, 8)}
                      </Link>
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-medium uppercase ${
                          STATUS_BADGE[run.status] ?? "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {run.status}
                      </span>
                      <span className="text-xs text-slate-500">
                        {run.progress.completed ?? 0}/{run.progress.total ?? 0} cases
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="mt-6">
            <h2 className="mb-2 text-sm font-semibold text-slate-700">
              Key metric summaries (latest completed runs)
            </h2>
            {(overview.data?.key_metrics.length ?? 0) === 0 ? (
              <EmptyState
                title="No completed runs yet"
                hint="Key metric summaries appear once runs complete."
              />
            ) : (
              <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-4 py-2">Run</th>
                      <th className="px-4 py-2">Application</th>
                      <th className="px-4 py-2">Success rate</th>
                      <th className="px-4 py-2">Latency (mean)</th>
                      <th className="px-4 py-2">Cost (total)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.data!.key_metrics.map((k) => (
                      <tr key={k.run_id} className="border-b border-slate-100 last:border-0">
                        <td className="px-4 py-2">
                          <Link
                            to={`/evaluations/${k.run_id}`}
                            className="font-mono text-xs text-blue-700 hover:underline"
                          >
                            {k.run_id.slice(0, 8)}
                          </Link>
                        </td>
                        <td className="px-4 py-2 text-xs">
                          {k.application_name ?? <span className="text-slate-400">unknown</span>}
                        </td>
                        <td className="px-4 py-2 text-xs">
                          <MetricCell value={k.success_rate} status={k.success_rate_status} />
                        </td>
                        <td className="px-4 py-2 text-xs">
                          <MetricCell
                            value={k.latency_mean_ms}
                            status={k.latency_status}
                            suffix=" ms"
                          />
                        </td>
                        <td className="px-4 py-2 text-xs">
                          <MetricCell value={k.total_cost_usd} status={k.cost_status} prefix="$" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="mt-6 mb-8">
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Recent failures</h2>
            {(overview.data?.recent_failures.length ?? 0) === 0 ? (
              <p className="text-xs text-slate-500">
                No application errors or timeouts recorded.
              </p>
            ) : (
              <ul className="space-y-2">
                {overview.data!.recent_failures.map((f) => (
                  <li
                    key={f.result_id}
                    className="rounded-md border border-rose-100 bg-rose-50 p-3 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/evaluations/${f.run_id}`}
                        className="font-mono text-xs text-rose-700 hover:underline"
                      >
                        run {f.run_id.slice(0, 8)}
                      </Link>
                      <span className="rounded bg-rose-100 px-1.5 py-0.5 uppercase text-rose-700">
                        {f.outcome}
                      </span>
                      {f.external_id && <span>{f.external_id}</span>}
                      {f.error_type && (
                        <span className="font-medium text-rose-700">{f.error_type}</span>
                      )}
                    </div>
                    {f.error_message && (
                      <p className="mt-1 truncate text-rose-600">{f.error_message}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function MetricCell({
  value,
  status,
  prefix = "",
  suffix = "",
}: {
  value: number | null;
  status: string;
  prefix?: string;
  suffix?: string;
}) {
  if (status !== "computed" || value == null) {
    return (
      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">unavailable</span>
    );
  }
  return (
    <span className="font-mono">
      {prefix}
      {value}
      {suffix}
    </span>
  );
}

export function StatusCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold" data-testid={`status-${label.replace(/\s/g, "-").toLowerCase()}`}>
        {value}
      </p>
    </div>
  );
}
