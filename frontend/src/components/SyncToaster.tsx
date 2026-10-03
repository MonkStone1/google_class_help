import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { useSync } from "../features/sync/index.ts";
import { toLocalDate } from "../shared/lib/dates.ts";
import { useI18n } from "../shared/i18n/index.ts";

/**
 * Announce a finished synchronization (ADR-0030). Renders nothing.
 *
 * The trigger is the server's `last_sync_finished_at` stamp, not the click on
 * "Sync". Two reasons:
 * - a scheduled background run finishes without any user action, and the stamp
 *   is the only thing that says so while the browser is open;
 * - a refused `POST /api/sync` (429 cooldown, 409 already running) leaves that
 *   stamp untouched, so a toast can never claim a success that did not happen.
 *
 * The first status answer is recorded as the baseline rather than as an event,
 * so opening the dashboard during a finished sync stays quiet.
 */
export function SyncToaster() {
  const { status } = useSync();
  const { t } = useI18n();
  // `undefined` means "no status seen yet" and is distinct from a seen `null`:
  // without the three states the first stamp of a never-synced account would
  // be indistinguishable from a finished run.
  const announced = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    // Nothing is known yet while `status` is still null (first render, or the
    // cache drop after a 401). Recording a baseline here would make the very
    // first answer look like a *change* from "no sync ever finished" and greet
    // every page load with a toast.
    if (status === null) {
      return;
    }
    const finishedAt = status.last_sync_finished_at ?? null;
    if (announced.current === undefined) {
      announced.current = finishedAt;
      return;
    }
    if (finishedAt === null || finishedAt === announced.current) {
      return;
    }
    announced.current = finishedAt;

    if (status.sync_status === "ok") {
      const at = toLocalDate(status.last_sync ?? finishedAt);
      toast.success(t("toast.syncCompleted"), {
        description: at
          ? t("toast.syncCompletedAt", { time: at.toLocaleString() })
          : undefined,
      });
      return;
    }
    // needs_reauth is not a failure: the schedule is paused until this browser
    // signs in again (§63), so the toast asks for that instead of alarming.
    if (status.sync_status === "needs_reauth") {
      toast.warning(t("toast.syncNeedsReauth"), {
        description: status.last_sync_error ?? undefined,
      });
      return;
    }
    toast.error(t("toast.syncFailed"), {
      description: status.last_sync_error ?? undefined,
    });
  }, [status, t]);

  return null;
}
