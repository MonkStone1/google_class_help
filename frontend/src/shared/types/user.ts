import type { Wire } from "./wire.ts";

/** Backend status of the whole cache, as the dashboard polls it (ADR-0032). */
export type AppStatus = Wire<"SyncStatus">;

/** Who is signed in, and what the backend derived about them (§26). */
export type AuthStatus = Wire<"AuthStatus">;

/** The outcome of a queued or running synchronization run. */
export type SyncResult = Wire<"SyncResult">;