import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { api, LOGIN_URL, setUnauthorizedHandler } from "../../shared/api/index.ts";
import type { ApiError } from "../../shared/api/index.ts";
import { invalidateAllResources } from "../../shared/hooks/useResource.ts";
import {
  AuthContext,
  SIGNED_OUT,
  useContextSafe,
  type AuthState,
} from "../../entities/user/index.ts";
import {
  CoursesContext,
  type CoursesState,
} from "../../entities/course/index.ts";
import {
  SyncContext,
  type SyncState,
} from "../../features/sync/index.ts";
import type {
  AppStatus,
  Assignment,
  AuthStatus,
  Course,
  SyncResult,
} from "../../shared/types/index.ts";

/** Everything the provider owns at once; kept for the pages that need it all. */
export type DataState = AuthState & SyncState & CoursesState;

/**
 * Fallback stuck threshold, seconds — used only until the server has answered
 * at least once. The authoritative value is `sync_stuck_after_seconds` from
 * `GET /api/status` (ADR-0032): the dashboard must not decide "stuck" on one
 * number while `POST /api/sync?restart=true` enforces another, or it would
 * either offer a restart the server refuses or hide one it would accept.
 */
const STUCK_SYNC_SECONDS = 5 * 60;

/**
 * Start of the CLAIMED run in epoch milliseconds, or 0 when the server row
 * carries no stamp.
 *
 * `last_sync_started_at` is naive UTC (ADR-0004), so `Z` is appended; a value
 * that already carries an offset is parsed as-is. It is only meaningful while
 * ``sync_status === "running"`` — until the worker claims a job, this field
 * still describes the PREVIOUS run (see the stuck verdict below).
 */
function startedAtMs(status: AppStatus): number {
  const raw = status.last_sync_started_at;
  if (!raw) {
    return 0;
  }
  const parsed = Date.parse(raw.endsWith("Z") ? raw : `${raw}Z`);
  return Number.isNaN(parsed) ? 0 : parsed;
}


/** A 401 is a session problem, not a transport problem (§26). */
function isUnauthorized(reason: unknown): boolean {
  return reason instanceof Error && (reason as ApiError).status === 401;
}

/** Human-readable reason of the first failed request, or null when all passed. */
function describeFailure(
  results: readonly PromiseSettledResult<unknown>[],
): string | null {
  const failure = results.find(
    (result) => result.status === "rejected" && !isUnauthorized(result.reason),
  );
  if (!failure || failure.status !== "rejected") {
    return null;
  }
  if (failure.reason instanceof Error) {
    return failure.reason.message;
  }
  return "Google Classroom could not be reached. Showing your last synchronized data.";
}

export function DataProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [sessionRequired, setSessionRequired] = useState(false);
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncStuck, setSyncStuck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // When this browser first saw the current sync WITHOUT a claim (ADR-0032).
  // A job waiting for the worker keeps `last_sync_started_at` of the PREVIOUS
  // run, so without this baseline the stuck verdict measured the new job
  // against an hours-old stamp and fired the instant Sync was pressed. 0 means
  // "no such sighting", which is also the reset value once a claim appears.
  const queuedSince = useRef(0);

  const loadData = useCallback(async () => {
    // allSettled, not all: a failing /auth/status (backend restarting) must
    // not discard the courses and assignments that did load.
    const results = await Promise.allSettled([
      api.getAuthStatus(),
      api.getStatus(),
      api.getCourses(),
      api.getAssignments(),
    ] as const);

    const [authRes, statusRes, coursesRes, assignmentsRes] = results;

    if (authRes.status === "fulfilled") {
      setAuth(authRes.value);
      // A readable status means this browser HAS a session (hosted) or is on
      // the desktop build; either way the sign-in gate can stand down.
      if (authRes.value.authenticated) {
        setSessionRequired(false);
      }
    }
    if (statusRes.status === "fulfilled") setStatus(statusRes.value);
    if (coursesRes.status === "fulfilled") setCourses(coursesRes.value);
    if (assignmentsRes.status === "fulfilled") {
      setAssignments(assignmentsRes.value);
    }

    setError(describeFailure(results));
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // §26: a 401 from ANY request means the application session is gone. Drop
  // the cached view (it may belong to a session that just ended) and let the
  // sign-in gate take over. Registered once for the whole app.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setAuth(SIGNED_OUT);
      setSessionRequired(true);
      setStatus(null);
      setCourses([]);
      setAssignments([]);
      invalidateAllResources();
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  // Poll while an OAuth login flow is running in the browser. Only the light
  // /auth/status endpoint is hit per tick; the full dataset reloads once, when
  // the flow reports success.
  useEffect(() => {
    if (!auth?.login_in_progress) {
      return;
    }
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getAuthStatus();
        if (cancelled) return;
        setAuth(next);
        if (!next.login_in_progress) {
          window.clearInterval(timer);
          await loadData(); // final load, once, after the sign-in lands
        }
      } catch {
        // A network hiccup just means the next tick retries.
      }
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [auth?.login_in_progress, loadData]);

  const login = useCallback(
    async (turnToken?: string) => {
      invalidateAllResources();
      setError(null);
      try {
        if (turnToken) {
          // Turnstile challenge solved (DDoS plan §17): the backend verified
          // the token at Cloudflare and handed back the Google consent URL.
          const { redirect_url } = await api.loginStart(turnToken);
          window.location.assign(redirect_url);
          return;
        }
        await api.login();
        await loadData();
      } catch (err) {
        const status = err instanceof Error ? (err as ApiError).status : 0;
        // Hosted mode deliberately disables POST /auth/login (405): the only
        // way in is a full-page navigation into the server-owned OAuth flow,
        // where the browser never touches the Google token (§25/§26).
        if (status === 405) {
          window.location.assign(LOGIN_URL);
          return;
        }
        if (status === 403) {
          // The server asked for a Turnstile challenge (expired/missing
          // token). Send the browser back to the sign-in gate so the widget
          // is rendered again.
          if (window.location.search.includes("challenge=required")) {
            window.location.reload();
          } else {
            window.location.assign("/?challenge=required");
          }
          return;
        }
        setError(
          err instanceof Error
            ? err.message
            : "Google authentication failed. Please try signing in again.",
        );
      }
    },
    [loadData],
  );

  const logout = useCallback(async (): Promise<boolean> => {
    try {
      await api.logout();
      // Only drop the teacher cache once the sign-out actually succeeded.
      invalidateAllResources();
      await loadData();
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Sign-out failed. Please try again.",
      );
      return false;
    }
  }, [loadData]);

  // Follow every active server-side sync, including a job that is still queued
  // after sign-in. The status row is the source of truth: a queued job has
  // ``sync_status == "pending"`` but ``syncing == true`` until the worker
  // claims it. There is deliberately no fixed attempt limit here — Classroom
  // imports can legitimately take longer than 50 seconds. When the status turns
  // terminal, invalidate teacher resources and reload the cache once.
  useEffect(() => {
    if (status?.syncing !== true) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    const schedule = () => {
      timer = window.setTimeout(() => {
        void poll();
      }, 1500);
    };

    const poll = async () => {
      try {
        const next = await api.getStatus();
        if (cancelled) return;
        setStatus(next);
        if (next.syncing) {
          schedule();
          return;
        }
        setSyncStuck(false);
        // The worker has committed the final status before this request sees
        // it, so the data reads below observe the completed cache.
        invalidateAllResources();
        await loadData();
      } catch {
        // A temporary network failure must not turn a real running sync into a
        // permanently spinning button; retry on the next tick.
        if (!cancelled) schedule();
      }
    };

    schedule();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [loadData, status?.syncing]);

  // Flag a sync that the server still calls active long after it started. The
  // status watcher above re-renders on every tick, but the stuck verdict also
  // has to appear when NO new status arrives (a killed worker answers with the
  // same row forever, and the browser clock is what crosses the threshold), so
  // it is a separate one-shot timer rather than part of that loop. Nothing is
  // cancelled: the backend keeps working, this only tells the user what to
  // expect instead of leaving a spinner with no explanation.
  //
  // Which clock the age is measured on is the subtle part (ADR-0032):
  // - a CLAIMED run (``sync_status === "running"``) carries its own
  //   ``last_sync_started_at``, and that server stamp is authoritative;
  // - a job still QUEUED (``sync_status === "pending"`` with ``sync_requested``)
  //   does not — the field still describes the previous run, routinely hours
  //   old, so aging the new job against it reported "stuck" immediately after
  //   the user pressed Sync. Such a job is aged from the first moment this
  //   browser saw it instead, which also covers a page opened mid-queue;
  // - a row with no usable stamp at all falls into the same local baseline
  //   rather than reporting an age of "since 1970".
  useEffect(() => {
    if (status?.syncing !== true) {
      queuedSince.current = 0;
      setSyncStuck(false);
      return;
    }
    const threshold = status.sync_stuck_after_seconds || STUCK_SYNC_SECONDS;
    const claimedAt =
      status.sync_status === "running" ? startedAtMs(status) : 0;
    if (claimedAt > 0) {
      queuedSince.current = 0;
    } else if (queuedSince.current === 0) {
      queuedSince.current = Date.now();
    }
    const since = claimedAt > 0 ? claimedAt : queuedSince.current;
    const remaining = Math.max(0, threshold * 1000 - (Date.now() - since));
    if (remaining === 0) {
      setSyncStuck(true);
      return;
    }
    setSyncStuck(false);
    const timer = window.setTimeout(() => setSyncStuck(true), remaining);
    return () => window.clearTimeout(timer);
    // `status` as a whole: the effect reads the whole object through
    // startedAtMs(), and the status watcher replaces it on every poll.
  }, [status]);

  const syncNow = useCallback(async (): Promise<SyncResult | null> => {
    setSyncing(true);
    try {
      const result = await api.sync();
      // Teacher pages read from the resource cache; a fresh sync must drop it
      // so they refetch instead of showing pre-sync data (ADR-0017). The final
      // data reload is performed by the status watcher above once the worker
      // reaches a terminal state.
      invalidateAllResources();
      await loadData();
      return result;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Sync failed. Showing your last synchronized data.",
      );
      return null;
    } finally {
      setSyncing(false);
    }
  }, [loadData]);

  const syncRestart = useCallback(async (): Promise<SyncResult | null> => {
    // ADR-0032: the restart asks the server to drop its own stuck claim. It
    // does NOT clear the stuck flag here on purpose — the replacement run
    // starts from a fresh claim, and until the server reports one the status
    // poll keeps the verdict honest. A refused restart (409, the sync is still
    // healthy by the server's clock) leaves the button available.
    setSyncing(true);
    try {
      const result = await api.sync(true);
      invalidateAllResources();
      await loadData();
      return result;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not restart the synchronization. Showing your last synchronized data.",
      );
      return null;
    } finally {
      setSyncing(false);
    }
  }, [loadData]);

  const refresh = useCallback(async () => {
    setLoading(true);
    await loadData();
  }, [loadData]);

  // Three independent values instead of one: a sync tick now re-renders only
  // the components subscribed to SyncState, not every list on the screen.
  const authValue = useMemo(
    () => ({ auth, sessionRequired, login, logout }),
    [auth, sessionRequired, login, logout],
  );

  // A queued job is active from the moment it is requested. The status
  // row remains `pending` until the worker claims it, but the UI must
  // already show the spinner and follow it through completion.
  const syncValue = useMemo(() => {
    // `syncing` covers both a queued job and one the worker has claimed.
    // The status response keeps `sync_status` as `pending` during the queue,
    // so relying on that string alone leaves the spinner stale forever.
    const serverRunning = status?.syncing === true;
    return {
      status,
      loading,
      syncing: syncing || serverRunning,
      syncStuck: syncStuck && (syncing || serverRunning),
      error,
      syncNow,
      syncRestart,
      refresh,
    };
  }, [
    status,
    loading,
    syncing,
    syncStuck,
    error,
    syncNow,
    syncRestart,
    refresh,
  ]);

  const coursesValue = useMemo(
    () => ({ courses, assignments }),
    [courses, assignments],
  );

  return (
    <AuthContext.Provider value={authValue}>
      <SyncContext.Provider value={syncValue}>
        <CoursesContext.Provider value={coursesValue}>
          {children}
        </CoursesContext.Provider>
      </SyncContext.Provider>
    </AuthContext.Provider>
  );
}

/**
 * Facade over the three contexts, kept for pages that legitimately need
 * everything at once. New code should prefer `useAuth`, `useSync` or
 * `useCourses`: subscribing to all three re-renders on every change.
 *
 * It stays HERE rather than in a layer of its own because it is a convenience
 * over the assembly's own providers — there is nothing about it a screen could
 * use without the provider that fills the contexts.
 */
export function useData(): DataState {
  const auth = useContextSafe(AuthContext, "useData");
  const sync = useContextSafe(SyncContext, "useData");
  const courses = useContextSafe(CoursesContext, "useData");
  return { ...auth, ...sync, ...courses };
}
