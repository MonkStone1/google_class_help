"""Hosted web OAuth: the endpoints, and the router main.py mounts.

Three parts, separated by what they are FOR rather than by size:

- ``sessions``  — the cookie session every later request is authenticated by
- ``turnstile`` — the optional DDoS guard in front of login initiation
- here         — the OAuth dance itself: login, callback, status, logout

The OAuth half stays here because it is the only part that knows the ORDER of
the round trip (nonce → redirect → callback → session), and splitting a
sequence across files is how a step ends up in the wrong one.

This package is also what ``main.py`` imports lazily: the hosted startup path
must never pull in a desktop module, and keeping ``auth/hosted/__init__.py``
importable without ``auth/desktop.py`` is what makes that checkable.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom puts Depends() in the
# parameter default; that is how every handler in this backend declares its
# session and DB, and rewriting it would obscure the signatures.

import hmac
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from auth.hosted import turnstile
from auth.hosted.sessions import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,  # noqa: F401  (re-export)
    _create_session,
    _http_get_json,
    _pkce_pair,
    _safe_relative,
    _session_cookie_secure,
    _set_session_cookie,
    _sha256_hex,
    _upsert_user,
    _utcnow,
    get_current_user,
    resolve_session_user,  # noqa: F401  (re-export)
)
from auth.hosted.turnstile import LoginStartIn, _turnstile_enabled, _verify_turnstile
from core import metrics
from db.models.accounts import OAuthLoginState, User, UserSession
from db.session import get_db
from gapi import credentials, oauth_transport
from sync import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")

# --------------------------------------------------------------- parameters

STATE_TTL_SECONDS = 15 * 60
NONCE_COOKIE_NAME = "gch_oauth_nonce"
NONCE_TTL_SECONDS = STATE_TTL_SECONDS

# Google endpoints (stable OIDC values; deliberately not configuration: a
# wrong value here would send authorization codes to an attacker).
_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
# offline → refresh token; consent → re-issue even when a grant exists.
_EXTRA_AUTH_PARAMS = {"access_type": "offline", "prompt": "consent"}
# Where a browser lands when Turnstile demands a challenge (DDoS plan §17).
_TURNSTILE_LANDING = "/?challenge=required"


def _build_authorization_url(
    client_config: dict, state: str, code_challenge: str, redirect_uri: str
) -> str:
    params = {
        "client_id": client_config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(oauth_transport.SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        **_EXTRA_AUTH_PARAMS,
    }
    return f"{_AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


def _fetch_identity(access_token: str) -> dict:
    """Resolve the Google user from an access token (stable ``sub``, §7)."""
    identity = _http_get_json(
        _USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}
    )
    if not identity.get("sub"):
        raise RuntimeError("Google userinfo response did not contain a subject.")
    return identity


# ---------------------------------------------------------------- endpoints


@router.get("/turnstile")
def turnstile_config() -> dict:
    """Tell the frontend whether login needs a challenge (site key is public)."""
    if _turnstile_enabled():
        # Read through the turnstile module: the keys are ITS configuration, and
        # a name bound here would be a copy that a test cannot replace (ADR-0039).
        return {"enabled": True, "site_key": turnstile.TURNSTILE_SITE_KEY}
    return {"enabled": False, "site_key": None}


def _begin_login(request: Request, db: Session) -> tuple[str, str]:
    """Create server-side state for one login attempt.

    Returns ``(google_authorization_url, nonce)`` — the caller attaches the
    nonce cookie itself (RedirectResponse vs JSONResponse differ between the
    plain GET flow and the Turnstile-guarded POST /login/start).
    """
    client_config = credentials.require_client_config()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = _pkce_pair()
    now = _utcnow()
    db.add(
        OAuthLoginState(
            state=state,
            browser_nonce=nonce,
            code_verifier=verifier,
            redirect_to=_safe_relative(request.query_params.get("redirect_to", "/")),
            created_at=now,
            expires_at=now + timedelta(seconds=STATE_TTL_SECONDS),
        )
    )
    # Expired attempts are garbage; delete them in passing.
    db.query(OAuthLoginState).filter(OAuthLoginState.expires_at <= now).delete()
    db.commit()

    auth_url = _build_authorization_url(
        client_config, state, challenge, client_config["redirect_uri"]
    )
    return auth_url, nonce


def _attach_nonce(
    response: RedirectResponse | JSONResponse, request: Request, nonce: str
) -> None:
    """Bind the OAuth attempt to this browser (migration prompt §5).

    The nonce cookie must survive the cross-site redirect back from Google,
    so it always stays SameSite=Lax — COOKIE_SAMESITE applies to the session
    cookie, not to this one.
    """
    response.set_cookie(
        NONCE_COOKIE_NAME,
        nonce,
        max_age=NONCE_TTL_SECONDS,
        path="/",
        domain=None,
        secure=_session_cookie_secure(request),
        httponly=True,
        samesite="lax",
    )


@router.get("/login")
def login(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    """Start a login attempt: create server-side state, redirect to Google."""
    if _turnstile_enabled():
        # DDoS plan §17: when a challenge is configured, the direct GET
        # bypass must not exist — send the browser to the SPA, which renders
        # the widget and POSTs the solved token to /login/start.
        return RedirectResponse(_TURNSTILE_LANDING, status_code=302)
    auth_url, nonce = _begin_login(request, db)
    response = RedirectResponse(auth_url, status_code=302)
    _attach_nonce(response, request, nonce)
    return response


@router.post("/login/start")
def login_start(
    payload: LoginStartIn, request: Request, db: Session = Depends(get_db)
) -> JSONResponse:
    """Turnstile-guarded login start (DDoS plan §17).

    Flow: widget → browser POSTs the solved ``token`` → backend verifies it
    at Cloudflare siteverify (fail-closed) → same server-side state as the
    plain GET flow → JSON ``{"redirect_url": …}`` the SPA navigates to.
    With Turnstile disabled (empty keys) the endpoint still works and only
    requires no token, so the frontend has one code path.
    """
    if _turnstile_enabled():
        token = (payload.token or "").strip()
        if not token:
            metrics.record("turnstile_rejected")
            raise HTTPException(
                status_code=403, detail="Verification challenge required."
            )
        if not _verify_turnstile(token):
            metrics.record("turnstile_rejected")
            logger.warning("Turnstile challenge rejected for a login start")
            raise HTTPException(
                status_code=403, detail="Verification challenge failed."
            )
        metrics.record("turnstile_accepted")
    auth_url, nonce = _begin_login(request, db)
    response = JSONResponse({"redirect_url": auth_url})
    _attach_nonce(response, request, nonce)
    return response


@router.post("/login")
def login_post() -> None:
    """Hosted mode has no desktop loopback login: sign-in is a redirect."""
    raise HTTPException(
        status_code=405,
        detail="Sign-in starts with a browser redirect: GET /api/auth/login.",
    )


@router.get("/callback")
def callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    """Validate the redirect, exchange the code, create the session."""

    def _fail(detail: str, status_code: int = 400) -> RedirectResponse:
        # Fail closed to the dashboard with a short marker; the reason goes
        # to the log only (no token/code material, §5 "never log").
        # Stage 9 (§39): rejected callbacks are counted per IP so an error
        # loop cannot retry forever — successes are never throttled.
        from core.config import RATE_LIMIT_CALLBACK_FAILURES_PER_MINUTE
        from core.proxy import client_ip as _client_ip

        limiter = request.app.state.rate_limiter
        if not limiter.allow(
            f"callback-fail:{_client_ip(request)}",
            capacity=RATE_LIMIT_CALLBACK_FAILURES_PER_MINUTE,
            refill_per_second=RATE_LIMIT_CALLBACK_FAILURES_PER_MINUTE / 60.0,
        ):
            logger.warning("OAuth callback failure bucket exhausted: %s", detail)
            metrics.record(metrics.LOGIN_FAILED)
            response = RedirectResponse("/?login_error=429", status_code=302)
            response.delete_cookie(NONCE_COOKIE_NAME, path="/")
            return response
        metrics.record(metrics.LOGIN_FAILED)
        response = RedirectResponse(f"/?login_error={status_code}", status_code=302)
        response.delete_cookie(NONCE_COOKIE_NAME, path="/")
        logger.warning("OAuth callback rejected: %s", detail)
        return response

    client_config = credentials.require_client_config()
    params = request.query_params
    state = params.get("state", "")
    code = params.get("code", "")
    error = params.get("error")
    nonce_cookie = request.cookies.get(NONCE_COOKIE_NAME)

    row = (
        db.query(OAuthLoginState).filter(OAuthLoginState.state == state).one_or_none()
        if state
        else None
    )
    if row is None:
        return _fail("unknown or expired state")
    if error:
        # Single use: the attempt is over even when Google reports an error.
        db.delete(row)
        db.commit()
        return _fail(f"Google refused the sign-in: {error}")
    if nonce_cookie is None or not hmac.compare_digest(
        nonce_cookie.encode("utf-8"), row.browser_nonce.encode("utf-8")
    ):
        # A callback that fails validation still consumes the attempt: the
        # first presentation of a state is the only one that may proceed.
        db.delete(row)
        db.commit()
        return _fail("login attempt does not belong to this browser")
    if row.expires_at <= _utcnow():
        db.delete(row)
        db.commit()
        return _fail("login attempt expired")

    # Single use BEFORE the network exchange: a replayed callback can never
    # reach the token endpoint with this state again.
    redirect_to = row.redirect_to
    code_verifier = row.code_verifier
    db.delete(row)
    db.commit()

    if not code:
        return _fail("the redirect carried no authorization code")

    # The code is exchanged over the shared httplib2 transport (ADR-0019);
    # the PKCE verifier from the stored state goes with it. Failures are
    # logged without the code/token values.
    try:
        payload = oauth_transport.post_token_request(
            client_config, code, client_config["redirect_uri"], code_verifier
        )
        creds = oauth_transport.credentials_from_payload(client_config, payload)
    except RuntimeError as exc:
        logger.warning("OAuth code exchange failed: %s", exc)
        return _fail("authorization code exchange failed", 502)

    try:
        identity = _fetch_identity(creds.token)
    except (RuntimeError, TypeError) as exc:
        logger.warning("Google userinfo lookup failed: %s", exc)
        return _fail("could not resolve the Google account", 502)

    now = _utcnow()
    try:
        user = _upsert_user(db, identity, now)
        credentials.save_google_credentials(db, user.id, creds)
        # The account just granted (or re-granted) access: make it due for
        # the per-user scheduler immediately (stage 5, §63) instead of
        # waiting out the interval, and lift ``needs_reauth`` if the grant
        # had gone stale. sync_store is imported at module level below; no
        # cycle (it touches models only).
        store.request_sync(db, user.id)
        session_token = _create_session(
            db, user.id, request.headers.get("user-agent"), now
        )
    except HTTPException as exc:
        db.rollback()
        return _fail(
            exc.detail if isinstance(exc.detail, str) else "login failed",
            exc.status_code,
        )

    response = RedirectResponse(redirect_to, status_code=302)
    _set_session_cookie(response, session_token, _session_cookie_secure(request))
    response.delete_cookie(NONCE_COOKIE_NAME, path="/")
    metrics.record(metrics.LOGIN_SUCCEEDED)
    logger.info("User id=%s signed in (hosted web OAuth).", user.id)
    return response


@router.get("/status")
def hosted_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """AuthStatus for the hosted UI (§24): this browser's session only.

    Never any token material: only the local user id and the profile the
    UI renders, in the canonical ``user`` shape (§24). The flat
    ``user_name``/``user_email`` mirrors were removed in stage 7 (§26).

    The ``user`` object is built by ``auth.identity._user_out`` — the SAME
    helper the desktop status and ``/api/me`` use — so the role flags
    (ADR-0036) are computed by one function and cannot drift between the two
    surfaces.
    """
    # Imported here, not at module level: auth.identity is the module this one
    # builds on (§32 desktop/hosted separation is about the desktop modules; the
    # shared projection is the point here), so a module-level import would close
    # the identity -> ownership -> hosted -> identity cycle at import time.
    from auth.identity import _user_out

    return {
        "authenticated": True,
        "login_in_progress": False,
        "error": None,
        "auth_url": None,
        "user": _user_out(user, db).model_dump(),
    }


@router.post("/logout")
def logout(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Revoke the application session; keep the Google grant (ADR-0020).

    The stored refresh token is retained server-side so the next sign-in
    can reuse the Google authorization without a new consent screen; the
    session alone dies here.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        row = (
            db.query(UserSession)
            .filter(UserSession.session_token_hash == _sha256_hex(token))
            .one_or_none()
        )
        if row is not None:
            row.revoked_at = _utcnow()
            db.commit()
            metrics.record(metrics.LOGOUT)
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response
