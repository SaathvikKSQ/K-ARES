import { useEffect, useState } from "react";
import { getSecurityCatalog } from "../services/security";
import type { SecurityCatalog } from "../types/api";
import { EmptyState } from "./OverviewPage";

/**
 * Security Evaluation page (T5.5, SR-25).
 * Shows the static, code-versioned controlled security suite catalog with the
 * mandatory disclaimer and an explicit covered-vs-untested disclosure
 * (constitution §4: honest security claims).
 */

// Risk areas deliberately NOT covered by the controlled suite (honesty over
// marketing — SR-25). Static disclosure; suites are versioned in code (D9).
const UNTESTED_AREAS = [
  "Multi-turn and adaptive attacks beyond the listed payloads",
  "Jailbreak techniques outside the controlled payload set",
  "Adversarial ML / model extraction",
  "Runtime data exfiltration through side channels",
  "Infrastructure and network security",
  "Concurrency and resource-exhaustion attacks",
];

export default function SecurityPage() {
  const [catalog, setCatalog] = useState<SecurityCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSecurityCatalog()
      .then((data) => {
        if (!cancelled) setCatalog(data);
      })
      .catch(() => {
        if (!cancelled) setError("Failed to load the security suite catalog.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Security Evaluation</h1>
        {catalog && (
          <span className="text-xs text-slate-500">
            suite {catalog.suite_id} · v{catalog.version} · {catalog.case_count} controlled cases
          </span>
        )}
      </div>

      {/* Mandatory disclaimer (SR-25, metrics.md §8) */}
      <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
        <strong>Disclaimer:</strong>{" "}
        {catalog?.disclaimer ??
          "Passing controlled security tests does not prove an application is secure."}
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          {error}
        </div>
      )}

      {!catalog && !error && (
        <p className="text-sm text-slate-500">Loading security suite catalog...</p>
      )}

      {catalog && catalog.case_count === 0 && (
        <EmptyState
          title="No security suite available"
          hint="No controlled payloads are defined for this deployment."
        />
      )}

      {catalog && catalog.case_count > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold text-slate-800">
              Covered categories ({catalog.categories.length})
            </h2>
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-1 pr-3 font-medium">Category</th>
                  <th className="py-1 pr-3 font-medium">Cases</th>
                  <th className="py-1 font-medium">Expected behavior</th>
                </tr>
              </thead>
              <tbody>
                {catalog.categories.map((cat) => (
                  <tr key={cat.category} className="border-b border-slate-100">
                    <td className="py-2 pr-3 font-mono text-[11px] text-slate-700">
                      {cat.category}
                    </td>
                    <td className="py-2 pr-3 text-slate-700">{cat.case_count}</td>
                    <td className="py-2 text-slate-600">{cat.cases[0]?.expected_behavior}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-[11px] text-slate-500">
              Payloads are static and versioned in code (suite{" "}
              {catalog.suite_id} v{catalog.version}). Runs append these cases
              when the security suite option is enabled; per-case verdicts are{" "}
              <span className="font-mono">pass</span> /{" "}
              <span className="font-mono">fail</span> /{" "}
              <span className="font-mono">inconclusive</span> — an ambiguous
              response is never counted as a pass.
            </p>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold text-slate-800">
              Not covered by this suite
            </h2>
            <ul className="list-disc space-y-1 pl-5 text-xs text-slate-600">
              {UNTESTED_AREAS.map((area) => (
                <li key={area}>{area}</li>
              ))}
            </ul>
            <p className="mt-3 text-[11px] text-slate-500">
              The list above is an explicit disclosure of untested risk
              categories (SR-25). New scenarios require a suite version bump
              and code review (decision D9). No destructive actions are
              executed and no external systems are attacked by this suite.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}