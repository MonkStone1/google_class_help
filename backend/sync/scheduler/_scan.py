"""Per-user background synchronization (migration stage 5, §18/§19/§63/§64).

``background_sync.py`` remains the desktop schedule (one process, one
account — ADR-0015/ADR-0019). The hosted service cannot reuse it: there the
accounts are independent, and a single process-global loop either runs one
user per pass (starvation) or all of them at once (a startup thundering
herd). The hosted shape is a scan/queue/execute pipeline instead:

    scan every SYNC_SCAN_INTERVAL_SECONDS
        ↓
    select users that are due — active, google provider, a stored grant,
    not paused for re-authorization, and their next sync time has passed
        ↓
    submit each to a bounded pool (SYNC_MAX_CONCURRENT_USERS)
        ↓
    sync_service.sync_user_id(user_id) — per-user lock + DB claim, so a
    user is never synced twice even by two worker containers
        ↓
    the outcome lands in that user's ``sync_status`` row

Correctness boundaries:

- **No global lock** (§18): concurrency is per user. Two accounts sync in
  parallel; one account never syncs twice at once. One broken grant or a
  403 for user A cannot stop user B — each job has its own session, its own
  credentials and its own try/except.
- **Only usable accounts are candidates** (§63): a user with no stored
  grant is not selected at all, and a user whose grant failed to refresh is
  marked ``needs_reauth`` by the sync itself and skipped until the next
  sign-in sets ``sync_requested``.
- **No startup storm** (§64): the first run of each user is offset inside a
  deterministic per-user window derived from the user id, and each scan
  submits at most as many users as there are free worker slots. A
  deployment with thousands of existing accounts therefore drains as a
  queue instead of hitting Google with thousands of simultaneous syncs.
- **Retry backoff** (§63): consecutive failures multiply the wait between
  attempts (up to 8×) so a temporarily failing account cannot hammer the
  API.

The scheduler is safe to run in several containers at once: duplicate jobs
are prevented by ``sync_store.claim_sync``, a conditional UPDATE in the
database, not by process-local bookkeeping.
"""

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import maintenance
from core import metrics
from core.config import (
    RETENTION_SWEEP_SECONDS,
    SYNC_INTERVAL_MINUTES,
    SYNC_MAX_CONCURRENT_USERS,
    SYNC_SCAN_INTERVAL_SECONDS,
    SYNC_STARTUP_STAGGER_SECONDS,
)
from db.session import SessionLocal
from sync import store

logger = logging.getLogger(__name__)

# A user with a pending sync request is due regardless of the interval;
# ``None`` from :func:`next_sync_at` expresses that without inventing a
# sentinel timestamp.

# Consecutive failures stretch the interval up to this factor (2^3), which
# bounds retry traffic per broken account without ever giving up on it.

class SyncScheduler:
    """Live per-user scheduler with a bounded, non-overlapping queue (§19)."""

    def __init__(
        self,
        *,
        interval_seconds: int | None = None,
        max_concurrent: int | None = None,
        scan_interval_seconds: int | None = None,
        startup_stagger_seconds: int | None = None,
        maintenance_interval_seconds: int | None = None,
    ) -> None:
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else SYNC_INTERVAL_MINUTES * 60
        )
        self.max_concurrent = max_concurrent or SYNC_MAX_CONCURRENT_USERS
        self.scan_interval_seconds = (
            scan_interval_seconds
            if scan_interval_seconds is not None
            else SYNC_SCAN_INTERVAL_SECONDS
        )
        maintenance_interval_seconds = (
            maintenance_interval_seconds
            if maintenance_interval_seconds is not None
            else RETENTION_SWEEP_SECONDS
        )
        self.startup_stagger_seconds = (
            startup_stagger_seconds
            if startup_stagger_seconds is not None
            else SYNC_STARTUP_STAGGER_SECONDS
        )
        self._pool = ThreadPoolExecutor(
            max_workers=self.max_concurrent, thread_name_prefix="user-sync"
        )
        # Reentrant on purpose: a job whose future is ALREADY finished when
        # its done-callback is registered runs the callback inline, in this
        # same thread — and that callback discards from ``_in_flight``
        # through the same guard that ``scan_once`` is still holding. With a
        # plain Lock that inline re-entry deadlocks the scheduler forever.
        self._guard = threading.RLock()
        self._in_flight: set[int] = set()
        self._stop = threading.Event()
        self._loop: threading.Thread | None = None
        # Stage 9 (§44/§60): housekeeping cadence — the retention sweep and
        # the metrics summary run at most this often, from the scan loop.
        self.maintenance_interval_seconds = maintenance_interval_seconds
        self._last_maintenance = 0.0

    # ------------------------------------------------------------- runtime

    @property
    def in_flight_count(self) -> int:
        """How many users this scheduler is syncing right now."""
        with self._guard:
            return len(self._in_flight)

    def run_maintenance(self) -> dict[str, int]:
        """Retention sweep + metrics summary (§44/§60); never fatal."""
        removed: dict[str, int] = {}
        try:
            with SessionLocal() as db:
                removed = maintenance.purge_expired(db)
        except Exception:
            logger.exception("Retention sweep failed; retrying next cycle")
        if removed.get("sessions") or removed.get("login_states"):
            logger.info(
                "Retention sweep removed sessions=%s login_states=%s.",
                removed.get("sessions", 0),
                removed.get("login_states", 0),
            )
        metrics.log_snapshot("worker")
        self._last_maintenance = time.monotonic()
        return removed

    def scan_once(self, now: datetime | None = None) -> list[int]:
        """Submit every due user this pass, up to the free worker slots.

        Returns the ids submitted. Holding the guard for the whole
        selection+submission makes two concurrent ``scan_once`` calls (a
        manual tick and the loop) unable to queue the same account twice.
        """
        with self._guard:
            free = self.max_concurrent - len(self._in_flight)
            if free <= 0:
                return []
            with SessionLocal() as db:
                due_ids = select_due_users(
                    db,
                    now or _now(),
                    interval_seconds=self.interval_seconds,
                    startup_stagger_seconds=self.startup_stagger_seconds,
                    limit=free,
                    exclude=set(self._in_flight),
                )
            submitted: list[int] = []
            for user_id in due_ids:
                self._in_flight.add(user_id)
                # Called as ``due.run_user`` rather than as a bare name: the
                # scheduler tests replace that function, and a name bound at
                # import time would keep calling the original (ADR-0039).
                future = self._pool.submit(due.run_user, user_id)
                future.add_done_callback(lambda _future, uid=user_id: self._forget(uid))
                submitted.append(user_id)
            return submitted

    def _forget(self, user_id: int) -> None:
        with self._guard:
            self._in_flight.discard(user_id)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until no job submitted by this scheduler is in flight.

        Returns True when the pool drained, False on timeout. Used by the
        SIGTERM path so a graceful stop can wait for the sync it is finishing.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._guard:
                if not self._in_flight:
                    return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def start(self) -> None:
        """Start the scan loop (idempotent)."""
        if self._loop is not None and self._loop.is_alive():
            return
        self._stop.clear()
        self._loop = threading.Thread(
            target=self._loop_body, name="user-sync-scheduler", daemon=True
        )
        self._loop.start()

    def _loop_body(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception:
                logger.exception("Sync scan failed; retrying on the next tick")
            # Stage 9 (§44/§60): retention sweep + metrics summary, at most
            # once per maintenance interval (0 disables it in tests).
            if (
                self.maintenance_interval_seconds > 0
                and time.monotonic() - self._last_maintenance
                >= self.maintenance_interval_seconds
            ):
                self.run_maintenance()
            # Scans carry a little randomness so several worker containers
            # do not tick in lockstep (their DB claim already prevents
            # duplicate jobs, this only smooths the database load).
            jitter = random.uniform(0, max(1.0, self.scan_interval_seconds * 0.1))
            if self._stop.wait(self.scan_interval_seconds + jitter):
                break

    def stop(self) -> None:
        """Stop scheduling new scans and release the worker pool."""
        self._stop.set()
        loop = self._loop
        if loop is not None:
            loop.join(timeout=5)
            self._loop = None
        self._pool.shutdown(wait=False, cancel_futures=False)

    def release_in_flight_claims(self) -> int:
        """Hand every in-flight user's claim back to the schedule (§19).

        A hard kill (Docker's default 10s stop grace period expires long
        before a long Classroom fan-out finishes) used to leave the account
        in ``running`` with no process behind it, and the row then blocked
        every later attempt for the whole SYNC_CLAIM_STALE_SECONDS window —
        a spinner the user could not clear. Called on SIGTERM after the jobs
        are given a chance to finish, this is the difference between "the
        next scan retries" and "the account is parked for an hour".

        The jobs themselves release their own claim when they finish; this
        only matters for the ones still running when we are being told to go
        away. Never raises: a shutdown path must not fail on the database.
        """
        with self._guard:
            in_flight = sorted(self._in_flight)
        released = 0
        for user_id in in_flight:
            try:
                with SessionLocal() as db:
                    if store.release_claim(db, user_id, _now()):
                        released += 1
            except Exception:  # best effort during shutdown
                logger.exception("Could not release the sync claim of user %s", user_id)
        if released:
            logger.info("Released %s in-flight sync claim(s) on shutdown.", released)
        return released

    def shutdown(self) -> None:
        """Alias for :meth:`stop` (used by one-shot callers)."""
        self.stop()


# --------------------------------------------------------------- singleton

_scheduler: SyncScheduler | None = None
_singleton_lock = threading.Lock()


def start() -> SyncScheduler:
    """Start the process-wide scheduler (used by the embedded mode)."""
    global _scheduler
    with _singleton_lock:
        if _scheduler is None:
            _scheduler = SyncScheduler()
        _scheduler.start()
        return _scheduler


def stop() -> None:
    """Stop the process-wide scheduler, if it was started."""
    global _scheduler
    with _singleton_lock:
        scheduler, _scheduler = _scheduler, None
    if scheduler is not None:
        scheduler.stop()

# The due-time arithmetic lives in ``sync/scheduler/due.py`` (ADR-0039). These
# are the names the class below calls; they are bound, not re-implemented, so a
# test that patches ``due.select_due_users`` changes what the scan really does.
from sync.scheduler import due
from sync.scheduler.due import (
    select_due_users,
)

_now = due._now
