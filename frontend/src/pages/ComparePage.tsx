import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { listRuns } from "../services/evaluations";
import { compareRuns } from "../services/reports";
import type { CompareOut, MetricDelta } from "../types/api";
import { EmptyState } from "./OverviewPage";

/** LOWER_IS_BETTER ids where a rising number is a regression (mirrors backend). */
const LOWER_IS_BETTER = new Set(["performance.latency", "cost.estimated_total"]);

const COMPARED_OUT_IDS = new Set(["performance.latency", "cost.estimated_total"]);

export default function ComparePage() {
  const runsQuery = useQuery({
    queryKey: ["evaluations", "completed", 1],
    queryFn: () => listRuns({ page: 1, page_size: 50, status: "completed" }),
  });

  const completed = runsQuery.data?.items ?? [];
  const [baselineId, setBaselineId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [result, setResult] = useState<CompareOut | null>(null);
  const [isComparing, setIsComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errorText = (err: unknown): string => {
    if (typeof err === "string") return err;
    if (err && typeof err === "object" && "message" in err) return String(err.message);
    return "Comparison failed.";
  };

  const runCompare = async () => {
    if (!baselineId || !candidateId || baselineId === candidateId) return;
    setIsComparing(true);
    setError(null);
    try {
      setResult(await compareRuns(baselineId, candidateId));
    } catch (err) {
      setResult(null);
      setError(errorText(err));
    } finally {
      setIsComparing(false);
    }
  };

  const chartData = useMemo(() => {
    if (!result) return [];
    return result.metric_deltas
      .filter(
        (d) =>
          !COMPARED_OUT_IDS.has(d.evaluator_id) &&
          d.baseline != null &&
          d.candidate != null,
      )
      .map((d) => ({
        metric: d.evaluator_id,
        Baseline: d.baseline as number,
        Candidate: d.candidate as number,
      }));
  }, [result]);

  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Run Comparison</h1>

      {runsQuery.isLoading && <p className="text-sm text-slate-500">Loading runs…</p>}

      {completed.length < 2 ? (
        <EmptyState
          title="Need at least two completed runs"
          hint="Start evaluations against the same application and dataset to compare versions."
        />
      ) : (
        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4">
          <Selector
            id={baselineId}
            onChange={setBaselineId}
            runs={completed}
            label="Baseline"
            excludeId={candidateId}
          />
          <Selector
            id={candidateId}
            onChange={setCandidateId}
            runs={completed}
            label="Candidate"
            excludeId={baselineId}
          />
          <button
            type="button"
            onClick={() => void runCompare()}
            disabled={!baselineId || !candidateId || baselineId === candidateId || isComparing}
            className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isComparing ? "Comparing…" : "Compare"}
          </button>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-6">
          {!result.dataset_compatible && (
            <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Warning: the two runs used different dataset versions — per-case comparisons may be
              unreliable.
            </p>
          )}

          {chartData.length > 0 && (
            <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-3 text-xs font-semibold uppercase text-slate-500">
                Metric comparison
              </h2>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="metric"
                    tick={{ fontSize: 10 }}
                    interval={0}
                    angle={-25}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Baseline" fill="#94a3b8" />
                  <Bar dataKey="Candidate" fill="#2563eb" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
              <h2 className="mb-2 text-xs font-semibold uppercase text-slate-500">
                Latency delta
              </h2>
              {result.latency_delta ? (
                <div className="space-y-1 text-xs">
                  <p>
                    mean: {result.latency_delta.baseline_mean_ms ?? "n/a"} →{" "}
                    {result.latency_delta.candidate_mean_ms ?? "n/a"} ms{" "}
                    <DeltaBadge
                      delta={result.latency_delta.delta_ms}
                      lowerIsBetter
                    />
                  </p>
                  <p>
                    p95: {result.latency_delta.baseline_p95_ms ?? "n/a"} →{" "}
                    {result.latency_delta.candidate_p95_ms ?? "n/a"} ms
                  </p>
                </div>
              ) : (
                <p className="text-xs text-slate-500">Latency not measured in both runs.</p>
              )}
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
              <h2 className="mb-2 text-xs font-semibold uppercase text-slate-500">Cost delta</h2>
              {result.cost_delta ? (
                result.cost_delta.unavailable_reason ? (
                  <p className="text-xs text-amber-700">
                    Unavailable: {result.cost_delta.unavailable_reason}
                  </p>
                ) : (
                  <div className="space-y-1 text-xs">
                    <p>
                      total: ${result.cost_delta.baseline_total_usd ?? "n/a"} → $
                      {result.cost_delta.candidate_total_usd ?? "n/a"}
                    </p>
                    <p>
                      delta: <DeltaBadge delta={result.cost_delta.delta_usd} lowerIsBetter />
                    </p>
                  </div>
                )
              ) : (
                <p className="text-xs text-slate-500">Cost not available.</p>
              )}
            </div>
          </div>

          <h2 className="mb-2 mt-6 text-sm font-semibold text-slate-700">Metric deltas</h2>
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-sm" data-testid="metric-deltas">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-2">Metric</th>
                  <th className="px-4 py-2">Baseline</th>
                  <th className="px-4 py-2">Candidate</th>
                  <th className="px-4 py-2">Delta</th>
                  <th className="px-4 py-2">Provenance</th>
                </tr>
              </thead>
              <tbody>
                {result.metric_deltas.map((d) => (
                  <DeltaRow key={d.evaluator_id} delta={d} />
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <CaseFlipList
              title="Newly failing cases"
              ids={result.newly_failing_case_ids}
              tone="rose"
            />
            <CaseFlipList title="Resolved cases" ids={result.resolved_case_ids} tone="emerald" />
          </div>
        </div>
      )}
    </section>
  );
}

function Selector({
  id,
  onChange,
  runs,
  label,
  excludeId,
}: {
  id: string;
  onChange: (value: string) => void;
  runs: { id: string; created_at: string | null }[];
  label: string;
  excludeId: string;
}) {
  return (
    <label className="text-xs font-medium text-slate-600">
      {label}
      <select
        value={id}
        onChange={(e) => onChange(e.target.value)}
        className="ml-2 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
      >
        <option value="">Select run…</option>
        {runs
          .filter((r) => r.id !== excludeId || r.id === id)
          .map((r) => (
            <option key={r.id} value={r.id}>
              {r.id.slice(0, 8)}
              {r.created_at ? ` (${r.created_at.slice(0, 16).replace("T", " ")})` : ""}
            </option>
          ))}
      </select>
    </label>
  );
}

function DeltaBadge({
  delta,
  lowerIsBetter,
}: {
  delta: number | null;
  lowerIsBetter: boolean;
}) {
  if (delta == null) {
    return <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">unavailable</span>;
  }
  if (delta === 0) {
    return <span className="rounded bg-slate-200 px-1.5 py-0.5 text-slate-700">no change</span>;
  }
  const isRegression = delta > 0 === lowerIsBetter;
  const cls = isRegression ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700";
  return (
    <span className={`rounded px-1.5 py-0.5 font-medium ${cls}`} data-testid="delta-badge">
      {delta > 0 ? "+" : ""}
      {delta}
    </span>
  );
}

function DeltaRow({ delta }: { delta: MetricDelta }) {
  const regression = delta.regression === true;
  return (
    <tr className={`border-b border-slate-100 last:border-0 ${regression ? "bg-rose-50" : ""}`}>
      <td className="px-4 py-2">
        <span className="font-mono text-xs text-slate-800">{delta.evaluator_id}</span>
        {delta.unavailable_reason && (
          <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
            unavailable: {delta.unavailable_reason}
          </span>
        )}
      </td>
      <td className="px-4 py-2 font-mono text-xs">{delta.baseline ?? "n/a"}</td>
      <td className="px-4 py-2 font-mono text-xs">{delta.candidate ?? "n/a"}</td>
      <td className="px-4 py-2 text-xs">
        <DeltaBadge delta={delta.delta} lowerIsBetter={LOWER_IS_BETTER.has(delta.evaluator_id)} />
      </td>
      <td className="px-4 py-2 text-xs text-slate-500">{delta.provenance}</td>
    </tr>
  );
}

function CaseFlipList({
  title,
  ids,
  tone,
}: {
  title: string;
  ids: string[];
  tone: "rose" | "emerald";
}) {
  const toneClass =
    tone === "rose"
      ? "border-rose-100 bg-rose-50 text-rose-700"
      : "border-emerald-100 bg-emerald-50 text-emerald-700";
  return (
    <div className={`rounded-lg border p-4 ${toneClass}`}>
      <h2 className="mb-2 text-xs font-semibold uppercase">{title}</h2>
      {ids.length === 0 ? (
        <p className="text-xs opacity-70">None.</p>
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {ids.map((id) => (
            <li key={id} className="rounded bg-white px-2 py-0.5 font-mono text-xs shadow-sm">
              {id.length > 12 ? `${id.slice(0, 12)}…` : id}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}