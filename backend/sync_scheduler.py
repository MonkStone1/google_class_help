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

import hashlib
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

import maintenance
import metrics
import sync_service
import sync_store
from config import (
    RETENTION_SWEEP_SECONDS,
    SYNC_INTERVAL_MINUTES,
    SYNC_MAX_CONCURRENT_USERS,
    SYNC_SCAN_INTERVAL_SECONDS,
    SYNC_STARTUP_STAGGER_SECONDS,
)
from database import SessionLocal
from models import SyncStatus
from models_auth import OAuthToken, User
from sync_store import SYNC_NEEDS_REAUTH

logger = logging.getLogger(__name__)

# A user with a pending sync request is due regardless of the interval;
# ``None`` from :func:`next_sync_at` expresses that without inventing a
# sentinel timestamp.

# Consecutive failures stretch the interval up to this factor (2^3), which
# bounds retry traffic per broken account without ever giving up on it.
_BACKOFF_MAX_POWER = 3


def _now() -> datetime:
    """Naive UTC — the timestamp convention of the user-scoped tables."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stagger_offset_seconds(user_id: int, span_seconds: int) -> int:
    """Deterministic per-user offset inside ``span_seconds`` (§64).

    Derived from the user id with SHA-256 rather than ``hash()``: the value
    must be identical in every process and across restarts (Python's string
    hash is salted per process), so two containers always agree on the same
    user's slot. Yields the same offset for the same user every time, which
    spreads load without making the schedule unpredictable.
    """
    if span_seconds <= 0:
        return 0
    digest = hashlib.sha256(f"gch-sync-{user_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % span_seconds


def retry_delay_seconds(interval_seconds: int, failures: int) -> int:
    """Wait before the next attempt of a user with ``failures`` failures."""
    power = min(max(failures, 0), _BACKOFF_MAX_POWER)
    return interval_seconds * (2**power)


def next_sync_at(
    user: User,
    status: SyncStatus | None,
    *,
    interval_seconds: int,
    startup_stagger_seconds: int,
) -> datetime | None:
    """When this user's next sync becomes due; ``None`` means "right now".

    - an explicit request (fresh sign-in) is due immediately;
    - a user that never synced enters the schedule inside the startup
      stagger window measured from account creation (§64);
    - everyone else waits the (backoff-multiplied) interval plus their own
      deterministic offset.
    """
    if status is not None and status.sync_requested:
        return None
    last = None
    failures = 0
    if status is not None:
        last = status.last_finished_at or status.last_started_at
        failures = status.consecutive_failures or 0
    if last is None:
        span = min(interval_seconds, startup_stagger_seconds)
        return user.created_at + timedelta(
            seconds=stagger_offset_seconds(user.id, span)
        )
    return last + timedelta(
        seconds=retry_delay_seconds(interval_seconds, failures)
        + stagger_offset_seconds(user.id, interval_seconds)
    )


def select_due_users(
    session: Session,
    now: datetime,
    *,
    interval_seconds: int,
    startup_stagger_seconds: int,
    limit: int | None = None,
    exclude: set[int] | frozenset[int] = frozenset(),
) -> list[int]:
    """Ids of users that are due for a sync, oldest due time first.

    Candidates are active ``google`` users that hold a stored OAuth grant
    and are not paused for re-authorization (§63). The inner join on
    ``oauth_tokens`` is what keeps a user who never signed in out of the
    schedule: there is nothing to sync with.

    ``limit`` gives the caller its bounded batch; ``exclude`` lets the
    in-process scheduler skip accounts whose job is still running in this
    very process (other processes are handled by the DB claim).
    """
    stmt = (
        select(User, SyncStatus)
        .outerjoin(SyncStatus, SyncStatus.user_id == User.id)
        .join(OAuthToken, OAuthToken.user_id == User.id)
        .where(User.is_active.is_(True), User.provider == "google")
        .where(or_(SyncStatus.status.is_(None), SyncStatus.status != SYNC_NEEDS_REAUTH))
    )
    rows = session.execute(stmt).all()
    candidates: list[tuple[datetime, int]] = []
    requested: list[int] = []
    for user, status in rows:
        if user.id in exclude:
            continue
        due_at = next_sync_at(
            user,
            status,
            interval_seconds=interval_seconds,
            startup_stagger_seconds=startup_stagger_seconds,
        )
        if due_at is None:
            requested.append(user.id)
        elif due_at <= now:
            candidates.append((due_at, user.id))
    # Explicit requests first (a user who just signed in), then the oldest
    # due time; ties broken by id for a stable order.
    candidates.sort()
    ids = requested + [user_id for _, user_id in candidates]
    return ids if limit is None else ids[:limit]


def run_user(user_id: int) -> dict:
    """Sync one user, isolating every failure to that user (§18).

    Returns the sync result plus the user id. Nothing raised by the job
    escapes: a crash in user A's job must not abort the scan that is
    starting user B's.
    """
    try:
        result = sync_service.sync_user_id(user_id)
    except Exception:
        logger.exception("Scheduled sync for user id=%s crashed", user_id)
        metrics.record(metrics.SYNC_JOB_CRASHED)
        return {"user_id": user_id, "ok": False, "error": "Internal sync error."}
    error = str(result.get("error") or "")
    if result.get("ok"):
        logger.info("Scheduled sync for user id=%s finished.", user_id)
    elif "already running" in error:
        logger.info("Scheduled sync for user id=%s skipped: already running.", user_id)
    else:
        logger.warning("Scheduled sync for user id=%s failed: %s", user_id, error)
    return {"user_id": user_id, **result}


def sync_users(user_ids: list[int], *, max_concurrent: int | None = None) -> list[dict]:
    """Run the given users' syncs through a bounded pool and wait for them.

    Blocking batch used by the one-shot worker invocation (``--once``) and
    by tests. The live scheduler uses :class:`SyncScheduler` instead, which
    keeps one long-lived pool.
    """
    if not user_ids:
        return []
    workers = max_concurrent or SYNC_MAX_CONCURRENT_USERS
    with ThreadPoolExecutor(
        max_workers=min(workers, len(user_ids)), thread_name_prefix="user-sync"
    ) as pool:
        futures = [pool.submit(run_user, user_id) for user_id in user_ids]
        return [future.result() for future in futures]


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
                due = select_due_users(
                    db,
                    now or _now(),
                    interval_seconds=self.interval_seconds,
                    startup_stagger_seconds=self.startup_stagger_seconds,
                    limit=free,
                    exclude=set(self._in_flight),
                )
            submitted: list[int] = []
            for user_id in due:
                self._in_flight.add(user_id)
                future = self._pool.submit(run_user, user_id)
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
                    if sync_store.release_claim(db, user_id, _now()):
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
