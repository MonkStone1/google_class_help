"""GET /api/status — the short, fast poll the dashboard repeats every ~1.5 s.

Everything expensive is aggregated in SQL (``queries.dashboard``) rather than by
loading tables: this endpoint is hit continuously during sign-in and while a
sync runs, so its cost is multiplied by the number of open browsers.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import sync
from api import queries
from auth import identity, ownership
from core.config import SYNC_STUCK_SECONDS
from db.models.accounts import User
from db.session import get_db
from schemas.dashboard import SyncStatus

router = APIRouter()


@router.get("/status", response_model=SyncStatus)
def status(
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> SyncStatus:
    # Signed-in state of the CALLING user (§16): hosted reads the session
    # user, desktop the loopback account — never a global login state, and
    # never a Google profile lookup (identity is exposed via /auth/status
    # and /api/me only, §26).
    owner_id = user.id
    # Structured per-user sync state (migration stage 5, §18): the
    # dashboard sees a short status plus the last successful time — never
    # an exception trace (the stored message is already sanitized).
    sync_state = sync.sync_status(db, owner_id)
    return SyncStatus(
        authenticated=identity._is_authenticated(user),
        last_sync=sync_state.last_success_at if sync_state else None,
        last_sync_error=sync_state.last_error if sync_state else None,
        # A queued job is active from the moment it is requested. The status
        # row remains ``pending`` until the worker claims it, but the UI must
        # already show the spinner and follow it through completion.
        syncing=bool(
            sync_state
            and (sync_state.status == sync.SYNC_RUNNING or sync_state.sync_requested)
        ),
        sync_status=sync_state.status if sync_state else sync.SYNC_PENDING,
        last_sync_started_at=sync_state.last_started_at if sync_state else None,
        last_sync_finished_at=sync_state.last_finished_at if sync_state else None,
        # ADR-0032: the same threshold `?restart=true` enforces, published so
        # the dashboard's stuck verdict is the server's, not a second guess.
        sync_stuck_after_seconds=SYNC_STUCK_SECONDS,
        # Aggregated in SQL, not by loading every table: the frontend polls
        # this endpoint every ~1.5 s while signing in (review §2.1 / §1.3).
        **queries.dashboard._student_totals_sql(db, owner_id),
    )