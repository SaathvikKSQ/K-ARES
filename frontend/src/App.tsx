import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import ApplicationsPage from "./pages/ApplicationsPage";
import DatasetsPage from "./pages/DatasetsPage";
import { EvaluationsPage, SecurityPage } from "./pages/PlaceholderPages";
import { useAuth } from "./features/auth/useAuth";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="p-6 text-sm text-slate-500">Loading...</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<OverviewPage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/datasets" element={<DatasetsPage />} />
        <Route path="/evaluations" element={<EvaluationsPage />} />
        <Route path="/security" element={<SecurityPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
