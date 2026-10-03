/**
 * The synchronization state, as the shell and the sync button see it.
 *
 * The CONTEXT is here, in the feature that owns the behaviour, and not in the
 * provider that fills it: `app/providers/` is assembly and pages may not import
 * it (guardrail #7), while "how fresh is the cache and how do I refresh it" is
 * a question about the sync feature itself.
 *
 * `useSyncState` holds the polling and the stuck verdict; this file holds what a
 * consumer needs to answer. They are split because the first is a mechanism with
 * timers and the second is a contract — the topbar, the toast and the sidebar
 * all depend on the second and none of them on the first.
 */

import { createContext } from "react";

import type { AppStatus, SyncResult } from "../../../shared/types/index.ts";
import { useContextSafe } from "../../../entities/user/index.ts";

/**
 * Synchronization state: how fresh the local cache is and how to refresh it.
 * Kept separate from the data itself so a sync spinner or an error banner does
 * not re-render every list on the screen.
 */
export type SyncState = {
  status: AppStatus | null;
  loading: boolean;
  syncing: boolean;
  /**
   * True when the server still reports a sync in flight but it has been
   * running for longer than the server's `sync_stuck_after_seconds` without
   * finishing. A real Classroom import of a few hundred courses takes a
   * couple of minutes, so the threshold is deliberately generous — this is the
   * "something is wrong, offer the user a restart" signal, not a timeout
   * that cancels anything (ADR-0032).
   */
  syncStuck: boolean;
  error: string | null;
  syncNow: () => Promise<SyncResult | null>;
  /**
   * Abandon the stuck sync and start a new one (ADR-0032). Only offered while
   * `syncStuck` is true, and only ever honoured by the server for a claim that
   * really is past the stuck threshold — a click during a healthy sync answers
   * 409 and changes nothing.
   */
  syncRestart: () => Promise<SyncResult | null>;
  refresh: () => Promise<void>;
};

export const SyncContext = createContext<SyncState | null>(null);

export function useSync(): SyncState {
  return useContextSafe(SyncContext, "useSync");
}