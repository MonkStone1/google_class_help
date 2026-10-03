import { useCallback, useEffect } from "react";

import {
  api,
  setUnauthorizedHandler,
} from "../../shared/api/index.ts";
import { invalidateAllResources } from "../../shared/hooks/index.ts";
import type { SyncResult } from "../../shared/types/index.ts";

/**
 * The sync commands and the session guard.
 *
 * Both answer the question "what happens when the user acts, or when the
 * session dies" — which is why they live together rather than with the polling
 * loops in `syncEffects.ts`, whose whole job is to notice a change nobody asked
 * for.
 */

/**
 * The three sync commands the shell offers: run, restart a stuck run, reload.
 *
 * Both network calls end the same way — drop the teacher cache and reload the
 * dataset — and neither clears the stuck flag by itself: the replacement run
 * starts from a fresh claim, and until the server reports one the status poll
 * keeps the verdict honest (ADR-0032).
 */
export function useSyncCommands(
  loadData: () => Promise<void>,
  setSyncing: (syncing: boolean) => void,
  setLoading: (loading: boolean) => void,
  setError: (message: string | null) => void,
): {
  syncNow: () => Promise<SyncResult | null>;
  syncRestart: () => Promise<SyncResult | null>;
  refresh: () => Promise<void>;
} {
  const run = useCallback(
    async (restart: boolean): Promise<SyncResult | null> => {
      setSyncing(true);
      try {
        const result = await api.sync(restart);
        // Teacher pages read from the resource cache; a fresh sync must drop it
        // so they refetch instead of showing pre-sync data (ADR-0017). The final
        // data reload happens once the status watcher sees a terminal state.
        invalidateAllResources();
        await loadData();
        return result;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : restart
              ? "Could not restart the synchronization. Showing your last synchronized data."
              : "Sync failed. Showing your last synchronized data.",
        );
        return null;
      } finally {
        setSyncing(false);
      }
    },
    [loadData, setError, setSyncing],
  );

  const syncNow = useCallback(() => run(false), [run]);
  // The restart asks the server to drop its own stuck claim. A refused restart
  // (409, the sync is still healthy by the server's clock) leaves the button
  // available.
  const syncRestart = useCallback(() => run(true), [run]);

  const refresh = useCallback(async () => {
    setLoading(true);
    await loadData();
  }, [loadData, setLoading]);

  return { syncNow, syncRestart, refresh };
}

/** §26: a 401 from ANY request means the application session is gone. */
export function useSessionGuard(clearDataset: () => void): void {
  // Registered once for the whole app, not per request: the handler owns a
  // single "the session ended" answer, whoever happened to trigger it. The
  // cached view goes with it — it may belong to the session that just ended.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearDataset();
      invalidateAllResources();
    });
    return () => setUnauthorizedHandler(null);
  }, [clearDataset]);
}