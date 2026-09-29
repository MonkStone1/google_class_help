import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api.ts";
import { SettingsProvider } from "../context/SettingsContext.tsx";
import { DEFAULT_SETTINGS, type AuthStatus } from "../types.ts";
import { Settings } from "./Settings.tsx";

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: toastMock }));

const useAuth = vi.fn();
const useSync = vi.fn();

// Only the hooks the page reads: a real DataProvider would fire the network
// requests this suite has nothing to do with.
vi.mock("../context/DataContext.tsx", async () => {
  const actual = await vi.importActual<
    typeof import("../context/DataContext.tsx")
  >("../context/DataContext.tsx");
  return {
    ...actual,
    DataProvider: ({ children }: { children: React.ReactNode }) => children,
    useAuth: () => useAuth(),
    useSync: () => useSync(),
    useCourses: () => ({ courses: [], assignments: [] }),
  };
});

function renderSettings() {
  localStorage.setItem(
    "gc-settings",
    JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
  );
  return render(
    <SettingsProvider>
      <Settings />
    </SettingsProvider>,
  );
}

describe("Settings cache clearing", () => {
  beforeEach(() => {
    toastMock.success.mockReset();
    toastMock.error.mockReset();
    useAuth.mockReset();
    useSync.mockReset();
    useAuth.mockReturnValue({
      auth: null,
      sessionRequired: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
    useSync.mockReturnValue({
      status: null,
      loading: false,
      syncing: false,
      error: null,
      syncNow: vi.fn().mockResolvedValue(null),
      refresh: vi.fn(),
    });
  });

  it("reports a successful clear as a toast instead of a page banner", async () => {
    vi.spyOn(api, "clearCache").mockResolvedValue({ ok: true });
    renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /Clear local data/ }));
    fireEvent.click(screen.getByRole("button", { name: /Yes, delete/ }));

    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith(
        "Local cached data cleared.",
      ),
    );
    // The old `alert alert-info` banner is gone: a result that outlives the
    // click used to sit at the top of the page until the next render.
    expect(document.querySelector(".alert")).toBeNull();
  });

  it("reports a failed clear with the error tone", async () => {
    vi.spyOn(api, "clearCache").mockRejectedValue(new Error("nope"));
    renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /Clear local data/ }));
    fireEvent.click(screen.getByRole("button", { name: /Yes, delete/ }));

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith("Could not clear the cache."),
    );
    // A failure was previously painted with the blue info style.
    expect(toastMock.success).not.toHaveBeenCalled();
  });
});

describe("Settings sign-out", () => {
  const SIGNED_IN: AuthStatus = {
    authenticated: true,
    login_in_progress: false,
    error: null,
    auth_url: null,
    user: { id: 1, name: "Test User", email: "test@example.com" },
  };

  /** The trigger and the confirmation share one label, so pick the last. */
  function signOutButton(): HTMLElement {
    const buttons = screen.getAllByRole("button", { name: "Sign out" });
    return buttons[buttons.length - 1];
  }

  beforeEach(() => {
    toastMock.error.mockReset();
    useAuth.mockReset();
    useSync.mockReset();
    useSync.mockReturnValue({
      status: null,
      loading: false,
      syncing: false,
      error: null,
      syncNow: vi.fn().mockResolvedValue(null),
      refresh: vi.fn(),
    });
  });

  it("stays quiet when the sign-out actually happened", async () => {
    useAuth.mockReturnValue({
      auth: SIGNED_IN,
      sessionRequired: false,
      login: vi.fn(),
      logout: vi.fn().mockResolvedValue(true),
    });
    renderSettings();

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    fireEvent.click(signOutButton());

    await waitFor(() => expect(useAuth().logout).toHaveBeenCalled());
    // The UI moves on by itself; a "signed out" toast would only add noise.
    expect(toastMock.error).not.toHaveBeenCalled();
  });

  it("says so when the sign-out failed", async () => {
    useAuth.mockReturnValue({
      auth: SIGNED_IN,
      sessionRequired: false,
      login: vi.fn(),
      logout: vi.fn().mockResolvedValue(false),
    });
    renderSettings();

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    fireEvent.click(signOutButton());

    // Without this the user has no feedback at all: the shared `error` is only
    // rendered on the dashboard, and they are still signed in.
    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith(
        "Sign-out failed. Please try again.",
      ),
    );
  });
});
