# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets
#       (same dispensation as api.py).
"""Hosted web authentication: web OAuth flow, users, sessions (stage 2).

Migration prompt §4–§8 implemented for the hosted service. The desktop
loopback flow in ``auth.py`` (ADR-0019) is untouched and stays the primary
flow of the desktop build; this module is mounted only in hosted mode
(``GC_DASHBOARD_HOSTED=1``, ADR-0020).

Flow (§5):

    GET /api/auth/login      → 302 to Google consent (state + PKCE, both
                                stored server-side in oauth_login_states,
                                browser bound by a short-lived nonce cookie)
    Google → GET /api/auth/callback
                             → state + nonce validated, single-use
                             → code exchanged over the app's httplib2 transport
                             → userinfo resolves the Google identity (stable sub)
                             → user found/created, tokens encrypted at rest
                             → opaque session token in an HttpOnly cookie
                             → 302 back into the SPA

Security invariants enforced here (§5, §8, §9):

- random per-attempt state, stored server-side, single-use, mismatch → reject;
- the frontend never supplies a user id; identity comes from Google only;
- access/refresh tokens live in ``oauth_tokens`` encrypted (Fernet), are
  never returned in JSON, never put in cookies, never logged;
- the web client secret and the token-encryption key are read from the
  environment only;
- the authorization code is exchanged exactly once (state row deleted
  before the network exchange, so a replayed callback cannot reach the
  token endpoint with the same attempt);
- sessions are opaque random tokens, stored hashed (SHA-256), revocable
  independently of the Google grant; logout keeps the refresh token
  server-side (decision documented in ADR-0020);
- the redirect URI is the FIXED https endpoint of this flow
  (``GOOGLE_REDIRECT_URI`` from ``APP_BASE_URL``); the desktop loopback
  redirect is built dynamically in ``auth._CallbackServer`` and the two
  implementations are never shared (§75).

Since migration stage 4 the user-scoped credential operations (§15) live
in ``google_credentials.py``; this module owns the OAuth flow and the
sessions, and reaches credentials only through that layer.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import google_credentials
import httplib2
import oauth_transport
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

import sync_store
from config import COOKIE_HOST_PREFIX, COOKIE_SAMESITE, COOKIE_SECURE
from database import get_db
from models_auth import OAuthLoginState, User, UserSession
from proxy import external_scheme, peer_is_trusted_proxy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")

# --------------------------------------------------------------- parameters

STATE_TTL_SECONDS = 15 * 60
# Explicit expiry, no permanent sessions (migration prompt §37).
SESSION_TTL_SECONDS = 14 * 24 * 60 * 60
# §37: HttpOnly + Secure + SameSite=Lax + Path=/ + no Domain — which is
# exactly the constraint set of the optional ``__Host-`` prefix; the
# deployment opts in with GC_DASHBOARD_COOKIE_HOST_PREFIX=1 (see config,
# validated there against COOKIE_SECURE).
SESSION_COOKIE_NAME = f"{COOKIE_HOST_PREFIX}gch_session"
NONCE_COOKIE_NAME = f"{COOKIE_HOST_PREFIX}gch_oauth_nonce"
NONCE_TTL_SECONDS = STATE_TTL_SECONDS

# Google endpoints (stable OIDC values; deliberately not configuration: a
# wrong value here would send authorization codes to an attacker).
_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
# offline → refresh token; consent → re-issue even when a grant exists.
_EXTRA_AUTH_PARAMS = {"access_type": "offline", "prompt": "consent"}

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
        raise HTTPException(status_code=401, detail="Not signed in.")
    row = (
        db.query(UserSession)
        .filter(UserSession.session_token_hash == _sha256_hex(token))
        .one_or_none()
    )
    now = _utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=401, detail="Not signed in.")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Not signed in.")
    # Touch last_seen at most once a minute to keep writes off the hot path.
    if now - row.last_seen_at > timedelta(minutes=1):
        row.last_seen_at = now
        db.commit()
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
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


# ---------------------------------------------------------------- endpoints


@router.get("/login")
def login(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    """Start a login attempt: create server-side state, redirect to Google."""
    client_config = google_credentials.require_client_config()
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
    response = RedirectResponse(auth_url, status_code=302)
    # Binds the OAuth attempt to this browser: the callback must present
    # the same nonce (migration prompt §5: state bound to the initiator).
    # The nonce cookie must survive the cross-site redirect back from
    # Google, so it always stays SameSite=Lax — COOKIE_SAMESITE applies to
    # the session cookie, not to this one.
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
        response = RedirectResponse(f"/?login_error={status_code}", status_code=302)
        response.delete_cookie(NONCE_COOKIE_NAME, path="/")
        logger.warning("OAuth callback rejected: %s", detail)
        return response

    client_config = google_credentials.require_client_config()
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
        google_credentials.save_google_credentials(db, user.id, creds)
        # The account just granted (or re-granted) access: make it due for
        # the per-user scheduler immediately (stage 5, §63) instead of
        # waiting out the interval, and lift ``needs_reauth`` if the grant
        # had gone stale. sync_store is imported at module level below; no
        # cycle (it touches models only).
        sync_store.request_sync(db, user.id)
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
    logger.info("User id=%s signed in (hosted web OAuth).", user.id)
    return response


@router.get("/status")
def hosted_status(user: User = Depends(get_current_user)) -> dict:
    """AuthStatus for the hosted UI (§24): this browser's session only.

    Never any token material: only the local user id and the profile the
    UI renders, in the canonical ``user`` shape (§24). The flat
    ``user_name``/``user_email`` mirrors were removed in stage 7 (§26).
    """
    return {
        "authenticated": True,
        "login_in_progress": False,
        "error": None,
        "auth_url": None,
        "user": {
            "id": user.id,
            "name": user.display_name,
            "email": user.email,
        },
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
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response
