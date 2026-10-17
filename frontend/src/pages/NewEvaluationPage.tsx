import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { listApplications } from "../services/applications";
import { listDatasets } from "../services/datasets";
import { createRun, listMetricSpecs, validateRunConfig } from "../services/evaluations";
import type { MetricSpec } from "../types/api";

export function metricSortKey(spec: MetricSpec): string {
  return spec.id;
}

function MetricCheckbox({
  spec,
  checked,
  onToggle,
}: {
  spec: MetricSpec;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <li>
      <label className="flex items-start gap-2 rounded-md border border-slate-200 p-2 text-xs hover:bg-slate-50">
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          aria-label={spec.id}
          className="mt-0.5"
        />
        <span>
          <span className="font-medium text-slate-800">{spec.id}</span>
          <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-slate-500">
            {spec.scope} - {spec.provenance}
          </span>
          {spec.required_fields.length > 0 && (
            <span className="ml-1 text-slate-400">
              needs: {spec.required_fields.join(", ")}
            </span>
          )}
          <p className="mt-1 text-slate-500">{spec.description}</p>
        </span>
      </label>
    </li>
  );
}

export default function NewEvaluationPage() {
  const navigate = useNavigate();
  const [applicationId, setApplicationId] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof validateRunConfig>> | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const apps = useQuery({ queryKey: ["applications"], queryFn: () => listApplications() });
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });
  const metrics = useQuery({
    queryKey: ["metric-specs"],
    queryFn: listMetricSpecs,
    select: (specs) => [...specs].sort((a, b) => metricSortKey(a).localeCompare(metricSortKey(b))),
  });

  const selectedSpecs = useMemo(
    () => (metrics.data ?? []).filter((m) => selected.includes(m.id)),
    [metrics.data, selected],
  );

  const toggleMetric = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]));
    setPreview(null);
  };

  const validate = useMutation({
    mutationFn: () =>
      validateRunConfig({
        application_id: applicationId,
        dataset_id: datasetId,
        metric_ids: selected,
      }),
    onSuccess: (result) => {
      setPreview(result);
      setActionError(null);
    },
    onError: (err: unknown) => {
      setPreview(null);
      setActionError(extractMessage(err, "Config validation failed."));
    },
  });

  const create = useMutation({
    mutationFn: () =>
      createRun({
        application_id: applicationId,
        dataset_id: datasetId,
        metric_ids: selected,
      }),
    onSuccess: (run) => navigate(`/evaluations/${run.id}`),
    onError: (err: unknown) => setActionError(extractMessage(err, "Could not create the run.")),
  });

  const inputCls =
    "w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";

  return (
    <section className="max-w-3xl">
      <h1 className="mb-4 text-xl font-semibold">New evaluation</h1>

      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="eval-app" className="mb-1 block text-xs font-medium text-slate-600">
              Application
            </label>
            <select
              id="eval-app"
              value={applicationId}
              onChange={(e) => {
                setApplicationId(e.target.value);
                setPreview(null);
              }}
              className={inputCls}
            >
              <option value="">Select an application...</option>
              {(apps.data ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.application_type})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="eval-dataset" className="mb-1 block text-xs font-medium text-slate-600">
              Dataset
            </label>
            <select
              id="eval-dataset"
              value={datasetId}
              onChange={(e) => {
                setDatasetId(e.target.value);
                setPreview(null);
              }}
              className={inputCls}
            >
              <option value="">Select a dataset...</option>
              {(datasets.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.version_count} version(s))
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Metrics</h2>
          {metrics.isLoading && <p className="text-xs text-slate-500">Loading metrics...</p>}
          {metrics.data && (
            <ul className="grid gap-2 sm:grid-cols-2">
              {metrics.data.map((spec) => (
                <MetricCheckbox
                  key={spec.id}
                  spec={spec}
                  checked={selected.includes(spec.id)}
                  onToggle={() => toggleMetric(spec.id)}
                />
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={!applicationId || !datasetId || selected.length === 0 || validate.isPending}
            onClick={() => validate.mutate()}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {validate.isPending ? "Checking..." : "Check applicability"}
          </button>
          <button
            type="button"
            disabled={!applicationId || !datasetId || selected.length === 0 || create.isPending}
            onClick={() => create.mutate()}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {create.isPending ? "Starting..." : "Start evaluation"}
          </button>
          {selectedSpecs.length > 0 && (
            <span className="text-xs text-slate-500">
              {selectedSpecs.length} metric(s) selected
            </span>
          )}
        </div>

        {actionError && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {actionError}
          </p>
        )}

        {preview && (
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs">
            <p className="font-medium text-slate-700">
              Applicability: {preview.applicable.length} applicable -{" "}
              {preview.estimated_cases} valid case(s)
            </p>
            {preview.inapplicable.length > 0 && (
              <ul className="mt-2 space-y-1 text-amber-700">
                {preview.inapplicable.map((item) => (
                  <li key={item.id}>
                    {item.id}: {item.reason}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function extractMessage(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null && "message" in err) {
    return String((err as { message: unknown }).message);
  }
  return fallback;
}