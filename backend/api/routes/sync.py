"""POST /api/sync — queue (hosted) or run (desktop) a sync of the caller's cache.

Both deployment shapes answer the same HTTP contract but do the work in
different places: desktop runs the fan-out inline in the request (ADR-0032),
hosted only flags the request and lets the worker container do it (DDoS plan
§9). The branch is decided once, in the handler.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004).

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import metrics
import ownership
import sync
from config import SYNC_STUCK_SECONDS
from database import get_db
from models_auth import User
from schemas import SyncResult

router = APIRouter()


@router.post("/sync", response_model=SyncResult)
def run_sync(
    request: Request,
    restart: bool = Query(
        default=False,
        description="Abandon a stuck sync and start a new one (ADR-0032).",
    ),
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> SyncResult:
    """Queue (hosted) or run (desktop) a sync of the calling user's cache.

    §12: /api/sync must never touch another user's data. Desktop: the local
    owner (token.json) — sync runs inline as before. Hosted: the session
    user's oauth_tokens — the request only flags ``sync_requested`` and
    answers ``{"ok": True, "queued": True, "status": "queued"}`` immediately;
    the worker container performs the actual Classroom fan-out (DDoS plan
    §9: never run the full sync inside the HTTP request).

    Hosted conflict mapping: a sync already in flight for THIS user → 409;
    a manual request inside the per-user cooldown → 429 + Retry-After; the
    background scheduler bypasses the cooldown. Other users sync
    independently. Rate-limit buckets (§39) stay in middleware.

    ``restart=true`` (ADR-0032) is the dashboard's answer to "this sync is
    stuck". It is the ONE case where an in-flight sync does not answer 409: a
    claim older than ``SYNC_STUCK_SECONDS`` is released and a new one queued.
    A younger claim still answers 409 — a long but progressing Classroom
    import must never be interrupted, and the cooldown is skipped only because
    the abandoned claim is by definition older than it.
    """
    if restart and _is_sync_running(db, user.id):
        # Hosted and desktop differ only in who performs the work, so the
        # restart decision is made once, before the branch below.
        if request.app.state.hosted:
            if not sync.restart_stuck_sync(db, user.id):
                raise HTTPException(
                    status_code=409,
                    detail="This synchronization is still running; try again later.",
                )
            return SyncResult(ok=True, queued=True, status="queued", restarted=True)
        return _restart_desktop_sync(user, db)
    # With no claim in flight there is nothing to abandon: `restart=true` falls
    # through to the ordinary request below rather than answering 409 about a
    # sync that does not exist.

    if request.app.state.hosted:
        from config import SYNC_MANUAL_COOLDOWN_SECONDS
        from sync_store import sync_status as _sync_row

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        row = _sync_row(db, user.id)
        if row is not None and row.status == sync.SYNC_RUNNING:
            # A running sync is not an error: 409 tells the client to keep
            # showing its spinner instead of surfacing a failure (§3.9).
            raise HTTPException(
                status_code=409, detail="A synchronization is already running."
            )
        if (
            SYNC_MANUAL_COOLDOWN_SECONDS > 0
            and row is not None
            and row.last_started_at is not None
            and (now - row.last_started_at).total_seconds()
            < SYNC_MANUAL_COOLDOWN_SECONDS
        ):
            raise HTTPException(
                status_code=429,
                detail="A sync just ran for this account; try again shortly.",
                headers={"Retry-After": str(SYNC_MANUAL_COOLDOWN_SECONDS)},
            )
        sync.request_sync(db, user.id)
        return SyncResult(ok=True, queued=True, status="queued")
    result = sync.sync_now(user=user, interactive=True)
    if not result.get("ok"):
        error = str(result.get("error", ""))
        if "already running" in error:
            # A running sync is not an error: 409 tells the client to keep
            # showing its spinner instead of surfacing a failure (§3.9).
            raise HTTPException(
                status_code=409, detail="A synchronization is already running."
            )
        if error == sync.SERVER_BUSY:
            raise HTTPException(status_code=503, detail=error)
    return SyncResult(**result)
def _is_sync_running(db: Session, user_id: int) -> bool:
    """Whether the calling user currently has a claimed sync in flight.

    The gate in front of every restart: a claim is what can be abandoned, and
    without one the request is an ordinary sync no matter which flag it carried.
    """
    row = sync.sync_status(db, user_id)
    return row is not None and row.status == sync.SYNC_RUNNING


def _restart_desktop_sync(user: User, db: Session) -> SyncResult:
    """Restart a stuck sync on desktop, where the sync runs inline (ADR-0032).

    Desktop has no queue and no separate worker: ``sync_now`` claims the row
    itself, so the restart is "release the stale claim, then run". Releasing
    first is what makes the retry possible at all — otherwise the new attempt
    would hit the very claim it is meant to replace.

    When the hung thread still holds the in-process per-user lock, the stale
    claim IS released but no second fan-out can start here; the next attempt
    (the user's click, or the desktop background schedule) proceeds normally.
    That case answers 409 with a message saying so — it is not a failed
    restart, and the dashboard keeps watching the status row either way.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not sync.abandon_claim(db, user.id, now, older_than=SYNC_STUCK_SECONDS):
        metrics.record(metrics.SYNC_RESTART_REJECTED)
        raise HTTPException(
            status_code=409,
            detail="This synchronization is still running; try again later.",
        )
    metrics.record(metrics.SYNC_RESTARTED)
    result = sync.sync_now(user=user, interactive=True)
    if not result.get("ok") and "already running" in str(result.get("error", "")):
        # The claim is free again, but the hung thread still owns the in-process
        # lock. Say so plainly instead of surfacing a generic failure.
        raise HTTPException(
            status_code=409,
            detail="The previous synchronization is still shutting down; "
            "try again in a moment.",
        )
    return SyncResult(**result, restarted=True)