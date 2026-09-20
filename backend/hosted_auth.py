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
  server-side (decision documented in ADR-0020).
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httplib2
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

import auth
import token_crypto
from config import hosted_oauth_client_config
from database import get_db
from models_auth import OAuthLoginState, OAuthToken, User, UserSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")

# --------------------------------------------------------------- parameters

STATE_TTL_SECONDS = 15 * 60
# Explicit expiry, no permanent sessions (migration prompt §37).
SESSION_TTL_SECONDS = 14 * 24 * 60 * 60
SESSION_COOKIE_NAME = "gch_session"
NONCE_COOKIE_NAME = "gch_oauth_nonce"
NONCE_TTL_SECONDS = STATE_TTL_SECONDS

# Google endpoints (stable OIDC values; deliberately not configuration: a
# wrong value here would send authorization codes to an attacker).
_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
# offline → refresh token; consent → re-issue even when a grant exists.
_EXTRA_AUTH_PARAMS = {"access_type": "offline", "prompt": "consent"}

# Serialized per-user token refreshes (audit A3: the refresh is a network
# call; two threads hitting an expired token of the same user must not both
# POST to the token endpoint).
_refresh_locks_guard = threading.Lock()
_refresh_locks: dict[int, threading.Lock] = {}


def _refresh_lock_for(user_id: int) -> threading.Lock:
    with _refresh_locks_guard:
        return _refresh_locks.setdefault(user_id, threading.Lock())


# ------------------------------------------------------------------ helpers


def _utcnow() -> datetime:
    """Naive UTC — the timestamp convention of the whole backend."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    """GET over httplib2 — the app's single transport (ADR-0019)."""
    http = httplib2.Http(timeout=auth.TOKEN_TIMEOUT_SECONDS)
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


def _session_cookie_secure(request: Request) -> bool:
    """Secure flag follows the scheme (behind Caddy: X-Forwarded-Proto)."""
    forwarded = request.headers.get("x-forwarded-proto", "")
    scheme = forwarded.split(",")[0].strip() if forwarded else request.url.scheme
    return scheme == "https"


# --------------------------------------------------------- Google identity


def _build_authorization_url(
    client_config: dict, state: str, code_challenge: str, redirect_uri: str
) -> str:
    params = {
        "client_id": client_config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(auth.SCOPES),
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


def _store_token(db: Session, user_id: int, creds: Credentials, now: datetime) -> None:
    """Encrypt and persist the Google credentials (§8).

    The ciphertext prefix from token_crypto makes plaintext rows impossible
    to confuse with encrypted ones; the key never enters the database.
    """
    row = db.get(OAuthToken, user_id)
    if row is None:
        row = OAuthToken(user_id=user_id, created_at=now)
        db.add(row)
    row.access_token = token_crypto.encrypt(creds.token)
    row.refresh_token = (
        token_crypto.encrypt(creds.refresh_token) if creds.refresh_token else None
    )
    row.token_uri = creds.token_uri or _TOKEN_ENDPOINT
    row.scopes = list(creds.scopes or auth.SCOPES)
    row.expires_at = creds.expiry
    row.updated_at = now


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
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        domain=None,
        secure=secure,
        httponly=True,
        samesite="lax",
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
    """FastAPI dependency: the session user of this request.

    The seam every data endpoint will depend on from stage 4 on; in stage 2
    it additionally backs the hosted session gate in main.py, so no cached
    data is reachable without a session (audit §6.1: hosted access must not
    open before user-scoping exists).
    """
    user = resolve_session_user(request, db)
    request.state.user_id = user.id
    return user


# ------------------------------------------------------- credentials by user


def _decrypt_refresh_token(row: OAuthToken) -> str | None:
    if not row.refresh_token:
        return None
    try:
        return token_crypto.decrypt(row.refresh_token)
    except token_crypto.TokenEncryptionError as exc:
        logger.error(
            "Cannot read the stored Google authorization of user id=%s.",
            row.user_id,
        )
        raise HTTPException(
            status_code=401,
            detail="Stored credentials are unreadable; please sign in again.",
        ) from exc


def get_valid_credentials_for(db: Session, user: User) -> Credentials | None:
    """Valid Google credentials of one user, refreshed when possible.

    Hosted counterpart of ``auth.get_valid_credentials`` (audit A1/A3/A5):
    tokens come from ``oauth_tokens`` instead of the single token.json,
    refreshes are serialized per user, and a refreshed access token is
    persisted (encrypted) before it is handed out.
    """
    client_config = _require_client_config()
    row = db.get(OAuthToken, user.id)
    if row is None:
        return None
    if not set(auth.SCOPES).issubset(set(row.scopes or [])):
        # Token predates a scope change: force a new consent (same policy
        # as the desktop flow, auth.get_valid_credentials).
        db.delete(row)
        db.commit()
        return None

    def _build() -> Credentials:
        return Credentials(
            token=token_crypto.decrypt(row.access_token),
            refresh_token=_decrypt_refresh_token(row),
            token_uri=row.token_uri,
            client_id=client_config["client_id"],
            client_secret=client_config["client_secret"],
            scopes=list(row.scopes or []),
            expiry=row.expires_at,
        )

    creds = _build()
    if creds.valid:
        return creds
    if not creds.expired or not creds.refresh_token:
        return None
    with _refresh_lock_for(user.id):
        # Double-check under the lock: another thread may already have
        # refreshed and persisted the token while we waited.
        db.refresh(row)
        row.expires_at = row.expires_at or _utcnow()
        creds = _build()
        if creds.valid:
            return creds
        try:
            auth.refresh_credentials(creds)
        except Exception:  # noqa: BLE001 - a failed refresh means signed out
            logger.warning(
                "Google authorization refresh failed for user id=%s; sign-in required.",
                user.id,
            )
            return None
        _store_token(db, user.id, creds, _utcnow())
        db.commit()
        return creds


def require_google_credentials(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Credentials:
    """Google credentials of the session user, or 401.

    Hosted analogue of ``auth.require_credentials`` for data endpoints
    (stages 4+ rewire every endpoint to this dependency).
    """
    creds = get_valid_credentials_for(db, user)
    if creds is None:
        raise HTTPException(
            status_code=401,
            detail="Not signed in to Google. Please sign in again.",
        )
    return creds


# ---------------------------------------------------------------- endpoints

# Read once per process: the web client configuration is environment-only
# (§9). A missing configuration fails closed in every endpoint.
CLIENT_CONFIG: dict | None = hosted_oauth_client_config()


def _require_client_config() -> dict:
    if CLIENT_CONFIG is None:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth client configuration for the hosted service "
            "is missing (set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and "
            "GOOGLE_REDIRECT_URI or APP_BASE_URL).",
        )
    return CLIENT_CONFIG


@router.get("/login")
def login(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    """Start a login attempt: create server-side state, redirect to Google."""
    client_config = _require_client_config()
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

    client_config = _require_client_config()
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
        payload = auth.post_token_request(
            client_config, code, client_config["redirect_uri"], code_verifier
        )
        creds = auth.credentials_from_payload(client_config, payload)
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
        _store_token(db, user.id, creds, now)
        db.commit()
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
    """AuthStatus for the hosted UI (never any token material)."""
    return {
        "authenticated": True,
        "login_in_progress": False,
        "error": None,
        "auth_url": None,
        "user_name": user.display_name,
        "user_email": user.email,
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
