import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import App from "../App";
import { AuthProvider } from "../features/auth/useAuth";

function renderApp(route: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[route]}>{<App />}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("App shell", () => {
  it("renders main navigation when authenticated area redirects to login", async () => {
    renderApp("/");
    // Unauthenticated users are redirected to the login page (after auth probe resolves).
    expect(
      await screen.findByRole("heading", { name: /sign in to k-aers/i }),
    ).toBeInTheDocument();
  });

  it("login page renders email and password fields", () => {
    renderApp("/login");
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });
});

describe("AppLayout navigation", () => {
  it("shows the five primary navigation items", async () => {
    // Directly render the layout with a stubbed auth consumer.
    const { default: AppLayout } = await import("../components/layout/AppLayout");
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={["/"]}>{<AppLayout />}</MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    );
    const nav = screen.getByRole("navigation", { name: /main navigation/i });
    for (const label of ["Overview", "Applications", "Datasets", "Evaluations", "Security"]) {
      expect(within(nav).getByText(label)).toBeInTheDocument();
    }
  });
});
