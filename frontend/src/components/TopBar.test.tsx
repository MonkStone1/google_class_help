import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_SETTINGS, type AppStatus } from "../types.ts";
import { SettingsProvider } from "../context/SettingsContext.tsx";
import { TopBar } from "./TopBar.tsx";

// The sync actions are context-driven, and this suite is about what the topbar
// OFFERS — one active control that matches the sentence above it, instead of a
// disabled "Sync" plus advice the user cannot follow (ADR-0032). So the real
// providers stay out; only useSync/useCourses are mocked.
const useSync = vi.fn();
const useCourses = vi.fn();

vi.mock("../context/DataContext.tsx", async () => {
  const actual = await vi.importActual<
    typeof import("../context/DataContext.tsx")
  >("../context/DataContext.tsx");
  return {
    ...actual,
    useAuth: () => ({
      auth: null,
      sessionRequired: false,
      login: vi.fn(),
      logout: vi.fn(),
    }),
    useSync: () => useSync(),
    useCourses: () => useCourses(),
  };
});

const IDLE: AppStatus = {
  authenticated: true,
  last_sync: null,
  last_sync_error: null,
  syncing: false,
  sync_status: "ok",
  last_sync_started_at: null,
  last_sync_finished_at: null,
  sync_stuck_after_seconds: 300,
  total_assignments: 0,
  completed: 0,
  missing: 0,
  overdue: 0,
  due_today: 0,
  average_grade: null,
};

function renderTopBar() {
  // The real SettingsProvider (theme + language, and the i18n dictionary the
  // assertions read); only the sync state is faked.
  return render(
    <SettingsProvider>
      <MemoryRouter>
        <TopBar search="" onSearch={() => {}} />
      </MemoryRouter>
    </SettingsProvider>,
  );
}

describe("TopBar stuck-sync control", () => {
  beforeEach(() => {
    useCourses.mockReturnValue({ courses: [], assignments: [] });
    localStorage.setItem(
      "gc-settings",
      JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("offers an active restart instead of a disabled Sync button", () => {
    // The defect this replaces: the sentence said "try syncing again in a few
    // minutes" while the only Sync button was disabled by `syncing`, so the
    // advice was impossible to follow.
    const syncRestart = vi.fn();
    const syncNow = vi.fn();
    useSync.mockReturnValue({
      status: IDLE,
      loading: false,
      syncing: true,
      syncStuck: true,
      error: null,
      syncNow,
      syncRestart,
      refresh: vi.fn(),
    });

    renderTopBar();

    const restart = screen.getByRole("button", { name: /Restart sync/ });
    expect(restart).toBeEnabled();
    // No second, near-identical control next to it.
    expect(screen.queryByRole("button", { name: "Sync" })).toBeNull();
    expect(screen.getByText(/taking unusually long/)).toBeInTheDocument();
  });

  it("keeps the ordinary Sync button for a healthy run", () => {
    useSync.mockReturnValue({
      status: IDLE,
      loading: false,
      syncing: true,
      syncStuck: false,
      error: null,
      syncNow: vi.fn(),
      syncRestart: vi.fn(),
      refresh: vi.fn(),
    });

    renderTopBar();

    // Still disabled mid-sync: the restart is offered only when the server has
    // declared the run stuck, never as a way to abort a progressing import.
    expect(screen.getByRole("button", { name: /Syncing/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Restart sync/ })).toBeNull();
  });
});
