import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "../../shared/api/index.ts";
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
} from "../../shared/types/index.ts";
import { useAuthActions } from "./authActions.ts";
import { describeFailure } from "./dataHelpers.ts";
import {
  useLoginPoller,
  useSyncStuck,
  useSyncWatcher,
} from "./syncEffects.ts";
import {
  useSessionGuard,
  useSyncCommands,
} from "./syncCommands.ts";

/**
 * The assembly's data source: the auth answer, the sync state and the dataset.
 *
 * It was 453 lines holding a transport session, three contexts, an OAuth
 * poller and a stuck-sync clock. What is left here is the part that cannot be
 * stated without React: when to load, what each context carries. The decisions
 * moved next door — `dataHelpers.ts` for the rules that have no React in them,
 * `syncEffects.ts` for the loops, `authActions.ts` for the browser dead ends.
 *
 * Three contexts rather than one, so a sync tick re-renders the components that
 * subscribed to the sync and not every list on the screen.
 */

/** Everything the provider owns at once; kept for the pages that need it all. */
export type DataState = AuthState & SyncState & CoursesState;

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

  // §26: a 401 from ANY request means the application session is gone. The
  // cached view goes with it — it may belong to the session that just ended —
  // and the sign-in gate takes over.
  const clearDataset = useCallback(() => {
    setAuth(SIGNED_OUT);
    setSessionRequired(true);
    setStatus(null);
    setCourses([]);
    setAssignments([]);
  }, []);
  useSessionGuard(clearDataset);
  useLoginPoller(auth?.login_in_progress, setAuth, loadData);
  useSyncStuck(status, setSyncStuck);
  useSyncWatcher(status, loadData, setStatus, () => setSyncStuck(false));

  const { login, logout } = useAuthActions(loadData, setError);
  const { syncNow, syncRestart, refresh } = useSyncCommands(
    loadData,
    setSyncing,
    setLoading,
    setError,
  );

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
