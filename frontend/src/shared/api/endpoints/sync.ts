/**
 * Queueing a synchronization run.
 *
 * `restart` (ADR-0032) asks the server to abandon a sync it has itself declared
 * stuck and start a new one; without it the call keeps its plain "queue a sync"
 * meaning and answers 409 while a sync is in flight. The flag is a query
 * parameter, so the restart shares the endpoint's rate-limit bucket instead of
 * opening a new, separately-guarded surface.
 */

import { request } from "../client.ts";
import type { SyncResult } from "../../types/index.ts";

export const sync = {
    sync: (restart = false) =>
        request<SyncResult>(`/sync${restart ? "?restart=true" : ""}`, {
            method: "POST",
        }),
};