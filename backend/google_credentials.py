"""User-scoped Google credential access (migration stage 4, §14/§15).

Layer separation (§14) — this module is the middle one and never decides
who the browser user is:

    Authentication layer   → who is the local application user?
                             (hosted_auth.py sessions / ownership.py)
    Google credential layer→ what Google OAuth credentials belong to that
                             user? (this module)
    Classroom service layer→ uses those credentials to call Google
                             (classroom_api.py / sync_service.py)

The conceptual interface of §15 — every operation is keyed by an
authenticated user, never by process-global state:

    get_google_credentials(db, user)      → valid Credentials | None
    save_google_credentials(db, user_id, creds)
    refresh_google_credentials(db, user)  → force a token refresh
    delete_google_credentials(db, user_id)

Two storage backends live behind one interface, dispatched by the user's
provider:

- ``google`` (hosted web OAuth, ADR-0020): the user's ``oauth_tokens`` row,
  access/refresh tokens encrypted at rest (token_crypto.py), refreshed
  under a **per-user** lock — one user's refresh traffic (a network call
  of up to ~30 s) must not serialize every other user's requests (§15).
  Concurrent refreshes of the SAME user's token are still prevented: the
  lock is re-checked, and the persisted ciphertext is reloaded under the
  lock, so only one POST to the token endpoint happens.
- ``local`` (desktop build, ADR-0019): the process's single ``token.json``
  via auth.py. A desktop build signs in exactly one Google account, so its
  single refresh lock is user-aware in effect — there is only one user.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets
#       (same dispensation as api.py / hosted_auth.py).

import logging
import threading
from datetime import datetime, timezone

import oauth_transport
from fastapi import Depends, HTTPException
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

import ownership
import token_crypto
from config import hosted_oauth_client_config
from database import get_db
from models_auth import OAuthToken, User

logger = logging.getLogger(__name__)

# Serialized per-user token refreshes (§15; audit A3): the refresh is a
# network call, so two threads hitting an expired token of the same user
# must not both POST to the token endpoint. One lock per user id; the
# desktop's single user simply gets one entry of the same structure.
_refresh_locks_guard = threading.Lock()
_refresh_locks: dict[int, threading.Lock] = {}


def _refresh_lock_for(user_id: int) -> threading.Lock:
    with _refresh_locks_guard:
        return _refresh_locks.setdefault(user_id, threading.Lock())


def _utcnow() -> datetime:
    """Naive UTC — the timestamp convention of the whole backend."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------- OAuth client config


def require_client_config() -> dict:
    """Hosted web client configuration, or HTTP 500 (fail closed, §9).

    Read from the environment on every call; a missing configuration is a
    deployment error and must never fall back to the desktop client.
    """
    client_config = hosted_oauth_client_config()
    if client_config is None:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth client configuration for the hosted service "
            "is missing (set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and "
            "GOOGLE_REDIRECT_URI or APP_BASE_URL).",
        )
    return client_config


# ------------------------------------------------------------ google backend


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


def save_google_credentials(db: Session, user_id: int, creds: Credentials) -> None:
    """Encrypt and persist one user's Google credentials (§8, §15).

    The ciphertext prefix from token_crypto makes plaintext rows impossible
    to confuse with encrypted ones; the encryption key never enters the
    database. One row per user (PK = user_id).
    """
    row = db.get(OAuthToken, user_id)
    if row is None:
        row = OAuthToken(user_id=user_id, created_at=_utcnow())
        db.add(row)
    row.access_token = token_crypto.encrypt(creds.token)
    row.refresh_token = (
        token_crypto.encrypt(creds.refresh_token) if creds.refresh_token else None
    )
    row.token_uri = creds.token_uri or "https://oauth2.googleapis.com/token"
    row.scopes = list(creds.scopes or oauth_transport.SCOPES)
    row.expires_at = creds.expiry
    row.updated_at = _utcnow()
    db.commit()


def _hosted_credentials(db: Session, user: User) -> Credentials | None:
    """The google-provider backend: oauth_tokens of that one user."""
    client_config = require_client_config()
    row = db.get(OAuthToken, user.id)
    if row is None:
        return None
    if not set(oauth_transport.SCOPES).issubset(set(row.scopes or [])):
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
            oauth_transport.refresh_credentials(creds)
        except Exception:  # noqa: BLE001 - a failed refresh means signed out
            logger.warning(
                "Google authorization refresh failed for user id=%s; sign-in required.",
                user.id,
            )
            return None
        save_google_credentials(db, user.id, creds)
        return creds


def refresh_google_credentials(db: Session, user: User) -> Credentials | None:
    """Force a refresh of one user's Google credentials (§15).

    Unlike :func:`get_google_credentials` (which refreshes only an expired
    token), this always contacts the token endpoint when a refresh token
    exists — e.g. after learning the access token was revoked server-side.
    Returns None when there is nothing to refresh.

    Stage 9 (§41): a refresh that fails with ``invalid_grant`` (revoked or
    rotated grant) deletes ONLY this user's ``oauth_tokens`` row — User B's
    grant is never touched — so the next sync reports ``needs_reauth``
    instead of retrying a dead grant forever. Transient failures leave the
    row alone for the backoff to retry.
    """
    if user.provider != "google":
        # Desktop: token.json of the single local user. auth is imported
        # here so the hosted service never loads the desktop module (§32).
        import auth

        creds = auth.load_credentials()
        if creds is None or not creds.refresh_token:
            return None
        try:
            oauth_transport.refresh_credentials(creds)
        except Exception:  # noqa: BLE001 - a failed refresh means signed out
            return None
        auth.save_credentials(creds)
        return creds
    row = db.get(OAuthToken, user.id)
    if row is None or not row.refresh_token:
        return None
    client_config = require_client_config()
    creds = Credentials(
        token=token_crypto.decrypt(row.access_token),
        refresh_token=_decrypt_refresh_token(row),
        token_uri=row.token_uri,
        client_id=client_config["client_id"],
        client_secret=client_config["client_secret"],
        scopes=list(row.scopes or []),
        expiry=row.expires_at or _utcnow(),
    )
    with _refresh_lock_for(user.id):
        try:
            oauth_transport.refresh_credentials(creds)
        except Exception as exc:  # noqa: BLE001 - see docstring
            if _is_invalid_grant(exc):
                logger.warning(
                    "Google grant revoked for user id=%s; grant row removed.",
                    user.id,
                )
                db.delete(row)
                db.commit()
            else:
                logger.warning(
                    "Google authorization refresh failed for user id=%s; sign-in required.",
                    user.id,
                )
            return None
        save_google_credentials(db, user.id, creds)
        return creds


def _is_invalid_grant(exc: Exception) -> bool:
    """Whether a refresh failure means the grant itself is dead (§41).

    google-auth surfaces ``RefreshError`` whose message carries the token
    endpoint's ``error`` field (``invalid_grant`` for revoked/rotated
    grants). Matching is substring-based and case-insensitive on purpose:
    the exact wrapper text is a library detail, the error code is stable.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    return "invalid_grant" in text


def has_google_grant(db: Session, user: User) -> bool:
    """Whether a Google authorization exists for this user, valid or not.

    Used by the sync orchestrator to tell "this user never signed in" from
    "the stored grant is unusable" (stage 5, §63): only the latter flips the
    user's sync status to ``needs_reauth`` and pauses scheduled sync. This
    reads no token material — it only checks that a credential record exists.
    """
    if user.provider == "google":
        return db.get(OAuthToken, user.id) is not None
    # Desktop local owner: the process's single token.json (ADR-0019).
    import auth

    return auth.load_credentials() is not None


def delete_google_credentials(db: Session, user_id: int) -> None:
    """Forget one user's Google credentials (§15).

    Hosted: the user's oauth_tokens row is deleted; sessions stay revocable
    independently (ADR-0020). Desktop: the single token.json is unlinked
    (auth.logout) — with one local user there is nothing else to scope.
    """
    user = db.get(User, user_id)
    if user is not None and user.provider != "google":
        import auth

        auth.logout()
        return
    row = db.get(OAuthToken, user_id)
    if row is not None:
        db.delete(row)
        db.commit()


# ------------------------------------------------------------ dispatch (§15)


def get_google_credentials(db: Session, user: User) -> Credentials | None:
    """Valid Google credentials of one authenticated user, or None.

    Refreshes an expired token when possible (per-user serialized for
    google-provider users). This is the ONLY way data paths obtain
    credentials: no caller may read a process-global token state (§14/§15).
    """
    if user.provider == "google":
        return _hosted_credentials(db, user)
    # Desktop local owner: the process's single token.json (ADR-0019).
    import auth

    return auth.get_valid_credentials()


def require_google_credentials(
    user: User = Depends(ownership.get_current_user), db: Session = Depends(get_db)
) -> Credentials:
    """Dependency: the session user's Google credentials, or 401 (§13/§15).

    For endpoints that call Classroom live (the cached dashboard reads do
    not); the desktop analogue is auth.require_credentials.
    """
    creds = get_google_credentials(db, user)
    if creds is None:
        raise HTTPException(
            status_code=401,
            detail="Not signed in to Google. Please sign in again.",
        )
    return creds
