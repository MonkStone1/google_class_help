import { useEffect, useRef } from "react";

import { api } from "../../shared/api/index.ts";
import { invalidateAllResources } from "../../shared/hooks/index.ts";
import type { AppStatus, AuthStatus } from "../../shared/types/index.ts";
import { startedAtMs, stuckRemainingMs } from "./dataHelpers.ts";

/**
 * The effects behind the sync and the session, split out of `DataProvider`.
 *
 * Two loops that used to share one 150-line effect are now separate hooks,
 * because they answer different questions and fail differently: the WATCHER
 * follows a run the server reports active and gives up quietly on a network
 * hiccup, while the STUCK VERDICT has to fire even when no new status ever
 * arrives — a killed worker answers with the same row forever, and only the
 * browser clock crosses the threshold (ADR-0032).
 */

/**
 * Follows the server's view of the sync and reloads the dataset once the worker
 * reaches a terminal state.
 */
export function useSyncWatcher(
  status: AppStatus | null,
  loadData: () => Promise<void>,
  onStatus: (next: AppStatus) => void,
  onFinished: () => void,
): void {
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
        onStatus(next);
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
  }, [loadData, status?.syncing, onStatus, onFinished]);
}

/**
 * Flags a sync the server still calls active long after it started.
 *
 * Nothing is cancelled: the backend keeps working, and this only tells the user
 * what to expect instead of leaving a spinner with no explanation.
 */
export function useSyncStuck(
  status: AppStatus | null,
  setSyncStuck: (stuck: boolean) => void,
): void {
  // When this browser first saw the current sync WITHOUT a claim (ADR-0032).
  // A job waiting for the worker keeps `last_sync_started_at` of the PREVIOUS
  // run, so without this baseline the stuck verdict measured the new job
  // against an hours-old stamp and fired the instant Sync was pressed. 0 means
  // "no such sighting", which is also the reset value once a claim appears.
  const queuedSince = useRef(0);

  useEffect(() => {
    if (status?.syncing !== true) {
      queuedSince.current = 0;
      setSyncStuck(false);
      return;
    }
    const claimed = startedAtMs(status) > 0;
    if (claimed) {
      queuedSince.current = 0;
    } else if (queuedSince.current === 0) {
      queuedSince.current = Date.now();
    }

    const remaining = stuckRemainingMs(status, queuedSince.current);
    if (remaining === 0) {
      setSyncStuck(true);
      return;
    }
    setSyncStuck(false);
    const timer = window.setTimeout(() => setSyncStuck(true), remaining);
    return () => window.clearTimeout(timer);
    // `status` as a whole: the verdict reads the whole object, and the status
    // watcher replaces it on every poll.
  }, [status, setSyncStuck]);
}

/**
 * Polls the light `/auth/status` endpoint while an OAuth flow runs in the
 * browser; the full dataset reloads once, when the flow reports success.
 */
export function useLoginPoller(
  loginInProgress: boolean | undefined,
  setAuth: (next: AuthStatus) => void,
  loadData: () => Promise<void>,
): void {
  useEffect(() => {
    if (!loginInProgress) {
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
  }, [loginInProgress, loadData, setAuth]);
}