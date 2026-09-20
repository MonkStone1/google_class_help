"""Cache ownership resolution (migration stage 3).

The Classroom cache tables are user-scoped (models.py, migration prompt
§10): every row belongs to a local ``users`` row. Something has to say
WHICH user's rows a given read or write touches. This module is that
single seam, until the hosted data endpoints take the
``get_current_user`` dependency directly (migration stage 4):

- Desktop builds (ADR-0019) have no notion of an application user: the
  process signs in exactly one Google account. Its cache rows belong to
  one synthetic local user (provider "local", subject "desktop"),
  created on demand — the desktop cache keeps working unchanged on the
  user-scoped schema (audit: "desktop-путь обязан продолжать работать").

- Hosted service: the session-gate middleware (main.py, ADR-0020) resolves
  the session user before any /api data path runs and stores its id in
  ``request.state.user_id``; request-scoped cache access uses that id.

The synthetic local user is deliberately never created by a hosted
request: in hosted mode the id always comes from the session gate, so a
hosted database never accumulates a "local" row (fail closed, not shared
state).
"""

from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from models_auth import User

# The single implicit owner of a desktop build's cache. provider/subject
# mirror the Google-identity columns of users (models_auth.User) so both
# kinds of rows live in one table without special cases.
LOCAL_PROVIDER = "local"
LOCAL_SUBJECT = "desktop"


def _utcnow() -> datetime:
    """Naive UTC — the timestamp convention of the whole backend."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_local_owner(db: Session) -> User:
    """Return the desktop build's cache owner, creating the row once.

    Idempotent: repeated syncs/API calls reuse the same users row, so the
    cache of a desktop installation is always exactly one user's scope.
    """
    user = (
        db.query(User)
        .filter(User.provider == LOCAL_PROVIDER, User.provider_subject == LOCAL_SUBJECT)
        .one_or_none()
    )
    if user is None:
        now = _utcnow()
        user = User(
            provider=LOCAL_PROVIDER,
            provider_subject=LOCAL_SUBJECT,
            email=None,
            display_name=None,
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        db.add(user)
        db.flush()
    return user


def local_owner_id(db: Session) -> int:
    """The desktop cache owner's id (see :func:`ensure_local_owner`)."""
    return ensure_local_owner(db).id


def request_owner_id(request: Request, db: Session) -> int:
    """Owner of the cache rows for one API request (stage-3 seam).

    The hosted session gate stores the authenticated user's id in
    ``request.state.user_id`` before the request reaches any /api route;
    desktop requests carry no user state and resolve the single local
    owner. Stage 4 replaces per-endpoint usage of this helper with the
    ``get_current_user`` dependency; the scoping itself does not change.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        try:
            return int(user_id)
        except (TypeError, ValueError) as exc:
            # The gate only ever stores ints; a foreign value must not be
            # able to alias another user's cache (fail closed).
            raise HTTPException(status_code=401, detail="Not signed in.") from exc
    return local_owner_id(db)
