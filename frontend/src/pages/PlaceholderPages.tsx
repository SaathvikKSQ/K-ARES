import { EmptyState } from "./OverviewPage";

/** Placeholder pages for features landing in Phase 4+ (empty states only - no fake data). */

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
