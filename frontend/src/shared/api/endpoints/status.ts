/**
 * Backend status and the destructive cache drop.
 *
 * `GET /status` is the app's clock: it carries `syncing`, the stuck threshold
 * and the last sync stamps (ADR-0032), which is why the sync state lives next
 * to the call rather than in the endpoint.
 */

import { request } from "../client.ts";
import type { AppStatus } from "../../types/index.ts";

export const status = {
    getStatus: () => request<AppStatus>("/status"),
    clearCache: () =>
        request<{ ok: boolean }>("/cache?confirm=true", { method: "DELETE" }),
};