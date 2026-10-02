"""Role resolution and administrator authorization (ADR-0036).

One resolver, ``resolve_role``, is the ONLY place that decides who the caller
is. Every admin endpoint takes ``Depends(require_admin)`` (or
``Depends(require_super_admin)``) as a parameter, so "add an admin route and
forget the guard" is not expressible without visibly dropping it, and the
booleans ``UserOut.is_admin`` / ``UserOut.is_super_admin`` are produced by the
same function — they can never disagree with the API's verdict.

Three roles, resolved in this order:

1. **SUPER ADMIN** — the address equals ``config.SUPER_ADMIN_EMAIL``. Server-side
   only: the value never reaches a browser bundle, a ``/api/config`` field or the
   OpenAPI document, and it is deliberately NOT a row of the ``admins`` table, so
   the management API can never delete it. Unset/blank/``@``-less ⇒ nobody.
2. **ADMIN** — a row exists in ``admins`` with this address. The e-mail is the
   identity, stored normalized (``config.normalize_email``).
3. **USER** — everything else, including the desktop local owner, whose
   ``email is None``.

Deliberately thin:

- it does NOT parse the session. ``get_current_user`` has already rejected an
  anonymous request with 401 (and the hosted session gate answers even earlier),
  so re-implementing session resolution here would create a second way to learn
  who the caller is — exactly what ADR-0022 forbids;
- it never trusts a request-supplied e-mail, header, query parameter or form
  field. The identity is the validated session and nothing else;
- 401 is deliberately absent from both dependencies: an unauthenticated request
  never reaches them.

FastAPI caches a dependency per request, so the ``db`` resolved here is the SAME
``get_db`` session the handler receives — one connection per request.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets
#       (same dispensation as api.py / ownership.py).

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
import ownership
from config import normalize_email
from database import get_db
from models_admin import Admin
from models_auth import User

ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLE_SUPER_ADMIN = "super_admin"

# The local part of an address is turned into a display label by splitting the
# usual separators; the domain is dropped. A tuple, not a regex: the
# transformation is three ``str.replace`` calls, and a compiled pattern would
# hide a rule this simple.
_NAME_SEPARATORS = (".", "_", "-")


def is_super_admin_email(email: str | None) -> bool:
    """Whether an address is the configured Super Admin.

    Compared against the already-normalized ``config.SUPER_ADMIN_EMAIL``, so case
    and surrounding whitespace on the caller's side cannot decide the verdict. An
    unset/blank/``@``-less configuration makes this ``False`` for every address
    (fail closed).

    ``config.SUPER_ADMIN_EMAIL`` is read through the MODULE, not through a
    ``from config import`` binding: config parses the environment once at import
    time, and only the module attribute reflects a later change to it. A private
    ``from`` copy would silently keep answering with the value captured at import.
    """
    configured = config.SUPER_ADMIN_EMAIL
    if not configured:
        return False
    return normalize_email(email) == configured


def display_name_from_email(email: str) -> str:
    """A human label derived from an address, deterministically.

    ``john.doe@gmail.com`` → ``John Doe``; ``john_doe@…`` and ``john-doe@…`` →
    ``John Doe``; ``john@gmail.com`` → ``John``. The local part is split on the
    usual separators, title-cased and rejoined; a local part with no separator is
    title-cased as it is.

    Derived, never stored and never fetched from Google: a second copy of the
    identity would be a second thing to keep in sync, and this one cannot drift
    because it is a pure function of the stored address.
    """
    local = normalize_email(email).split("@", 1)[0]
    for separator in _NAME_SEPARATORS:
        local = local.replace(separator, " ")
    return " ".join(part.capitalize() for part in local.split() if part)


def _is_registered_admin(db: Session, email: str) -> bool:
    """One indexed SELECT on the normalized address."""
    return db.execute(select(Admin.id).where(Admin.email == email)).first() is not None


def resolve_role(db: Session, email: str | None) -> str:
    """The one role resolver of the feature: SUPER ADMIN, ADMIN or USER.

    Super Admin is checked FIRST, so the environment stays the single authority
    for the one role it defines even if the same address was also inserted into
    ``admins`` under an earlier configuration.

    An empty address is answered without a query at all: the desktop local owner
    has ``email is None`` and is therefore never an administrator, and spending a
    roundtrip to learn what ``""`` cannot match is pointless.
    """
    normalized = normalize_email(email)
    if not normalized:
        return ROLE_USER
    if is_super_admin_email(normalized):
        return ROLE_SUPER_ADMIN
    if _is_registered_admin(db, normalized):
        return ROLE_ADMIN
    return ROLE_USER


def is_admin_email(db: Session, email: str | None) -> bool:
    """Whether this address is ANY administrator (Admin or Super Admin).

    The DB-backed replacement of the deleted ADR-0035 allow-list test. Callers
    that must tell the two roles apart use ``resolve_role`` instead; this helper
    exists for the read-through paths (an attachment download, say) where "an
    administrator may see this" is the whole question.
    """
    return resolve_role(db, email) != ROLE_USER


def require_admin(
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """The caller, if an administrator (either role); 403 otherwise.

    401 is deliberately absent: an unauthenticated request never reaches here —
    the hosted session gate and ``ownership.get_current_user`` answer it first.
    """
    if not is_admin_email(db, user.email):
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def require_super_admin(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    """The caller, if the Super Admin; 403 for a plain administrator.

    Composed on top of ``require_admin`` on purpose: a caller who is not an
    administrator at all must keep the SAME 403 answer, and the 401 path stays in
    exactly one place (``ownership.get_current_user`` and the hosted session gate)
    instead of being re-implemented per dependency.
    """
    if resolve_role(db, user.email) != ROLE_SUPER_ADMIN:
        raise HTTPException(
            status_code=403, detail="Super administrator access required."
        )
    return user
