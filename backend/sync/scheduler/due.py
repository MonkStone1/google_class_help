"""When is each user due, and how is the spread decided (ADR-0039 split).

These are pure decisions about TIME: the stagger that keeps every account from
waking at the same instant, the backoff after a failure, and the query that
answers "who is due". Split out of the scheduler class so the arithmetic can be
read — and tested — without a thread pool in the picture.

Two rules that are easy to get wrong and are therefore worth stating:

- ``next_sync_at`` falls back to ``last_started_at`` when a run never finished.
  Without that, a sync killed mid-flight looks infinitely old and is offered to
  a second worker the moment its claim goes stale.
- The stagger is derived from the user id, not from a random number: a process
  restart must not re-shuffle every account, or the whole fleet re-synchronizes
  at once the moment the worker restarts.
"""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core import metrics
from core.config import SYNC_MAX_CONCURRENT_USERS
from db.models.accounts import OAuthToken, User
from db.models.classroom import SyncStatus
from sync import service
from sync.store.status import SYNC_NEEDS_REAUTH

logger = logging.getLogger(__name__)


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


# The backoff doubles per consecutive failure, capped here: past the cap a
# repeatedly failing account would otherwise be retried hours apart, which
# looks like a working retry policy but is really an outage.
_BACKOFF_MAX_POWER = 3


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
        result = service.sync_user_id(user_id)
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
