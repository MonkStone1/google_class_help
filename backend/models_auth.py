"""Identity, session and OAuth-credential tables (hosted mode, stage 2).

Separate from ``models.py`` on purpose: those models are the per-account
Classroom cache (ADR-0003), these are the application's own auth layer
(migration prompt §6):

    Google account → local User → OAuth credentials → session(s)

Identity uses Google's stable OpenID ``sub`` (migration prompt §7), never
the email alone. Sessions are opaque random tokens stored only as a SHA-256
hash; the raw token lives only in the browser cookie. Google access/refresh
tokens are stored encrypted at rest (token_crypto.py) and never leave the
backend. New tables are created by ``create_all`` (ADR-0003).
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    """One local application user, linked to one Google account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Identity provider. Only "google" exists today; the column keeps the
    # door open without inventing structure.
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="google")
    # Google's stable OpenID subject identifier (userinfo "sub"). Email is
    # NOT the identity key: it can change (migration prompt §7).
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    # Local profile fields, refreshed from Google at every login.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # A deactivated user's sessions stop resolving, but the rows (and the
    # Classroom cache linkage planned for stage 3) survive deactivation.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserSession(Base):
    """One authenticated browser session (opaque token, stored hashed).

    Revocable independently of the Google grant (migration prompt §6):
    logout revokes the session row but keeps the stored refresh token so
    the next sign-in can reuse the Google authorization without a new
    consent screen (documented in ADR-0020).
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # SHA-256 hex of the opaque cookie token. The raw token is never stored.
    session_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stored only as diagnostic context, never for identification.
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OAuthToken(Base):
    """Google OAuth credentials of one local user, encrypted at rest.

    One row per user (PK = user_id): a Google account has exactly one
    live grant in this application. access_token/refresh_token are Fernet
    ciphertext (token_crypto.py); the encryption key lives in the
    environment, never in the database (migration prompt §8).
    """

    __tablename__ = "oauth_tokens"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Naive UTC, like Credentials.expiry and every other timestamp this
    # backend compares in Python.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class OAuthLoginState(Base):
    """Server-side state of one pending OAuth login attempt.

    The state parameter is generated per attempt, stored server-side
    (migration prompt §5) and single-use: the callback must find the row,
    match the browser nonce cookie bound at /auth/login, and the row is
    deleted before the code exchange. code_verifier implements PKCE S256
    on top of the client secret.
    """

    __tablename__ = "oauth_login_states"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Bound to the initiating browser via a short-lived cookie; prevents
    # one browser's login from completing into another's session.
    browser_nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    # Same-origin relative path to return to after login (validated).
    redirect_to: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
