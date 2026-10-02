"""Sync-status transitions: claim, progress, release (ADR-0039 split).

One structured row per user holds when their cache was last filled, whether it
worked, and whether they may be scheduled again. Every transition lives here,
so there is exactly one place that can write that row — the scheduler and the
worker both go through these functions instead of updating the model directly.

The claim is a conditional UPDATE, not a SELECT-then-write: two schedulers
racing for the same user produce exactly one winner because the WHERE clause
re-checks the previous state inside the database's own lock.
"""

import logging
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.classroom import SyncStatus

logger = logging.getLogger(__name__)

# ------------------------------------------------------------- sync status
#
# One structured row per user (migration stage 5, §18) replaces the former
# key/value sync_state table. The scheduler reads it to decide who is due;
# the sync itself writes every transition through the functions below, so
# there is exactly one source of truth for "when did this user last sync,
# did it work, and may it be scheduled again".

SYNC_PENDING = "pending"
SYNC_RUNNING = "running"
SYNC_OK = "ok"
SYNC_ERROR = "error"
SYNC_NEEDS_REAUTH = "needs_reauth"

# Safety net for the VARCHAR(500) of sync_status.last_error: the message is
# ours, but truncating here keeps a future longer sentence from aborting an
# INSERT on PostgreSQL.
_MAX_ERROR_LENGTH = 500


def sync_status(db: Session, user_id: int) -> SyncStatus | None:
    """The user's sync-status row, or None if the user never touched sync."""
    return db.get(SyncStatus, user_id)


def _status_row(db: Session, user_id: int) -> SyncStatus:
    """The user's sync-status row, created on first use.

    Creation is idempotent under concurrency: if another process inserted
    the same PK between our SELECT and flush, the unique violation is
    rolled back and the existing row is read instead. No other pending
    change exists in this session at that point (the row is created before
    the sync starts its work).
    """
    row = db.get(SyncStatus, user_id)
    if row is not None:
        return row
    db.add(SyncStatus(user_id=user_id, status=SYNC_PENDING))
    try:
        db.flush()
    except IntegrityError:  # pragma: no cover - concurrent first touch
        db.rollback()
        row = db.get(SyncStatus, user_id)
        if row is None:
            raise
        return row
    row = db.get(SyncStatus, user_id)
    if row is None:  # pragma: no cover - only if the row vanished again
        raise RuntimeError(f"sync_status row for user {user_id} disappeared")
    return row


def claim_sync(db: Session, user_id: int, now: datetime, *, stale_after: int) -> bool:
    """Atomically claim the user's sync slot; False when one is in flight.

    The conditional UPDATE is what makes the scheduler safe across worker
    containers (migration stage 5, §19): a scan in container B cannot start
    a job for a user a scan in container A already claimed. A ``running``
    row whose ``last_started_at`` is older than ``stale_after`` seconds is
    assumed to belong to a crashed worker and may be taken over, so a hard
    kill cannot park a user forever.

    That takeover is the ONE event that can put two processes in the same
    user's write phase: the older run is still alive but has been going longer
    than the window (a teacher account whose write phase outlasts
    ``stale_after``), and the scheduler picks it up again because
    ``next_sync_at`` reads the PREVIOUS run's ``last_finished_at``. The losing
    run is stopped by the fence (ADR-0032) and its writes are made harmless by
    the conditional write (ADR-0033), but the takeover is rare and load-bearing
    enough to deserve a log line: it is the sole origin of a duplicate-key
    symptom, and without it the next occurrence is a forensic exercise.
    """
    row = _status_row(db, user_id)
    cutoff = now - timedelta(seconds=stale_after)
    # Snapshot the previous state as PLAIN values: the UPDATE below
    # synchronizes the session and rewrites this very object's attributes, so
    # reading ``row`` afterwards would compare ``now`` against ``now`` and the
    # takeover would never be recognised.
    previous_status = row.status
    previous_started_at = row.last_started_at
    result = cast(
        CursorResult,
        db.execute(
            update(SyncStatus)
            .where(SyncStatus.user_id == user_id)
            .where(
                or_(
                    SyncStatus.status != SYNC_RUNNING,
                    SyncStatus.last_started_at.is_(None),
                    SyncStatus.last_started_at < cutoff,
                )
            )
            .values(status=SYNC_RUNNING, last_started_at=now, sync_requested=False)
        ),
    )
    db.commit()
    if (
        result.rowcount
        and previous_status == SYNC_RUNNING
        and previous_started_at is not None
        and previous_started_at < cutoff
    ):
        logger.warning(
            "Took over a stale sync claim for user=%s: the previous run started "
            "%d s ago, past the %d s window. Two write phases of this account "
            "may now overlap; the older one is fenced and writes nothing.",
            user_id,
            int((now - previous_started_at).total_seconds()),
            stale_after,
        )
    return bool(result.rowcount)


def claim_is_own(db: Session, user_id: int, started_at: datetime) -> bool:
    """Whether the run that claimed at ``started_at`` still holds the claim.

    The fence of ADR-0032. ``claim_sync`` deliberately lets a stale ``running``
    row be taken over, so from that moment TWO processes can believe they own
    the same user's sync. The older one must notice before it writes anything:
    the cache purge and the terminal ``sync_status`` transition belong to the
    run that actually holds the claim now, not to a zombie that woke up late.

    The guard is the claim timestamp itself rather than a separate token
    column — the same conditional-guard idea as :func:`release_claim`, and it
    needs no schema change.
    """
    row = sync_status(db, user_id)
    return (
        row is not None
        and row.status == SYNC_RUNNING
        and row.last_started_at == started_at
    )


def abandon_claim(
    db: Session, user_id: int, now: datetime, *, older_than: int
) -> bool:
    """Give up one user's stale claim so a new sync may start (ADR-0032).

    The user's own "the sync is stuck, restart it" action. The conditional
    guard mirrors :func:`claim_sync` in reverse: only a ``running`` row that
    started more than ``older_than`` seconds ago is released, so a restart can
    never interrupt a sync that is still legitimately running — and two
    concurrent requests cannot release the same claim twice.

    ``last_finished_at`` is deliberately NOT touched. Moving it would look to
    ``SyncToaster`` like a finished run and, with ``status == "pending"``, be
    announced as a failed sync — a failure that never happened (ADR-0030).
    ``last_success_at`` likewise stays: the cache it describes is still on the
    caller's screen, and its age must remain visible (ADR-0027 §61).

    Returns True when a claim was actually released.
    """
    cutoff = now - timedelta(seconds=older_than)
    result = cast(
        CursorResult,
        db.execute(
            update(SyncStatus)
            .where(SyncStatus.user_id == user_id)
            .where(SyncStatus.status == SYNC_RUNNING)
            .where(SyncStatus.last_started_at.is_not(None))
            .where(SyncStatus.last_started_at <= cutoff)
            .values(status=SYNC_PENDING)
        ),
    )
    db.commit()
    return bool(result.rowcount)


def request_sync(db: Session, user_id: int) -> None:
    """Queue an immediate sync for one user, lifting ``needs_reauth`` (§63).

    Called after a successful sign-in: the user just granted Google access
    again, so a paused account becomes schedulable and should not wait out
    the regular interval. The worker picks the flag up on its next scan and
    the job clears it when it claims the user. A flag, not a timestamp, on
    purpose: the sign-in happens in the web process and the job runs in the
    worker container, so no shared clock is required.
    """
    row = _status_row(db, user_id)
    row.sync_requested = True
    if row.status == SYNC_NEEDS_REAUTH:
        row.status = SYNC_PENDING
        row.last_error = None
        row.consecutive_failures = 0
    db.commit()


def mark_sync_succeeded(db: Session, user_id: int, now: datetime) -> None:
    """Record a finished, successful run: this is "last sync" for the UI."""
    row = _status_row(db, user_id)
    row.status = SYNC_OK
    row.last_finished_at = now
    row.last_success_at = now
    row.last_error = None
    row.consecutive_failures = 0
    db.commit()


def mark_sync_failed(db: Session, user_id: int, message: str, now: datetime) -> None:
    """Record a retryable failure; ``message`` must be user-safe (§18)."""
    row = _status_row(db, user_id)
    row.status = SYNC_ERROR
    row.last_finished_at = now
    row.last_error = message[:_MAX_ERROR_LENGTH]
    row.last_error_at = now
    row.consecutive_failures = (row.consecutive_failures or 0) + 1
    db.commit()


def mark_sync_needs_reauth(
    db: Session, user_id: int, message: str, now: datetime
) -> None:
    """Pause scheduled sync for a user until they sign in again (§63)."""
    row = _status_row(db, user_id)
    row.status = SYNC_NEEDS_REAUTH
    row.last_finished_at = now
    row.last_error = message[:_MAX_ERROR_LENGTH]
    row.last_error_at = now
    row.consecutive_failures = (row.consecutive_failures or 0) + 1
    db.commit()


def mark_sync_pending(db: Session, user_id: int, now: datetime) -> None:
    """Release a claim without reporting an error (no Google grant yet)."""
    row = _status_row(db, user_id)
    row.status = SYNC_PENDING
    row.last_finished_at = now
    db.commit()


def release_claim(db: Session, user_id: int, now: datetime) -> bool:
    """Release one user's claim without an error, if it is still ours.

    Used on SIGTERM (sync_worker.run_forever) so a graceful stop hands the
    account back to the schedule instead of parking it in ``running`` until
    the claim's stale window expires. The conditional guard is the same idea
    as :func:`claim_sync` in reverse: only a row that is still ``running``
    AND was started at or before ``now`` is released, so a shutdown in one
    worker can never cancel a job another process has already re-claimed.

    Returns True when a row was actually released. Releasing is best effort —
    a caller shutting down treats ``False`` as "nothing of mine to undo".
    """
    result = cast(
        CursorResult,
        db.execute(
            update(SyncStatus)
            .where(SyncStatus.user_id == user_id)
            .where(SyncStatus.status == SYNC_RUNNING)
            .where(
                or_(
                    SyncStatus.last_started_at.is_(None),
                    SyncStatus.last_started_at <= now,
                )
            )
            .values(status=SYNC_PENDING)
        ),
    )
    db.commit()
    return bool(result.rowcount)


def last_sync_time(db: Session, user_id: int) -> datetime | None:
    """When this user's cache was last filled successfully."""
    row = db.get(SyncStatus, user_id)
    return row.last_success_at if row else None


def last_sync_error(db: Session, user_id: int) -> str | None:
    """The user-facing description of the last failed run, if any."""
    row = db.get(SyncStatus, user_id)
    return row.last_error if row else None
