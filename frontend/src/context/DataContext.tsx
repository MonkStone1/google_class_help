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

import { api } from "../api.ts";
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
 */
type AuthState = {
  auth: AuthStatus | null;
  login: () => Promise<void>;
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

/** Human-readable reason of the first failed request, or null when all passed. */
function describeFailure(
  result: PromiseSettledResult<unknown> | undefined,
): string | null {
  if (!result || result.status !== "rejected") {
    return null;
  }
  if (result.reason instanceof Error) {
    return result.reason.message;
  }
  return "Google Classroom could not be reached. Showing your last synchronized data.";
}

export function DataProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
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

    if (authRes.status === "fulfilled") setAuth(authRes.value);
    if (statusRes.status === "fulfilled") setStatus(statusRes.value);
    if (coursesRes.status === "fulfilled") setCourses(coursesRes.value);
    if (assignmentsRes.status === "fulfilled") {
      setAssignments(assignmentsRes.value);
    }

    const firstError = results.find((result) => result.status === "rejected");
    setError(describeFailure(firstError));
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

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

  const login = useCallback(async () => {
    try {
      invalidateAllResources();
      await api.login();
      await loadData();
    } catch (err) {
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

  const syncNow = useCallback(async (): Promise<SyncResult | null> => {
    setSyncing(true);
    try {
      const result = await api.sync();
      // Teacher pages read from the resource cache; a fresh sync must drop it
      // so they refetch instead of showing pre-sync data (ADR-0017).
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
    () => ({ auth, login, logout }),
    [auth, login, logout],
  );

  const syncValue = useMemo(
    () => ({ status, loading, syncing, error, syncNow, refresh }),
    [status, loading, syncing, error, syncNow, refresh],
  );

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
