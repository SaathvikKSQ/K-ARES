import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  installSampleDatasets,
  listDatasets,
  listSampleDatasets,
  uploadDataset,
  validateDatasetFile,
} from "../services/datasets";
import type { ApplicationType, ValidationReport } from "../types/api";
import { EmptyState } from "./OverviewPage";

function ValidationReportPanel({ report }: { report: ValidationReport }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs">
      <p className="font-medium text-slate-700">
        Validation: {report.total_rows} rows - {report.valid_rows} valid, {report.invalid_rows} invalid
      </p>
      {report.issues.length > 0 && (
        <ul className="mt-2 space-y-1 text-rose-600">
          {report.issues.slice(0, 20).map((issue, i) => (
            <li key={i}>
              Row {issue.row}, field `{issue.field}`: {issue.message}
            </li>
          ))}
        </ul>
      )}
      {report.warnings.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-amber-700">
            {report.warnings.length} warning(s)
          </summary>
          <ul className="mt-1 space-y-1 text-amber-700">
            {report.warnings.slice(0, 20).map((issue, i) => (
              <li key={i}>
                Row {issue.row}, field `{issue.field}`: {issue.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function UploadDatasetForm() {
  const [name, setName] = useState("");
  const [applicationType, setApplicationType] = useState<ApplicationType>("rag");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const validate = useMutation({
    mutationFn: (f: File) => validateDatasetFile(f, applicationType),
    onSuccess: (r) => {
      setReport(r);
      setError(null);
    },
    onError: (err: unknown) => {
      const message =
        typeof err === "object" && err !== null && "message" in err
          ? String((err as { message: unknown }).message)
          : "Validation request failed";
      setError(message);
      setReport(null);
    },
  });

  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("No file selected");
      return uploadDataset(file, { name: name.trim(), application_type: applicationType, description });
    },
    onSuccess: (detail) => {
      setReport(detail.validation_report);
      setError(null);
      setName("");
      setDescription("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
    onError: (err: unknown) => {
      const message =
        typeof err === "object" && err !== null && "message" in err
          ? String((err as { message: unknown }).message)
          : "Upload failed";
      setError(message);
    },
  });

  const inputCls =
    "w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!name.trim()) {
          setError("Dataset name is required");
          return;
        }
        if (!file) {
          setError("Choose a .jsonl or .csv file");
          return;
        }
        upload.mutate();
      }}
      className="space-y-3 rounded-lg border border-slate-200 bg-white p-4"
    >
      <h2 className="text-sm font-semibold text-slate-700">Upload dataset</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs text-slate-600">
          Dataset name
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. support-qa-v2" />
        </label>
        <label className="block text-xs text-slate-600">
          Application type
          <select
            className={inputCls}
            value={applicationType}
            onChange={(e) => setApplicationType(e.target.value as ApplicationType)}
          >
            <option value="rag">RAG</option>
            <option value="llm">LLM</option>
            <option value="agent">Agent</option>
          </select>
        </label>
        <label className="block text-xs text-slate-600 sm:col-span-2">
          Description (optional)
          <input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label className="block text-xs text-slate-600">
          File (.jsonl or .csv)
          <input
            ref={fileInput}
            type="file"
            accept=".jsonl,.json,.csv"
            className={inputCls}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!file || validate.isPending}
          onClick={() => file && validate.mutate(file)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {validate.isPending ? "Validating..." : "Validate only"}
        </button>
        <button
          type="submit"
          disabled={upload.isPending}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {upload.isPending ? "Uploading..." : "Upload dataset"}
        </button>
      </div>
      {error && <p className="text-xs text-rose-600">{error}</p>}
      {report && <ValidationReportPanel report={report} />}
    </form>
  );
}

function SampleDatasetsPanel() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data: samples } = useQuery({
    queryKey: ["dataset-samples"],
    queryFn: listSampleDatasets,
  });
  const install = useMutation({
    mutationFn: installSampleDatasets,
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
    onError: () => setError("Installing sample datasets failed."),
  });

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">Bundled sample datasets</h2>
        <button
          onClick={() => install.mutate()}
          disabled={install.isPending}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {install.isPending ? "Installing..." : "Install all samples"}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
      {samples && (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {samples.map((s) => (
            <li key={s.key} className="rounded-md border border-slate-100 bg-slate-50 p-3 text-xs">
              <p className="font-medium text-slate-700">{s.name}</p>
              <p className="mt-1 text-slate-500">{s.description}</p>
              <p className="mt-1 text-slate-400">
                {s.application_type} - {s.case_count} cases
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function DatasetsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["datasets"],
    queryFn: listDatasets,
  });

  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Datasets</h1>
      <div className="space-y-4">
        <UploadDatasetForm />
        <SampleDatasetsPanel />
      </div>
      <div className="mt-6">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Registered datasets</h2>
        {isLoading && <p className="text-sm text-slate-500">Loading datasets...</p>}
        {error && <p className="text-sm text-rose-600">Failed to load datasets.</p>}
        {data && data.length === 0 && (
          <EmptyState title="No datasets yet" hint="Upload a JSONL/CSV file or install the bundled samples above." />
        )}
        {data && data.length > 0 && (
          <ul className="space-y-3">
            {data.map((d) => (
              <li
                key={d.id}
                className="rounded-lg border border-slate-200 bg-white p-4"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-800">{d.name}</span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
                    {d.application_type}
                  </span>
                  <span className="text-xs text-slate-500">{d.version_count} version(s)</span>
                </div>
                {d.description && <p className="mt-1 text-xs text-slate-500">{d.description}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
