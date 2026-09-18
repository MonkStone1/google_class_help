"""Background synchronization schedule for the Classroom cache.

- one sync right after application startup;
- then a sync every SYNC_INTERVAL_MINUTES (default 10, env
  GC_DASHBOARD_SYNC_INTERVAL_MINUTES, 0 disables the schedule);
- a successful sign-in also triggers a one-off sync so the dashboard does
  not sit empty until the next tick.

Every run goes through ``sync.sync_now()``, which is mutex-protected: a
background run never duplicates a manual sync or another background run.
Failures are recorded in ``sync_state.last_sync_error`` by the sync itself;
while the user is not signed in, ``sync_now()`` returns early and the next
tick simply retries.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import sync
from config import SYNC_INTERVAL_MINUTES

logger = logging.getLogger(__name__)

_stop = threading.Event()
_start_lock = threading.Lock()
_scheduler: threading.Thread | None = None
# Serial one-off executor: concurrent syncs are impossible by design
# (sync_now mutex), so one worker is enough and triggers cannot stack.
_runs = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bg-sync")


def _run(reason: str) -> dict:
    result = sync.sync_now()
    if not result.get("ok") and "already running" in str(result.get("error", "")):
        # A manual sync got there first: not a failure, don't alarm the log
        # (review §3.5). The next tick will simply try again.
        logger.info(
            "%s sync skipped: another synchronization is already running.", reason
        )
        return result
    status = "ok" if result.get("ok") else f"failed: {result.get('error')}"
    logger.info("%s sync %s", reason, status)
    return result


def _scheduler_loop() -> None:
    while not _stop.is_set():
        _runs.submit(_run, "scheduled")
        if _stop.wait(SYNC_INTERVAL_MINUTES * 60):
            break


def start() -> None:
    """Start the schedule: sync now, then repeat every interval."""
    global _scheduler
    if SYNC_INTERVAL_MINUTES <= 0:
        return
    with _start_lock:
        if _scheduler is not None and _scheduler.is_alive():
            return
        _stop.clear()
        _scheduler = threading.Thread(
            target=_scheduler_loop, name="sync-scheduler", daemon=True
        )
        _scheduler.start()


def stop() -> None:
    """Signal the scheduler loop to exit (used by tests)."""
    _stop.set()


def request_soon() -> None:
    """Kick a one-off sync in the background (e.g. right after sign-in)."""
    _runs.submit(_run, "on-demand")
