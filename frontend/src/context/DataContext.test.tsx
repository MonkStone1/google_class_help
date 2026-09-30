import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, setUnauthorizedHandler } from "../api.ts";
import type { AppStatus, Assignment, AuthStatus } from "../types.ts";
import { DataProvider, useAuth, useCourses, useSync } from "./DataContext.tsx";

function Probe() {
  const { auth, sessionRequired } = useAuth();
  const { status, syncing, syncStuck, syncNow, syncRestart } = useSync();
  const { assignments } = useCourses();
  return (
    <div>
      <span data-testid="probe">
        {sessionRequired
          ? "gate"
          : auth?.authenticated
            ? "signed-in"
            : "signed-out"}
      </span>
      <span data-testid="sync-state">
        {syncing ? "syncing" : "idle"}:{status?.sync_status ?? "none"}:
        {assignments.length}
      </span>
      <span data-testid="stuck-state">{syncStuck ? "stuck" : "ok"}</span>
      <button type="button" onClick={() => void syncNow()}>
        Sync
      </button>
      <button type="button" onClick={() => void syncRestart()}>
        Restart
      </button>
    </div>
  );
}

function unauthorizedResponse(): Response {
  return {
    ok: false,
    status: 401,
    statusText: "Unauthorized",
    json: async () => ({ detail: "Not signed in." }),
  } as Response;
}

const AUTH: AuthStatus = {
  authenticated: true,
  login_in_progress: false,
  error: null,
  auth_url: null,
  user: { id: 1, name: "Test User", email: "test@example.com" },
};

const IDLE: AppStatus = {
  authenticated: true,
  last_sync: null,
  last_sync_error: null,
  syncing: false,
  sync_status: "pending",
  last_sync_started_at: null,
  last_sync_finished_at: null,
  // ADR-0032: the server owns the stuck threshold; 300 s matches the default
  // backend value these fixtures stand in for.
  sync_stuck_after_seconds: 300,
  total_assignments: 0,
  completed: 0,
  missing: 0,
  overdue: 0,
  due_today: 0,
  average_grade: null,
};

const QUEUED: AppStatus = {
  ...IDLE,
  syncing: true,
  sync_status: "pending",
};

const RUNNING: AppStatus = {
  ...IDLE,
  syncing: true,
  sync_status: "running",
};

const FINISHED: AppStatus = {
  ...IDLE,
  syncing: false,
  sync_status: "ok",
  last_sync: "2026-09-25T12:00:00",
  last_sync_finished_at: "2026-09-25T12:00:05",
};

function assignment(id: string): Assignment {
  return {
    id,
    course_id: "course-1",
    course_name: "Course",
    title: id,
    description: null,
    due_at: null,
    max_points: null,
    work_type: null,
    state: "PUBLISHED",
    alternate_link: null,
    materials: [],
    created_at: null,
    updated_at: null,
    submission_state: null,
    submitted: false,
    graded: false,
    points: null,
    late: false,
    is_overdue: false,
    priority: "low",
    role: "STUDENT",
    student_count: 0,
    submission_count: 0,
    graded_count: 0,
    average_percent: null,
  };
}

function renderProvider() {
  return render(
    <DataProvider>
      <Probe />
    </DataProvider>,
  );
}

async function advanceTimers(milliseconds: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
    await Promise.resolve();
  });
}

describe("DataProvider sync lifecycle", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });

  it("refreshes data and stops the spinner when a worker sync finishes", async () => {
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    const getStatus = vi
      .spyOn(api, "getStatus")
      .mockResolvedValueOnce(QUEUED)
      .mockResolvedValue(FINISHED);
    const getAssignments = vi
      .spyOn(api, "getAssignments")
      .mockResolvedValueOnce([])
      .mockResolvedValue([assignment("fresh-assignment")]);

    renderProvider();
    await advanceTimers(0);
    expect(screen.getByTestId("sync-state")).toHaveTextContent(
      "syncing:pending:0",
    );

    await advanceTimers(1500);
    expect(screen.getByTestId("sync-state")).toHaveTextContent("idle:ok:1");
    // The initial load and the post-queue refresh both read status; the final
    // data load reads it once more after the worker commits the cache.
    expect(getStatus).toHaveBeenCalledTimes(3);
    expect(getAssignments).toHaveBeenCalledTimes(2);
  });

  it("keeps following a queued manual sync beyond the old 20-poll limit", async () => {
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    vi.spyOn(api, "sync").mockResolvedValue({
      ok: true,
      last_sync: null,
      courses: 0,
      assignments: 0,
      error: null,
      queued: true,
      status: "queued",
      restarted: false,
    });
    const getStatus = vi.spyOn(api, "getStatus");
    let statusCalls = 0;
    getStatus.mockImplementation(async () => {
      statusCalls += 1;
      if (statusCalls === 1) return IDLE;
      if (statusCalls === 2) return QUEUED;
      if (statusCalls <= 25) return RUNNING;
      return FINISHED;
    });
    const getAssignments = vi
      .spyOn(api, "getAssignments")
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValue([assignment("manual-fresh-assignment")]);

    renderProvider();
    await advanceTimers(0);
    fireEvent.click(screen.getByRole("button", { name: "Sync" }));
    await advanceTimers(0);
    expect(screen.getByTestId("sync-state")).toHaveTextContent(
      "syncing:pending:0",
    );

    // 24 polls are deliberately more than the old 20-attempt cap.
    for (let index = 0; index < 24; index += 1) {
      await advanceTimers(1500);
    }

    expect(screen.getByTestId("sync-state")).toHaveTextContent("idle:ok:1");
    expect(statusCalls).toBeGreaterThan(25);
    expect(getAssignments).toHaveBeenCalledTimes(3);
  });

  it("flags a sync that the server keeps reporting as running", async () => {
    // A worker killed mid-sync leaves the row `running` forever: the status
    // poll keeps answering "syncing" while nothing happens. The user must get
    // an explanation instead of an endless spinner.
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    vi.spyOn(api, "getAssignments").mockResolvedValue([]);
    // Naive UTC, as the backend serializes it (ADR-0004).
    const staleStart = new Date(Date.now() - 20 * 60 * 1000)
      .toISOString()
      .replace("Z", "");
    const stuck: AppStatus = {
      ...RUNNING,
      last_sync_started_at: staleStart,
    };
    vi.spyOn(api, "getStatus").mockResolvedValue(stuck);

    renderProvider();
    await advanceTimers(0);

    expect(screen.getByTestId("sync-state")).toHaveTextContent(
      "syncing:running:0",
    );
    // The threshold is 5 minutes and the claim is already 20 minutes old, so
    // the verdict is immediate.
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("stuck");
  });

  it("does not flag a sync that started just now", async () => {
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    vi.spyOn(api, "getAssignments").mockResolvedValue([]);
    const freshStart = new Date().toISOString().replace("Z", "");
    vi.spyOn(api, "getStatus").mockResolvedValue({
      ...RUNNING,
      last_sync_started_at: freshStart,
    });

    renderProvider();
    await advanceTimers(0);

    expect(screen.getByTestId("sync-state")).toHaveTextContent(
      "syncing:running:0",
    );
    // A large Classroom import legitimately takes minutes: no premature alarm.
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("ok");
    await advanceTimers(60_000);
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("ok");
  });

  it("clears the stuck flag once the sync finishes", async () => {
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    vi.spyOn(api, "getAssignments").mockResolvedValue([]);
    const staleStart = new Date(Date.now() - 20 * 60 * 1000)
      .toISOString()
      .replace("Z", "");
    const getStatus = vi.spyOn(api, "getStatus");
    getStatus
      .mockResolvedValueOnce({ ...RUNNING, last_sync_started_at: staleStart })
      .mockResolvedValue(FINISHED);

    renderProvider();
    await advanceTimers(0);
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("stuck");

    await advanceTimers(1500);
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("ok");
  });

  it("asks the server to restart when the user acts on a stuck sync", async () => {
    // ADR-0032: the verdict and the action are one flow. A click on the
    // restart must reach the server AS a restart (?restart=true) — a plain
    // sync request would be answered 409 by the very claim we want replaced.
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    vi.spyOn(api, "getAssignments").mockResolvedValue([]);
    const staleStart = new Date(Date.now() - 20 * 60 * 1000)
      .toISOString()
      .replace("Z", "");
    vi.spyOn(api, "getStatus").mockResolvedValue({
      ...RUNNING,
      last_sync_started_at: staleStart,
    });
    const sync = vi.spyOn(api, "sync").mockResolvedValue({
      ok: true,
      last_sync: null,
      courses: 0,
      assignments: 0,
      error: null,
      queued: true,
      status: "queued",
      restarted: true,
    });

    renderProvider();
    await advanceTimers(0);
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("stuck");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Restart" }));
      await Promise.resolve();
    });

    expect(sync).toHaveBeenCalledWith(true);
  });

  it("uses the server's stuck threshold instead of a local guess", async () => {
    // The number the server enforces and the number the dashboard shows must be
    // the same one: a shorter local threshold would offer a restart that gets
    // 409, a longer one would hide a restart that would work.
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    vi.spyOn(api, "getAssignments").mockResolvedValue([]);
    // 4 minutes old with a 60-second server threshold: stuck for the server,
    // far from stuck for the old 5-minute constant.
    const fourMinutesAgo = new Date(Date.now() - 4 * 60 * 1000)
      .toISOString()
      .replace("Z", "");
    vi.spyOn(api, "getStatus").mockResolvedValue({
      ...RUNNING,
      sync_stuck_after_seconds: 60,
      last_sync_started_at: fourMinutesAgo,
    });

    renderProvider();
    await advanceTimers(0);

    expect(screen.getByTestId("stuck-state")).toHaveTextContent("stuck");
  });

  it("does not call a freshly queued sync stuck", async () => {
    // Regression (ADR-0032): a job the worker has not claimed keeps
    // `last_sync_started_at` of the PREVIOUS run. Aging the new job against
    // that hours-old stamp raised "stuck" the instant Sync was pressed — the
    // user was told to restart a sync that had not even started yet.
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    vi.spyOn(api, "getAssignments").mockResolvedValue([]);
    const hoursOld = new Date(Date.now() - 3 * 60 * 60 * 1000)
      .toISOString()
      .replace("Z", "");
    vi.spyOn(api, "getStatus").mockResolvedValue({
      ...QUEUED,
      last_sync_started_at: hoursOld,
    });

    renderProvider();
    await advanceTimers(0);

    expect(screen.getByTestId("sync-state")).toHaveTextContent(
      "syncing:pending",
    );
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("ok");
  });

  it("calls a queued sync stuck only after the threshold has passed", async () => {
    // The other half of the rule above: a job that never gets claimed (the
    // worker died before taking it) MUST still become restartable, or the
    // spinner would be permanent with no action offered.
    vi.spyOn(api, "getAuthStatus").mockResolvedValue(AUTH);
    vi.spyOn(api, "getCourses").mockResolvedValue([]);
    vi.spyOn(api, "getAssignments").mockResolvedValue([]);
    vi.spyOn(api, "getStatus").mockResolvedValue(QUEUED);

    renderProvider();
    await advanceTimers(0);
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("ok");

    await advanceTimers(60_000);
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("ok");
    // The server threshold of the fixture is 300 s.
    await advanceTimers(240_000);
    expect(screen.getByTestId("stuck-state")).toHaveTextContent("stuck");
  });
});

describe("DataProvider 401 handling", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(unauthorizedResponse())),
    );
  });

  afterEach(() => {
    setUnauthorizedHandler(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("moves to the sign-in gate when the session is rejected", async () => {
    render(
      <DataProvider>
        <Probe />
      </DataProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("probe")).toHaveTextContent("gate"),
    );
  });
});
