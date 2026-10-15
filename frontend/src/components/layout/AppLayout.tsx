import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../../features/auth/useAuth";

const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true },
  { to: "/applications", label: "Applications" },
  { to: "/datasets", label: "Datasets" },
  { to: "/evaluations", label: "Evaluations" },
  { to: "/security", label: "Security" },
];

export default function AppLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-slate-200 bg-white p-4">
        <div className="mb-6 text-lg font-semibold tracking-tight">
          K-AERS
          <span className="block text-xs font-normal text-slate-500">
            AI Evaluation, Reliability & Security
          </span>
        </div>
        <nav aria-label="Main navigation" className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm ${
                  isActive
                    ? "bg-blue-50 font-medium text-blue-700"
                    : "text-slate-600 hover:bg-slate-100"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-3 border-b border-slate-200 bg-white px-6 py-3">
          {user ? (
            <>
              <span className="text-sm text-slate-600" data-testid="user-email">
                {user.email}
              </span>
              <button
                type="button"
                onClick={() => void logout()}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
              >
                Log out
              </button>
            </>
          ) : (
            <span className="text-sm text-slate-500">Not signed in</span>
          )}
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
