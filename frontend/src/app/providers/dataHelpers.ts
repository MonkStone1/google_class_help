/**
 * The pure rules behind the sync state — no React, no transport.
 *
 * They were private functions inside a 453-line `DataProvider`, which made the
 * two questions that actually have answers — "is this request a session
 * problem?" and "how long has this sync been active?" — impossible to test
 * without mounting the whole provider stack and a fake API behind it.
 */

import type { ApiError } from "../../shared/api/index.ts";
import type { AppStatus } from "../../shared/types/index.ts";

/**
 * Fallback stuck threshold, seconds — used only until the server has answered
 * at least once. The authoritative value is `sync_stuck_after_seconds` from
 * `GET /api/status` (ADR-0032): the dashboard must not decide "stuck" on one
 * number while `POST /api/sync?restart=true` enforces another, or it would
 * either offer a restart the server refuses or hide one it would accept.
 */
export const STUCK_SYNC_SECONDS = 5 * 60;

/**
 * Start of the CLAIMED run in epoch milliseconds, or 0 when the server row
 * carries no stamp.
 *
 * `last_sync_started_at` is naive UTC (ADR-0004), so `Z` is appended; a value
 * that already carries an offset is parsed as-is. It is only meaningful while
 * ``sync_status === "running"`` — until the worker claims a job, this field
 * still describes the PREVIOUS run (see `stuckAgeMs`).
 */
export function startedAtMs(status: AppStatus): number {
  const raw = status.last_sync_started_at;
  if (!raw) {
    return 0;
  }
  const parsed = Date.parse(raw.endsWith("Z") ? raw : `${raw}Z`);
  return Number.isNaN(parsed) ? 0 : parsed;
}

/** A 401 is a session problem, not a transport problem (§26). */
export function isUnauthorized(reason: unknown): boolean {
  return reason instanceof Error && (reason as ApiError).status === 401;
}

/** Human-readable reason of the first failed request, or null when all passed. */
export function describeFailure(
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

/**
 * How long the current run has been active, and since when.
 *
 * Which clock the age is measured on is the subtle part (ADR-0032):
 *
 * - a CLAIMED run (``sync_status === "running"``) carries its own
 *   ``last_sync_started_at``, and that server stamp is authoritative;
 * - a job still QUEUED (``sync_status === "pending"`` with ``sync_requested``)
 *   does not — the field still describes the previous run, routinely hours
 *   old, so aging the new job against it reported "stuck" immediately after the
 *   user pressed Sync. Such a job is aged from the first moment this browser saw
 *   it instead (`queuedSince`), which also covers a page opened mid-queue;
 * - a row with no usable stamp at all falls into the same local baseline
 *   rather than reporting an age of "since 1970".
 */
export function stuckAgeMs(status: AppStatus, queuedSince: number): number {
  const claimedAt =
    status.sync_status === "running" ? startedAtMs(status) : 0;
  const since = claimedAt > 0 ? claimedAt : queuedSince;
  // No sighting and no claim: there is nothing to age yet.
  if (since === 0) return 0;
  return Math.max(0, Date.now() - since);
}

/** Milliseconds until the run crosses the server's stuck threshold. */
export function stuckRemainingMs(status: AppStatus, queuedSince: number): number {
  const threshold = status.sync_stuck_after_seconds || STUCK_SYNC_SECONDS;
  return Math.max(0, threshold * 1000 - stuckAgeMs(status, queuedSince));
}