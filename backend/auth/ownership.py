"""Cache ownership and the current-user dependency (migration stage 4).

The Classroom cache tables are user-scoped (models.py, migration prompt
§10): every row belongs to a local ``users`` row. :func:`get_current_user`
(§13) is the single dependency that says WHICH user a request belongs to:

- Hosted service: the request's session cookie is validated and the local
  User record loaded (hosted_auth.py, ADR-0020). The dependency does this
  itself — it never trusts a value the frontend or another layer supplied.
- Desktop builds (ADR-0019) have no notion of an application user: the
  process signs in exactly one Google account, so the current user is the
  synthetic local owner (provider "local", subject "desktop"), created on
  demand — the desktop cache keeps working unchanged on the user-scoped
  schema (audit: "desktop-путь обязан продолжать работать").

The synthetic local user is deliberately never created by a hosted
request: in hosted mode the id always comes from the session, so a hosted
database never accumulates a "local" row (fail closed, not shared state).
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets
#       (same dispensation as api.py / hosted_auth.py).

from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from db.models.accounts import User
from db.session import get_db

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


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """The authenticated user of this request (migration stage 4, §13).

    One dependency for both deployment modes, selected by the app instance
    (``app.state.hosted``, set by ``main.create_app``) — not by a process
    flag, so tests can build both apps side by side:

    - hosted: the session cookie is read, validated against ``sessions``
      (missing/expired/revoked → 401) and the active local User record is
      loaded (hosted_auth.get_current_user). No handler may trust any
      user id from the request itself.
    - desktop: the single local owner (loopback OAuth has no sessions;
      the process is the one user, ADR-0019).
    """
    if request.app.state.hosted:
        # Imported here, not at module level: hosted_auth builds on this
        # module's credential layer (google_credentials), which depends on
        # ownership.get_current_user in turn.
        from auth.hosted import get_current_user as session_user

        return session_user(request, db)
    return ensure_local_owner(db)
