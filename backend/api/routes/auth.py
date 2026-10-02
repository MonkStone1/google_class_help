"""Identity endpoints of the caller: /auth/status, /me, login, logout.

The handlers are thin by design: ``api.identity`` owns the profile cache and
the ``UserOut``/``AuthStatus`` projection, ``hosted_auth.py`` calls that same
projection for its own status route, and the desktop-only ``auth`` module is
imported lazily inside the branches that need it so the hosted service never
loads it (migration stage 8, §32).
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import ownership
from api import identity
from database import get_db
from models_auth import User
from schemas import AuthStatus, UserOut

router = APIRouter()


@router.get("/auth/status", response_model=AuthStatus)
def auth_status(
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> AuthStatus:
    return identity._build_auth_status(user, db)


@router.get("/me", response_model=UserOut)
def me(
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """Identity of the signed-in user (§23/§24).

    Same identity source as ``/api/auth/status``: the validated session
    user in hosted mode, the desktop local owner (with the Google profile
    resolved and cached per user) in desktop mode. A request without a
    valid application session is rejected earlier with 401 (hosted session
    gate / dependency); this handler never sees an anonymous caller.
    """
    status = identity._build_auth_status(user, db)
    # ``user`` is always populated by _build_auth_status; the fallback keeps
    # the type honest without inventing a second identity source.
    return status.user or identity._user_out(user, db)


@router.post("/auth/login", response_model=AuthStatus)
def login(
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> AuthStatus:
    import auth

    result = auth.start_login()
    if not result.get("started"):
        raise HTTPException(
            status_code=500, detail=result.get("error", "Login failed.")
        )
    return identity._build_auth_status(user, db)


@router.post("/auth/logout", response_model=AuthStatus)
def logout(
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> AuthStatus:
    import auth

    auth.logout()
    # Only the caller's cached profile is dropped (§17); the next sign-in on
    # this browser may be another account, but other users' entries stay.
    identity._reset_profile_cache(user.id)
    return identity._build_auth_status(user, db)