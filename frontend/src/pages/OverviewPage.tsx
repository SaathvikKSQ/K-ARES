import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "../services/auth";

/** Reusable empty state (no fabricated data — constitution §2). */
export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

export default function OverviewPage() {
  const { data: health, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: 1,
  });

  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Overview</h1>
      {isLoading && <p className="text-sm text-slate-500">Loading platform status…</p>}
      {isError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          Could not reach the K-AERS API. Verify the backend is running.
        </p>
      )}
      {health && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatusCard label="API status" value={health.status} />
          <StatusCard label="Database" value={health.database} />
          <StatusCard label="Version" value={health.version} />
          <StatusCard label="Environment" value={health.environment} />
        </div>
      )}
      <div className="mt-8">
        <EmptyState
          title="No evaluation data yet"
          hint="Register an application and upload a dataset to get started (available in Phase 2)."
        />
      </div>
    </section>
  );
}

function StatusCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold" data-testid={`status-${label.replace(/\s/g, "-").toLowerCase()}`}>
        {value}
      </p>
    </div>
  );
}
