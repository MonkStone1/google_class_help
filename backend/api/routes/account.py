"""Self-service account endpoints: disconnect Google, delete everything (§44).

Both are destructive, both require ``confirm=true``, and neither has a global
variant: the server-side session stays valid after disconnecting Google (the
caller keeps the dashboard and its cached data), while deleting the account
removes the session too and drops the cookie on the way out (§37).
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import maintenance
from auth import identity, ownership
from db.models.accounts import User
from db.session import get_db

router = APIRouter()


@router.delete("/me/google")
def disconnect_google_account(
    confirm: bool = Query(default=False),
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Disconnect the caller's Google account, keep the local account (§44).

    Removes the stored OAuth credentials and resets the caller's sync state
    of THIS user only; the application session stays valid (the caller
    stays signed in to the dashboard and its cached data remains visible,
    with its last-sync timestamp). ``confirm=true`` is required because the
    action forces a fresh consent screen on the next sync.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to disconnect the Google account.",
        )
    # Desktop has no application account: this is exactly /api/auth/logout.
    if user.provider != "google":
        from auth import desktop

        desktop.logout()
        identity._reset_profile_cache(user.id)
        return {"ok": True, "disconnected": True}
    maintenance.disconnect_google(db, user.id)
    identity._reset_profile_cache(user.id)
    return {"ok": True, "disconnected": True}


@router.delete("/me")
def delete_own_account(
    request: Request,
    confirm: bool = Query(default=False),
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Delete everything stored for the CALLER (§44).

    The explicit "delete my account" path: sessions, OAuth credentials,
    sync state and the whole Classroom cache of this user are removed, and
    the local ``users`` row goes with them. Other users' rows are never
    touched — there is deliberately no global variant of this operation.

    Desktop builds have no server-side account (single local user, data in
    ``%LOCALAPPDATA%``): the endpoint is hosted-only and answers 400 there
    with a pointer to ``DELETE /api/cache`` + logout.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to delete the account and all cached data.",
        )
    if not request.app.state.hosted:
        raise HTTPException(
            status_code=400,
            detail=(
                "Desktop builds have no server-side account; use "
                "DELETE /api/cache and sign out instead."
            ),
        )
    removed = maintenance.delete_user_data(db, user)
    identity._reset_profile_cache(user.id)
    response = JSONResponse({"ok": True, "deleted": True, **removed})
    # The session no longer exists server-side; drop the cookie too so the
    # browser does not keep presenting a dead token (§37).
    from auth.hosted import SESSION_COOKIE_NAME

    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response