"""Cookie sessions: mint, verify, expire (ADR-0039 split).

Split out of ``hosted/__init__.py`` because the session is a SEPARATE mechanism
from the OAuth flow that produces the login: it has its own storage, its own TTL
and its own cookie rules, and it is what every request after the callback is
authenticated by. Keeping it apart makes "when does a session end" a question
about one file.

Two rules that are easy to lose in a move and are therefore enforced here
rather than at the call site:

- the cookie is HttpOnly and, when the deployment opts in, carries the
  ``__Host-`` prefix, which browsers refuse unless Path=/, Secure and no Domain
  all hold at once (config validates that combination at startup);
- the token is stored hashed. A dump of the ``user_sessions`` table is not a set
  of usable cookies, so a stolen database does not become a stolen account.
"""

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httplib2
from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core import metrics
from core.config import COOKIE_HOST_PREFIX, COOKIE_SAMESITE, COOKIE_SECURE
from core.proxy import external_scheme, peer_is_trusted_proxy
from db.models.accounts import User, UserSession
from db.session import get_db
from gapi import oauth_transport

logger = logging.getLogger(__name__)

# Explicit expiry, no permanent sessions (migration prompt §37).
SESSION_TTL_SECONDS = 14 * 24 * 60 * 60
# §37: HttpOnly + Secure + SameSite=Lax + Path=/ + no Domain — which is exactly
# the constraint set of the optional ``__Host-`` prefix; the deployment opts in
# with GC_DASHBOARD_COOKIE_HOST_PREFIX=1 (validated in core/config.py against
# COOKIE_SECURE).
SESSION_COOKIE_NAME = f"{COOKIE_HOST_PREFIX}gch_session"


# ------------------------------------------------------------------ helpers


def _utcnow() -> datetime:
    """Naive UTC — the timestamp convention of the whole backend."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    """GET over httplib2 — the app's single transport (ADR-0019)."""
    http = httplib2.Http(timeout=oauth_transport.TOKEN_TIMEOUT_SECONDS)
    response, content = http.request(url, "GET", headers=headers or {})
    if response.status != 200:
        raise RuntimeError(f"Google endpoint answered with status {response.status}.")
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Google endpoint returned an unreadable body.") from exc
    if not isinstance(data, dict):
        raise TypeError("Google endpoint returned an unexpected payload type.")
    return data


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_pair() -> tuple[str, str]:
    """PKCE S256 verifier + challenge (RFC 7636)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    return verifier, challenge


def _safe_relative(path: str) -> str:
    """Allow only same-origin SPA paths as post-login targets.

    Anything else ("//evil.com", absolute URLs, control characters) falls
    back to "/": the redirect after login must never become an open
    redirect.
    """
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    if "\\" in path or "\r" in path or "\n" in path:
        return "/"
    return path


def _peer_is_trusted_proxy(request: Request) -> bool:
    """Compatibility wrapper around the shared proxy trust decision (§29)."""
    return peer_is_trusted_proxy(request)


def _external_scheme(request: Request) -> str:
    """Compatibility wrapper around the shared external-scheme helper (§29)."""
    return external_scheme(request)


def _session_cookie_secure(request: Request) -> bool:
    """Secure flag of the session/nonce cookies (§29/§30).

    An explicit ``COOKIE_SECURE`` wins; otherwise it follows the external
    scheme, which is only trusted when it comes through a trusted proxy.
    """
    if COOKIE_SECURE is not None:
        return COOKIE_SECURE
    return _external_scheme(request) == "https"


# --------------------------------------------------------- Google identity


def _upsert_user(db: Session, identity: dict, now: datetime) -> User:
    """Find or create the local user keyed by Google's stable subject (§7).

    Handles every required case from §7: first login (create), returning
    login and second browser (same row found), changed email (refreshed
    from the profile), duplicate display names (irrelevant — identity is
    the subject), deactivated user (rejected until reactivated).
    """
    user = (
        db.query(User)
        .filter(User.provider == "google", User.provider_subject == identity["sub"])
        .one_or_none()
    )
    if user is None:
        user = User(
            provider="google",
            provider_subject=identity["sub"],
            email=identity.get("email"),
            display_name=identity.get("name"),
            created_at=now,
            updated_at=now,
            last_login_at=now,
            is_active=True,
        )
        db.add(user)
        db.flush()
        logger.info("Created local user id=%s for the Google subject.", user.id)
        return user
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is deactivated.")
    # Email can change; the subject cannot. Refresh local profile fields.
    user.email = identity.get("email")
    user.display_name = identity.get("name")
    user.last_login_at = now
    user.updated_at = now
    return user


# ---------------------------------------------------------------- sessions


def _create_session(
    db: Session, user_id: int, user_agent: str | None, now: datetime
) -> str:
    """Create a session row; returns the raw cookie token (never stored)."""
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            session_token_hash=_sha256_hex(token),
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(seconds=SESSION_TTL_SECONDS),
            last_seen_at=now,
            revoked_at=None,
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    db.commit()
    return token


def _set_session_cookie(response: RedirectResponse, token: str, secure: bool) -> None:
    # §37: HttpOnly + Secure + SameSite=Lax + Path=/, no Domain attribute.
    # SameSite is configurable (§30) but stays Lax by default: the OAuth
    # callback arrives as a cross-site top-level redirect.
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        domain=None,
        secure=secure,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )


def resolve_session_user(request: Request, db: Session) -> User:
    """Cookie → active user, or HTTPException 401.

    Plain function (no FastAPI DI) so the hosted session gate in main.py
    can call it directly from middleware as well.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        metrics.record(metrics.SESSION_REJECTED)
        raise HTTPException(status_code=401, detail="Not signed in.")
    row = (
        db.query(UserSession)
        .filter(UserSession.session_token_hash == _sha256_hex(token))
        .one_or_none()
    )
    now = _utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        metrics.record(metrics.SESSION_REJECTED)
        raise HTTPException(status_code=401, detail="Not signed in.")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        metrics.record(metrics.SESSION_REJECTED)
        raise HTTPException(status_code=401, detail="Not signed in.")
    # Touch last_seen at most once a minute to keep writes off the hot path.
    if now - row.last_seen_at > timedelta(minutes=1):
        row.last_seen_at = now
        db.commit()
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:  # noqa: B008
    """FastAPI dependency: the session user of this request (§13).

    Validates the session cookie and loads the active User record — it
    never trusts a user id from the request itself. Since stage 4 every
    data endpoint reaches it through ``ownership.get_current_user`` (which
    dispatches desktop requests to the local owner instead); this
    dependency additionally backs the hosted session gate in main.py.
    """
    user = resolve_session_user(request, db)
    request.state.user_id = user.id
    return user
