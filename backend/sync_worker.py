"""Dedicated background-sync worker process (migration stage 5, §19).

The hosted deployment runs background synchronization in its own container
instead of inside the web process (Option A of the migration prompt):

    web container      — requests, OAuth, sessions, PostgreSQL reads
    worker container   — this process: per-user sync jobs only
    postgres container — the datastore
    caddy container    — TLS + reverse proxy

Why a separate process (§19): a scheduler living in the web process would
run once per Uvicorn worker/replica, and its in-memory queues would diverge.
Running it here keeps exactly one owner of the schedule; and even when the
web process opts into the embedded scheduler (``GC_DASHBOARD_EMBEDDED_
SCHEDULER=1``, single-replica convenience), duplicate jobs remain impossible
because every sync claims its user with a conditional UPDATE in the database
(``sync_store.claim_sync``).

Usage:

    python sync_worker.py            # run until SIGINT/SIGTERM (container)
    python sync_worker.py --once     # one scan, wait for its jobs, exit
                                     # (cron/scheduled-task style deployment)

The worker needs the same environment as the web process (DATABASE_URL and
the OAuth client/encryption settings) — it reads the users' stored tokens,
never Google credentials of its own. It never binds a port and holds no
secrets of its own.
"""

import argparse
import logging
import signal
import sys
import threading
from datetime import datetime, timezone

from config import (
    HOSTED_MODE,
    SYNC_INTERVAL_MINUTES,
    SYNC_MAX_CONCURRENT_USERS,
    SYNC_SCAN_INTERVAL_SECONDS,
    SYNC_STARTUP_STAGGER_SECONDS,
)
from database import SessionLocal, init_db
from sync_scheduler import SyncScheduler, select_due_users, sync_users

logger = logging.getLogger("sync_worker")


def _now() -> datetime:
    """Naive UTC — the timestamp convention of the user-scoped tables."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_once() -> list[dict]:
    """One synchronous scan: sync every due user now and wait for the batch."""
    with SessionLocal() as db:
        due = select_due_users(
            db,
            _now(),
            interval_seconds=SYNC_INTERVAL_MINUTES * 60,
            startup_stagger_seconds=SYNC_STARTUP_STAGGER_SECONDS,
            limit=SYNC_MAX_CONCURRENT_USERS,
        )
    if not due:
        logger.info("No users are due for synchronization.")
        return []
    logger.info("Synchronizing %s due user(s): %s", len(due), due)
    return sync_users(due, max_concurrent=SYNC_MAX_CONCURRENT_USERS)


def run_forever() -> int:
    """Run the scheduler loop until SIGINT/SIGTERM is received."""
    scheduler = SyncScheduler()
    stop_event = threading.Event()

    def _handle_signal(signum, _frame) -> None:
        logger.info("Received signal %s; shutting down after the current scan.", signum)
        stop_event.set()

    # SIGTERM is what Docker sends on `docker stop`; without a handler the
    # process is killed mid-sync and the user's row stays "running" until the
    # claim's stale window expires.
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    scheduler.start()
    logger.info(
        "Sync worker started: %ss per-user interval, up to %s user(s) at once, "
        "scan every %ss.",
        SYNC_INTERVAL_MINUTES * 60,
        SYNC_MAX_CONCURRENT_USERS,
        SYNC_SCAN_INTERVAL_SECONDS,
    )
    try:
        stop_event.wait()
    finally:
        scheduler.stop()
        logger.info("Sync worker stopped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-user background synchronization worker (hosting migration stage 5)."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one scan synchronously and exit (cron-style deployments)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level for the worker (default: INFO)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not HOSTED_MODE:
        # The desktop build has background_sync.py and a single account;
        # running this worker there would be a no-op (no google users) at
        # best and a second schedule at worst.
        logger.warning(
            "GC_DASHBOARD_HOSTED is not set: this worker is meant for the "
            "hosted service (the desktop build uses background_sync.py)."
        )
    init_db()
    if args.once:
        results = run_once()
        failed = [r for r in results if not r.get("ok")]
        logger.info(
            "One-shot scan finished: %s ok, %s failed.",
            len(results) - len(failed),
            len(failed),
        )
        return 0
    return run_forever()


if __name__ == "__main__":
    sys.exit(main())
