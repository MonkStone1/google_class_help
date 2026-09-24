"""Data retention and account deletion (migration stage 9, §44/§61).

The hosted service stores more than a cache: sessions, OAuth grants and
per-user sync state. Each of them needs an explicit end-of-life rule, and
"delete my data" must be a first-class operation that touches exactly ONE
user's rows.

Two layers live here:

1. **Retention sweep** (:func:`purge_expired`) — housekeeping that removes
   data whose own timestamps say it is dead: expired/revoked sessions and
   expired OAuth login attempts. It runs from the worker on the same
   schedule as sync scans, is idempotent, and never touches rows of an
   active user.
2. **Deletion** (:func:`delete_user_data`, :func:`disconnect_google`) —
   the explicit "delete my account" / "disconnect Google" paths. Both take
   the caller's own user id from the session (api.py) and delete only that
   user's rows: sessions, ``oauth_tokens``, ``sync_status`` and the whole
   Classroom cache through the ``courses`` cascade (coursework, rosters,
   roles, submissions). There is deliberately no global "clear everything"
   helper: §44 forbids destroying other users' data as a side effect of one
   user's request.

Retention policy (documented in ADR-0027):

    sessions           14 days TTL (ADR-0020); logout revokes immediately;
                       expired/revoked rows are swept
    oauth_login_states 15 minutes TTL (one OAuth attempt); swept on login
                       and by the retention sweep
    oauth_tokens       until disconnect or account deletion; a refresh
                       answering invalid_grant drops the row immediately
                       (§41)
    cache (courses →   until the next sync reconciles it, when the user
      children)        clears it, or when the account is deleted; a
                       ``synced_at``/``last_sync`` timestamp is always
                       exposed so stale data is never presented as current
                       (§61)
    sync_status        lives with the user (FK CASCADE), same as the cache
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

import metrics
from models import Course, SyncStatus
from models_auth import OAuthLoginState, OAuthToken, User, UserSession

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Naive UTC — the timestamp convention of the whole backend."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def purge_expired(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Delete expired/revoked sessions and expired OAuth attempts (§44).

    Returns the per-table counts so the worker can log them. Deleting a
    session row does NOT touch the user's Google grant: a browser that is
    simply gone must not force a new consent screen (ADR-0020).
    """
    moment = now or _utcnow()
    sessions = (
        db.query(UserSession)
        .filter(
            (UserSession.expires_at <= moment) | (UserSession.revoked_at.is_not(None))
        )
        .delete(synchronize_session=False)
    )
    states = (
        db.query(OAuthLoginState)
        .filter(OAuthLoginState.expires_at <= moment)
        .delete(synchronize_session=False)
    )
    db.commit()
    if sessions:
        metrics.record(metrics.SESSION_PURGED, int(sessions))
    if states:
        metrics.record(metrics.LOGIN_STATE_PURGED, int(states))
    return {"sessions": int(sessions), "login_states": int(states)}


def revoke_sessions(db: Session, user_id: int) -> int:
    """Revoke every session of one user (§44); the grant is kept."""
    count = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .update({UserSession.revoked_at: _utcnow()}, synchronize_session=False)
    )
    db.commit()
    return int(count)


def disconnect_google(db: Session, user_id: int) -> None:
    """Forget one user's Google grant but keep the application account (§44).

    The local account, its sessions (the caller stays signed in to the
    dashboard) and its cached data remain; only ``oauth_tokens`` and the
    sync state of THIS user are reset, so the dashboard falls back to the
    cache and offers "sign in again".
    """
    row = db.get(OAuthToken, user_id)
    if row is not None:
        db.delete(row)
    state = db.get(SyncStatus, user_id)
    if state is not None:
        state.status = "pending"
        state.last_error = None
        state.last_error_at = None
        state.consecutive_failures = 0
        state.sync_requested = False
        # ``last_success_at`` stays: the cache it describes is still on
        # screen, and §61 requires its age to remain visible.
    db.commit()
    logger.info("Google grant disconnected for user id=%s.", user_id)


def delete_user_data(db: Session, user: User) -> dict[str, int]:
    """Remove everything the service stores about one user (§44).

    Order matters on PostgreSQL: sessions/tokens/sync_status and the cache
    rows are children of ``users`` and would go with the row anyway
    (ON DELETE CASCADE), but deleting them explicitly keeps SQLite
    (desktop) and PostgreSQL identical and lets the caller report what was
    removed. No other user's row is ever touched: every statement carries
    this user's id.
    """
    user_id = user.id
    sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .delete(synchronize_session=False)
    )
    tokens = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == user_id)
        .delete(synchronize_session=False)
    )
    status = (
        db.query(SyncStatus)
        .filter(SyncStatus.user_id == user_id)
        .delete(synchronize_session=False)
    )
    # The cache cascades from courses: coursework, course_roles,
    # course_students, submissions and coursework_submissions all reference
    # (user_id, course_id) with ON DELETE CASCADE.
    courses = (
        db.query(Course)
        .filter(Course.user_id == user_id)
        .delete(synchronize_session=False)
    )
    db.delete(user)
    db.commit()
    logger.info(
        "User id=%s deleted: sessions=%s tokens=%s courses=%s sync_rows=%s.",
        user_id,
        sessions,
        tokens,
        courses,
        status,
    )
    return {
        "sessions": int(sessions),
        "tokens": int(tokens),
        "courses": int(courses),
        "sync_status": int(status),
    }
