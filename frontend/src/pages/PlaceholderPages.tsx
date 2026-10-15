import { EmptyState } from "./OverviewPage";

/** Placeholder pages for features landing in Phase 2+ (empty states only — no fake data). */

export function ApplicationsPage() {
  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Applications</h1>
      <EmptyState title="No applications registered" hint="Application registration arrives in Phase 2." />
    </section>
  );
}

export function DatasetsPage() {
  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Datasets</h1>
      <EmptyState title="No datasets yet" hint="Dataset upload and validation arrives in Phase 2." />
    </section>
  );
}

export function EvaluationsPage() {
  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Evaluations</h1>
      <EmptyState title="No evaluation runs yet" hint="The evaluation engine arrives in Phase 3." />
    </section>
  );
}

export function SecurityPage() {
  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Security Evaluation</h1>
      <EmptyState title="No security results yet" hint="Controlled security suites arrive in Phase 5." />
      <p className="mt-3 text-xs text-slate-500">
        Note: passing controlled security tests does not prove an application is secure.
      </p>
    </section>
  );
}
