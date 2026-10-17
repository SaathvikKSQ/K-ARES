import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createApplication,
  deleteApplication,
  listApplications,
  testApplicationConnection,
  updateApplication,
} from "../services/applications";
import type {
  Application,
  ApplicationCreateInput,
  CapabilityFlags,
  ConnectionTestResult,
} from "../types/api";
import { EmptyState } from "./OverviewPage";

const DEFAULT_CAPABILITIES: CapabilityFlags = {
  exposes_retrieved_docs: false,
  exposes_citations: false,
  exposes_traces: false,
  exposes_token_usage: false,
  streaming: false,
};

const emptyForm = {
  name: "",
  description: "",
  application_type: "rag" as ApplicationCreateInput["application_type"],
  integration_type: "mock" as ApplicationCreateInput["integration_type"],
  base_url: "",
  invoke_path: "",
  cred_type: "bearer",
  cred_value: "",
};

function CapabilitiesEditor({
  value,
  onChange,
}: {
  value: CapabilityFlags;
  onChange: (next: CapabilityFlags) => void;
}) {
  const labels: Record<keyof CapabilityFlags, string> = {
    exposes_retrieved_docs: "Retrieved docs",
    exposes_citations: "Citations",
    exposes_traces: "Agent traces",
    exposes_token_usage: "Token usage",
    streaming: "Streaming / TTFT",
  };
  return (
    <fieldset className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 p-3 sm:grid-cols-3">
      <legend className="px-1 text-xs font-medium text-slate-500">Reported capabilities</legend>
      {(Object.keys(labels) as (keyof CapabilityFlags)[]).map((key) => (
        <label key={key} className="flex items-center gap-2 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={value[key]}
            onChange={(e) => onChange({ ...value, [key]: e.target.checked })}
          />
          {labels[key]}
        </label>
      ))}
    </fieldset>
  );
}

function ConnectionBadge({ app }: { app: Application }) {
  const t = app.last_connection_test;
  if (!t) return <span className="text-xs text-slate-400">not tested</span>;
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${
        t.success ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
      }`}
      title={t.checked_at ?? undefined}
    >
      {t.success ? "connected" : "failed"}
      {t.latency_ms != null ? ` - ${t.latency_ms} ms` : ""}
    </span>
  );
}

function RegisterApplicationForm() {
  const [form, setForm] = useState(emptyForm);
  const [capabilities, setCapabilities] = useState<CapabilityFlags>(DEFAULT_CAPABILITIES);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const create = useMutation({
    mutationFn: (payload: ApplicationCreateInput) => createApplication(payload),
    onSuccess: () => {
      setForm(emptyForm);
      setCapabilities(DEFAULT_CAPABILITIES);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (err: unknown) => {
      const message =
        typeof err === "object" && err !== null && "message" in err
          ? String((err as { message: unknown }).message)
          : "Registration failed";
      setError(message);
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Name is required");
      return;
    }
    const payload: ApplicationCreateInput = {
      name: form.name.trim(),
      description: form.description,
      application_type: form.application_type,
      integration_type: form.integration_type,
      base_url: form.integration_type === "rest_api" ? form.base_url || null : null,
      invoke_path: form.integration_type === "rest_api" ? form.invoke_path : "",
      capabilities,
    };
    if (form.integration_type === "rest_api" && form.cred_value.trim()) {
      payload.credentials = { type: form.cred_type, value: form.cred_value.trim() };
    }
    create.mutate(payload);
  };

  const inputCls =
    "w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="text-sm font-semibold text-slate-700">Register application</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs text-slate-600">
          Name
          <input
            className={inputCls}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Support RAG v1"
          />
        </label>
        <label className="block text-xs text-slate-600">
          Application type
          <select
            className={inputCls}
            value={form.application_type}
            onChange={(e) =>
              setForm({ ...form, application_type: e.target.value as typeof form.application_type })
            }
          >
            <option value="rag">RAG</option>
            <option value="llm">LLM</option>
            <option value="agent">Agent</option>
          </select>
        </label>
        <label className="block text-xs text-slate-600">
          Integration
          <select
            className={inputCls}
            value={form.integration_type}
            onChange={(e) =>
              setForm({ ...form, integration_type: e.target.value as typeof form.integration_type })
            }
          >
            <option value="mock">Mock (deterministic)</option>
            <option value="rest_api">REST API</option>
          </select>
        </label>
        {form.integration_type === "rest_api" && (
          <>
            <label className="block text-xs text-slate-600">
              Base URL
              <input
                className={inputCls}
                value={form.base_url}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                placeholder="https://app.example.com/api"
              />
            </label>
            <label className="block text-xs text-slate-600">
              Invoke path (optional)
              <input
                className={inputCls}
                value={form.invoke_path}
                onChange={(e) => setForm({ ...form, invoke_path: e.target.value })}
                placeholder="/evaluate"
              />
            </label>
            <label className="block text-xs text-slate-600">
              Auth type
              <select
                className={inputCls}
                value={form.cred_type}
                onChange={(e) => setForm({ ...form, cred_type: e.target.value })}
              >
                <option value="bearer">Bearer token</option>
                <option value="api_key">API key header</option>
                <option value="basic">Basic</option>
              </select>
            </label>
            <label className="block text-xs text-slate-600">
              Secret (stored encrypted; never returned)
              <input
                className={inputCls}
                type="password"
                value={form.cred_value}
                onChange={(e) => setForm({ ...form, cred_value: e.target.value })}
                placeholder="optional"
              />
            </label>
          </>
        )}
      </div>
      <CapabilitiesEditor value={capabilities} onChange={setCapabilities} />
      {error && <p className="text-xs text-rose-600">{error}</p>}
      <button
        type="submit"
        disabled={create.isPending}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {create.isPending ? "Registering..." : "Register application"}
      </button>
    </form>
  );
}

function ApplicationRow({ app }: { app: Application }) {
  const queryClient = useQueryClient();
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);

  const test = useMutation({
    mutationFn: () => testApplicationConnection(app.id),
    onSuccess: (result) => setTestResult(result),
  });
  const toggle = useMutation({
    mutationFn: () => updateApplication(app.id, { is_enabled: !app.is_enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });
  const remove = useMutation({
    mutationFn: () => deleteApplication(app.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div className="flex items-center gap-2">
          <span className="font-medium text-slate-800">{app.name}</span>
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
            {app.application_type}
          </span>
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            {app.integration_type}
          </span>
          {!app.is_enabled && (
            <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">disabled</span>
          )}
        </div>
        {app.description && <p className="mt-1 text-xs text-slate-500">{app.description}</p>}
        <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
          <ConnectionBadge app={app} />
          <span>{app.has_credentials ? "credentials stored (encrypted)" : "no credentials"}</span>
        </div>
        {testResult && (
          <p className={`mt-1 text-xs ${testResult.success ? "text-emerald-600" : "text-rose-600"}`}>
            {testResult.message}
          </p>
        )}
      </div>
      <div className="flex shrink-0 gap-2">
        <button
          onClick={() => test.mutate()}
          disabled={test.isPending}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {test.isPending ? "Testing..." : "Test connection"}
        </button>
        <button
          onClick={() => toggle.mutate()}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          {app.is_enabled ? "Disable" : "Enable"}
        </button>
        <button
          onClick={() => remove.mutate()}
          className="rounded-md border border-rose-200 px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50"
        >
          Delete
        </button>
      </div>
    </li>
  );
}

export default function ApplicationsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["applications"],
    queryFn: () => listApplications(),
  });

  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Applications</h1>
      <RegisterApplicationForm />
      <div className="mt-6">
        {isLoading && <p className="text-sm text-slate-500">Loading applications...</p>}
        {error && <p className="text-sm text-rose-600">Failed to load applications.</p>}
        {data && data.length === 0 && (
          <EmptyState
            title="No applications registered"
            hint="Register your first application above to start evaluating."
          />
        )}
        {data && data.length > 0 && (
          <ul className="space-y-3">
            {data.map((app) => (
              <ApplicationRow key={app.id} app={app} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
