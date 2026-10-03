import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.tsx";
import { DEFAULT_SETTINGS } from "../shared/types/index.ts";
import type { AuthStatus } from "../shared/types/index.ts";

const useAuth = vi.fn();
const useSync = vi.fn();

// The real DataProvider would fire network requests; only the auth and
// loading state the gate branches on matter here.
vi.mock("./providers/DataProvider.tsx", async () => {
  const actual = await vi.importActual<
    typeof import("./providers/DataProvider.tsx")
  >("./providers/DataProvider.tsx");
  return {
    ...actual,
    DataProvider: ({ children }: { children: React.ReactNode }) => children,
  };
});
vi.mock("../entities/user/index.ts", async () => {
  const actual = await vi.importActual<
    typeof import("../entities/user/index.ts")
  >("../entities/user/index.ts");
  return {
    ...actual,
    useAuth: () => useAuth(),
  };
});
vi.mock("../features/sync/index.ts", async () => {
  const actual = await vi.importActual<
    typeof import("../features/sync/index.ts")
  >("../features/sync/index.ts");
  return {
    ...actual,
    useSync: () => useSync(),
  };
});
vi.mock("../entities/course/index.ts", async () => {
  const actual = await vi.importActual<
    typeof import("../entities/course/index.ts")
  >("../entities/course/index.ts");
  return {
    ...actual,
    useCourses: () => ({ courses: [], assignments: [] }),
  };
});

vi.mock("../widgets/landing/useSignInChallenge.ts", () => ({
  useSignInChallenge: () => ({
    token: null,
    required: false,
    requested: false,
    pending: false,
    widgetRef: { current: null },
  }),
}));

const SIGNED_OUT: AuthStatus = {
  authenticated: false,
  login_in_progress: false,
  error: null,
  auth_url: null,
  user: null,
};

const SIGNED_IN: AuthStatus = {
  authenticated: true,
  login_in_progress: false,
  error: null,
  auth_url: null,
  user: { id: 1, name: "Test", email: "test@example.com", is_admin: false, is_super_admin: false },
};

function renderApp() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>,
  );
}

describe("AppShell session gate", () => {
  beforeEach(() => {
    useAuth.mockReset();
    useSync.mockReset();
    useSync.mockReturnValue({
      status: null,
      loading: false,
      syncing: false,
      error: null,
      syncNow: vi.fn(),
      refresh: vi.fn(),
    });
    localStorage.setItem(
      "gc-settings",
      JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
    );
  });

  it("shows the landing straight away once the gate is known", () => {
    // The settled state: `auth` is no longer null, so the splash is already
    // gone by the time the gate can be decided.
    useAuth.mockReturnValue({
      auth: SIGNED_OUT,
      sessionRequired: true,
      login: vi.fn(),
      logout: vi.fn(),
    });

    renderApp();

    expect(
      screen.getByRole("heading", { name: "Your Google Classroom in one place" }),
    ).toBeInTheDocument();
  });

  it("shows only a neutral splash while the first response is in flight", () => {
    // t=0 in every deployment mode: no auth answer yet, request still open.
    useAuth.mockReturnValue({
      auth: null,
      sessionRequired: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
    useSync.mockReturnValue({
      status: null,
      loading: true,
      syncing: false,
      error: null,
      syncNow: vi.fn(),
      refresh: vi.fn(),
    });

    renderApp();

    // The dashboard frame with its fake cards must NOT be rendered: it is the
    // flash this splash exists to remove, and on a deep link it would flash
    // the wrong page entirely.
    expect(
      screen.queryByRole("heading", { name: "Your Google Classroom in one place" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Not signed in" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("replaces the splash with the landing as soon as the 401 lands", () => {
    useAuth.mockReturnValue({
      auth: null,
      sessionRequired: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
    useSync.mockReturnValue({
      status: null,
      loading: true,
      syncing: false,
      error: null,
      syncNow: vi.fn(),
      refresh: vi.fn(),
    });
    const { rerender } = renderApp();

    // api.ts raises the 401 synchronously inside `request()`, so `auth` is
    // already SIGNED_OUT while the other three requests are still pending.
    useAuth.mockReturnValue({
      auth: SIGNED_OUT,
      sessionRequired: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    rerender(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Your Google Classroom in one place" }),
    ).toBeInTheDocument();
  });

  it("shows the compact gate when a session that existed is gone", () => {
    // First render authenticated, then the session dies: the landing would be
    // wrong here, the user already knows the site and only needs the way in.
    useAuth.mockReturnValue({
      auth: SIGNED_IN,
      sessionRequired: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
    const { rerender } = renderApp();

    useAuth.mockReturnValue({
      auth: SIGNED_OUT,
      sessionRequired: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    rerender(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    // The SignIn gate, NOT the landing.
    expect(screen.getByRole("heading", { name: "Not signed in" })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Your Google Classroom in one place" }),
    ).not.toBeInTheDocument();
  });

  it("renders the dashboard for a signed-in user", () => {
    useAuth.mockReturnValue({
      auth: SIGNED_IN,
      sessionRequired: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    renderApp();

    // The dashboard shell, not the landing.
    expect(
      screen.queryByRole("heading", { name: "Your Google Classroom in one place" }),
    ).not.toBeInTheDocument();
  });

  it("renders the dashboard on the desktop build, where no session is required", () => {
    useAuth.mockReturnValue({
      auth: SIGNED_OUT,
      sessionRequired: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    renderApp();

    expect(
      screen.queryByRole("heading", { name: "Your Google Classroom in one place" }),
    ).not.toBeInTheDocument();
  });
});
