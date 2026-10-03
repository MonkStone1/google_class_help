import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../shared/api/index.ts";
import { DataProvider } from "../providers/index.ts";
import { SettingsProvider } from "../../shared/settings/index.ts";
import { DEFAULT_SETTINGS, type AppStatus, type AuthStatus } from "../../shared/types/index.ts";
import { SyncToaster } from "./SyncToaster.tsx";

// The real sonner is deliberately not involved here: this suite tests WHEN the
// app decides to announce something, not how the announcement is painted.
const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}));

vi.mock("sonner", async () => {
  const actual = await vi.importActual<typeof import("sonner")>(
    "sonner",
  );
  return {
    ...actual,
   toast: toastMock 
  };
});

const AUTH: AuthStatus = {
  authenticated: true,
  login_in_progress: false,
  error: null,
  auth_url: null,
  user: { id: 1, name: "Test User", email: "test@example.com", is_admin: false, is_super_admin: false },
};

const IDLE: AppStatus = {
  authenticated: true,
  last_sync: null,
  last_sync_error: null,
  syncing: false,
  sync_status: "pending",
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

const QUEUED: AppStatus = { ...IDLE, syncing: true, sync_status: "pending" };

const FINISHED: AppStatus = {
  ...IDLE,
  sync_status: "ok",
  last_sync: "2026-09-25T12:00:00",
  last_sync_started_at: "2026-09-25T11:59:55",
  last_sync_finished_at: "2026-09-25T12:00:05",
};

const FAILED: AppStatus = {
  ...IDLE,
  sync_status: "error",
  last_sync_error: "Google Classroom could not be reached.",
  last_sync_finished_at: "2026-09-25T12:00:07",
};

const NEEDS_REAUTH: AppStatus = {
  ...IDLE,
  sync_status: "needs_reauth",
  last_sync_error: "Google access has expired.",
  last_sync_finished_at: "2026-09-25T12:00:09",
};

function renderWatcher() {
  return render(
    <SettingsProvider>
      <DataProvider>
        <SyncToaster />
      </DataProvider>
    </SettingsProvider>,
  );
}

async function advanceTimers(milliseconds: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
    await Promise.resolve();
  });
}

describe("SyncToaster", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    toastMock.success.mockReset();
    toastMock.error.mockReset();
    toastMock.warning.mockReset();
    toastMock.info.mockReset();
    // Pin the language so the assertions compare against the English strings.
    localStorage.setItem(
      "gc-settings",
      JSON.stringify({ ...DEFAULT_SETTINGS, language: "en" }),
    );
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    vi.spyOn(api, "getAssignments").mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("announces a finished worker sync", async () => {
    vi.spyOn(api, "getStatus")
      .mockResolvedValueOnce(QUEUED)
      .mockResolvedValue(FINISHED);

    renderWatcher();
    await advanceTimers(0);
    expect(toastMock.success).not.toHaveBeenCalled();

    await advanceTimers(1500);

    expect(toastMock.success).toHaveBeenCalledTimes(1);
    expect(toastMock.success).toHaveBeenCalledWith(
      "Synchronization complete",
      expect.objectContaining({
        description: expect.stringContaining("Classroom data updated at"),
      }),
    );
  });

  it("announces a failed sync with the server's own reason", async () => {
    vi.spyOn(api, "getStatus")
      .mockResolvedValueOnce(QUEUED)
      .mockResolvedValue(FAILED);

    renderWatcher();
    await advanceTimers(0);
    await advanceTimers(1500);

    expect(toastMock.error).toHaveBeenCalledWith("Synchronization failed", {
      description: "Google Classroom could not be reached.",
    });
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it("treats a broken Google grant as a warning, not a failure", async () => {
    vi.spyOn(api, "getStatus")
      .mockResolvedValueOnce(QUEUED)
      .mockResolvedValue(NEEDS_REAUTH);

    renderWatcher();
    await advanceTimers(0);
    await advanceTimers(1500);

    expect(toastMock.warning).toHaveBeenCalledWith("Google access expired", {
      description: "Google access has expired.",
    });
    expect(toastMock.error).not.toHaveBeenCalled();
  });

  it("stays quiet when a finished sync is already the first thing it sees", async () => {
    // Opening the dashboard on an account whose last run completed earlier is
    // not an event; announcing it would greet every page load with a toast.
    // This is also the regression guard for the null-status baseline: before it,
    // the very first answer looked like a change and fired here every time.
    vi.spyOn(api, "getStatus").mockResolvedValue(FINISHED);

    renderWatcher();
    await advanceTimers(0);
    await advanceTimers(1500);

    expect(toastMock.success).not.toHaveBeenCalled();
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(toastMock.warning).not.toHaveBeenCalled();
  });

  it("does not repeat itself while the same finished stamp keeps coming back", async () => {
    // After the terminal status the provider reloads the dataset, and the final
    // load reads /api/status again — the same stamp must stay silent.
    const getStatus = vi
      .spyOn(api, "getStatus")
      .mockResolvedValueOnce(QUEUED)
      .mockResolvedValue(FINISHED);

    renderWatcher();
    await advanceTimers(0);
    await advanceTimers(1500);
    await advanceTimers(1500);
    await advanceTimers(1500);

    expect(getStatus.mock.calls.length).toBeGreaterThan(1);
    expect(toastMock.success).toHaveBeenCalledTimes(1);
  });
});
