import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type Context,
  type ReactNode,
} from "react";

import { api, LOGIN_URL, setUnauthorizedHandler } from "../api.ts";
import type { ApiError } from "../api.ts";
import { invalidateAllResources } from "../lib/resource.ts";
import type {
  AppStatus,
  Assignment,
  AuthStatus,
  Course,
  SyncResult,
} from "../types.ts";

/**
 * Sign-in state: who is logged in and how to change it.
 *
 * `sessionRequired` is the stage-7 signal (§26): it becomes true only when a
 * request answered 401, i.e. this browser holds no application session. The
 * desktop build never sets it (its `/auth/status` always answers 200, with
 * `authenticated: false` until the loopback consent completes), so the
 * desktop workflow is unchanged.
 */
type AuthState = {
  auth: AuthStatus | null;
  sessionRequired: boolean;
  /**
   * Start sign-in. `turnToken` is a solved Turnstile widget token — passed
   * only when the server reports a challenge (DDoS plan §17); desktop and
   * challenge-free hosted flows ignore it.
   */
  login: (turnToken?: string) => Promise<void>;
  logout: () => Promise<void>;
};

/**
 * Synchronization state: how fresh the local cache is and how to refresh it.
 * Kept separate from the data itself so a sync spinner or an error banner does
 * not re-render every list on the screen.
 */
type SyncState = {
  status: AppStatus | null;
  loading: boolean;
  syncing: boolean;
  error: string | null;
  syncNow: () => Promise<SyncResult | null>;
  refresh: () => Promise<void>;
};

/**
 * The locally cached Classroom slice. Changes on a sync or a manual refresh.
 */
type CoursesState = {
  courses: Course[];
  assignments: Assignment[];
};

export type DataState = AuthState & SyncState & CoursesState;

const AuthContext = createContext<AuthState | null>(null);
const SyncContext = createContext<SyncState | null>(null);
const CoursesContext = createContext<CoursesState | null>(null);

/**
 * The signed-out shape of `AuthStatus` (all fields, no invented data). A 401
 * replaces the current value with it so every consumer of `auth` — the
 * settings card, the sign-in gate, the dashboard hint — switches to the login
 * state without waiting for another round trip.
 */
const SIGNED_OUT: AuthStatus = {
  authenticated: false,
  login_in_progress: false,
  error: null,
  auth_url: null,
  user: null,
};

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
  const [error, setError] = useState<string | null>(null);

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

  const login = useCallback(async (turnToken?: string) => {
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
  }, [loadData]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
      // Only drop the teacher cache once the sign-out actually succeeded.
      invalidateAllResources();
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Sign-out failed. Please try again.",
      );
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
      error,
      syncNow,
      refresh,
    };
  }, [status, loading, syncing, error, syncNow, refresh]);

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

function useContextSafe<T>(context: Context<T | null>, name: string): T {
  const value = useContext(context);
  if (value === null) {
    throw new Error(`${name} must be used inside DataProvider`);
  }
  return value;
}

export function useAuth(): AuthState {
  return useContextSafe(AuthContext, "useAuth");
}

export function useSync(): SyncState {
  return useContextSafe(SyncContext, "useSync");
}

export function useCourses(): CoursesState {
  return useContextSafe(CoursesContext, "useCourses");
}

/**
 * Facade over the three contexts, kept for pages that legitimately need
 * everything at once. New code should prefer {@link useAuth}, {@link useSync}
 * or {@link useCourses}: subscribing to all three re-renders on every change.
 */
export function useData(): DataState {
  const auth = useContextSafe(AuthContext, "useData");
  const sync = useContextSafe(SyncContext, "useData");
  const courses = useContextSafe(CoursesContext, "useData");
  return { ...auth, ...sync, ...courses };
}
