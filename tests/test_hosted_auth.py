# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Hosted web OAuth + sessions (migration stage 2, ADR-0020).

The Google network boundary is mocked at the two seams hosted_auth exposes
(the authorization-code exchange and the userinfo lookup); everything else
— state/PKCE/nonce validation, user upsert, token encryption, session
cookie, gate, logout — runs as shipped.
"""

import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import desktop as auth_module
from auth import hosted
from core import crypto
from db.models.accounts import OAuthLoginState, OAuthToken, User, UserSession
from gapi import credentials, oauth_transport

REDIRECT = "https://gch.test/api/auth/callback"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _count(db: Session, entity) -> int:
    """Row count in the SQLAlchemy 2.0 builder style (no raw SQL)."""
    return db.scalar(select(func.count()).select_from(entity)) or 0


@pytest.fixture()
def fake_google(monkeypatch):
    """Canned Google answers: token endpoint + userinfo, no network."""

    def fake_post_token_request(client_config, code, redirect_uri, code_verifier):
        assert redirect_uri == REDIRECT
        assert code == "good-code"
        # The PKCE verifier stored with the login state must be sent along.
        assert code_verifier
        return {
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "expires_in": 3600,
        }

    identity = {"sub": "google-sub-1", "email": "alice@example.com", "name": "Alice"}

    # Stage 8 (В§32): the transport lives in oauth_transport — patch the
    # module the production code actually calls, not the desktop re-export.
    monkeypatch.setattr(oauth_transport, "post_token_request", fake_post_token_request)
    monkeypatch.setattr(hosted, "_fetch_identity", lambda token: dict(identity))
    return identity


def _start_login(client) -> str:
    """GET /auth/login (no redirect follow); returns the OAuth state."""
    response = client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    params = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    return params["state"][0]


def _finish_login(client, state: str, code: str = "good-code"):
    return client.get(
        f"/api/auth/callback?state={urllib.parse.quote(state)}&code={code}",
        follow_redirects=False,
    )


# ------------------------------------------------------------------ the gate


def test_data_endpoints_require_a_session(hosted_client):
    assert hosted_client.get("/api/courses").status_code == 401
    assert hosted_client.get("/api/status").status_code == 401
    assert hosted_client.get("/api/health").status_code == 200


def test_hosted_login_is_a_redirect_not_the_desktop_loopback(hosted_client):
    # The desktop POST /auth/login must not be reachable in hosted mode.
    assert hosted_client.post("/api/auth/login").status_code == 405


# ------------------------------------------------------------- login start


def test_login_redirect_carries_state_pkce_and_binds_the_browser(
    hosted_client, db: Session
):
    response = hosted_client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    params = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == [REDIRECT]
    assert params["code_challenge_method"] == ["S256"]
    assert params["access_type"] == ["offline"]
    requested_scopes = set(params["scope"][0].split())
    assert requested_scopes == set(oauth_transport.SCOPES)
    # Identity scopes are required for the OIDC userinfo lookup; Classroom
    # scopes remain read-only and are what the application uses for data.
    assert {"openid", "profile", "email"}.issubset(requested_scopes)
    assert (
        "https://www.googleapis.com/auth/classroom.courses.readonly" in requested_scopes
    )
    # State and nonce are independent random values, stored server-side.
    set_cookie = response.headers["set-cookie"]
    assert "gch_oauth_nonce=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    row = db.scalars(select(OAuthLoginState)).one()
    assert row.state == params["state"][0]
    assert row.browser_nonce in set_cookie
    assert row.code_verifier
    assert row.redirect_to == "/"
    assert row.expires_at > _now()


def test_login_rejects_a_foreign_redirect_target(hosted_client, db: Session):
    hosted_client.get(
        "/api/auth/login?redirect_to=https://evil.example/steal",
        follow_redirects=False,
    )
    assert db.scalars(select(OAuthLoginState)).one().redirect_to == "/"


# ---------------------------------------------------------------- callback


def test_callback_rejects_unknown_state(hosted_client, db: Session):
    response = hosted_client.get(
        "/api/auth/callback?state=nope&code=good-code", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/?login_error=400"
    assert _count(db, User) == 0
    assert _count(db, UserSession) == 0


def test_callback_rejects_a_nonce_from_another_browser(hosted_client, db: Session):
    state = _start_login(hosted_client)
    # Replace the nonce cookie with a foreign value: the attempt must not
    # complete even though the state exists server-side.
    hosted_client.cookies.set("gch_oauth_nonce", "foreign-nonce")
    response = _finish_login(hosted_client, state)
    assert response.headers["location"] == "/?login_error=400"
    # Single use: the first presentation of a state consumes the attempt.
    assert _count(db, OAuthLoginState) == 0
    assert _count(db, User) == 0


def test_callback_rejects_a_missing_code(hosted_client, db: Session):
    state = _start_login(hosted_client)
    response = hosted_client.get(
        f"/api/auth/callback?state={state}", follow_redirects=False
    )
    assert response.headers["location"] == "/?login_error=400"
    assert _count(db, User) == 0


def test_full_login_creates_user_session_and_encrypted_tokens(
    hosted_client, fake_google, db: Session
):
    state = _start_login(hosted_client)
    response = _finish_login(hosted_client, state)

    assert response.status_code == 302
    assert response.headers["location"] == "/"
    set_cookie = response.headers["set-cookie"]
    assert "gch_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    # HTTPS deployment (Caddy in production) в†’ Secure cookie.
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    # The one-time nonce is cleared.
    assert "gch_oauth_nonce=" in set_cookie

    user = db.scalars(select(User)).one()
    assert user.provider == "google"
    assert user.provider_subject == "google-sub-1"
    assert user.email == "alice@example.com"
    assert user.display_name == "Alice"
    assert user.last_login_at is not None

    token = db.scalars(select(OAuthToken)).one()
    assert token.user_id == user.id
    # Tokens are encrypted at rest, never plaintext (В§8).
    assert token.access_token.startswith("enc.v1:")
    assert "at-123" not in token.access_token
    assert crypto.decrypt(token.access_token) == "at-123"
    assert token.refresh_token is not None
    assert crypto.decrypt(token.refresh_token) == "rt-456"
    assert set(auth_module.SCOPES).issubset(set(token.scopes))

    session = db.scalars(select(UserSession)).one()
    raw_cookie = next(
        value
        for value in hosted_client.cookies.values()
        if len(value) >= 40 and not value.startswith("foreign")
    )
    # Only the hash is stored; the raw cookie token never reaches the DB.
    assert session.session_token_hash != raw_cookie
    assert session.session_token_hash == hosted._sha256_hex(raw_cookie)
    assert session.revoked_at is None

    # Status resolves from the session and the users table (no Google call).
    status = hosted_client.get("/api/auth/status")
    assert status.status_code == 200
    body = status.json()
    assert body["authenticated"] is True
    # В§26: identity is nested, never flat and never a token.
    assert body["user"]["name"] == "Alice"
    assert body["user"]["email"] == "alice@example.com"
    assert "user_name" not in body and "user_email" not in body
    assert "at-123" not in status.text and "rt-456" not in status.text

    # The session gate now lets data endpoints through.
    assert hosted_client.get("/api/courses").status_code == 200


def test_login_state_is_single_use(hosted_client, fake_google, db: Session):
    state = _start_login(hosted_client)
    assert _finish_login(hosted_client, state).headers["location"] == "/"
    replay = _finish_login(hosted_client, state)
    assert replay.headers["location"] == "/?login_error=400"
    assert _count(db, User) == 1
    assert _count(db, UserSession) == 1


def test_returning_login_reuses_the_user_and_a_second_browser_adds_a_session(
    hosted_client, fake_google, db: Session
):
    for _ in range(2):
        state = _start_login(hosted_client)
        assert _finish_login(hosted_client, state).headers["location"] == "/"
    assert _count(db, User) == 1
    assert _count(db, UserSession) == 2


def test_changed_email_updates_the_same_user(
    hosted_client, fake_google, monkeypatch, db: Session
):
    state = _start_login(hosted_client)
    _finish_login(hosted_client, state)

    monkeypatch.setattr(
        hosted,
        "_fetch_identity",
        lambda token: {
            "sub": "google-sub-1",
            "email": "alice.new@example.com",
            "name": "Alice",
        },
    )
    state = _start_login(hosted_client)
    _finish_login(hosted_client, state)

    assert _count(db, User) == 1
    assert db.scalars(select(User)).one().email == "alice.new@example.com"


def test_deactivated_user_cannot_use_an_existing_session(
    hosted_client, fake_google, db: Session
):
    state = _start_login(hosted_client)
    _finish_login(hosted_client, state)
    user = db.scalars(select(User)).one()
    user.is_active = False
    db.commit()
    assert hosted_client.get("/api/auth/status").status_code == 401
    assert hosted_client.get("/api/courses").status_code == 401


# ----------------------------------------------------------------- logout


def test_logout_revokes_the_session_but_keeps_the_google_grant(
    hosted_client, fake_google, db: Session
):
    state = _start_login(hosted_client)
    _finish_login(hosted_client, state)

    response = hosted_client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "gch_session=" in response.headers["set-cookie"]

    assert hosted_client.get("/api/auth/status").status_code == 401
    assert hosted_client.get("/api/courses").status_code == 401
    # Session revoked, refresh token retained (ADR-0020).
    assert db.scalars(select(UserSession)).one().revoked_at is not None
    assert _count(db, OAuthToken) == 1


# ----------------------------------------------------- credentials by user


def _make_user_with_token(
    db: Session, *, expires_at, refresh_token="rt-old", scopes=None
):
    now = _now()
    user = User(
        provider="google",
        provider_subject="sub-refresh",
        email="r@example.com",
        display_name="R",
        created_at=now,
        updated_at=now,
        last_login_at=now,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        OAuthToken(
            user_id=user.id,
            access_token=crypto.encrypt("at-old"),
            refresh_token=crypto.encrypt(refresh_token)
            if refresh_token
            else None,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=list(scopes if scopes is not None else auth_module.SCOPES),
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    return user


def test_expired_token_is_refreshed_and_persisted_encrypted(db: Session, monkeypatch):
    user = _make_user_with_token(db, expires_at=_now() - timedelta(minutes=1))

    def fake_refresh(creds):
        creds.token = "at-new"
        creds.expiry = _now() + timedelta(hours=1)

    monkeypatch.setattr(oauth_transport, "refresh_credentials", fake_refresh)

    creds = credentials.get_google_credentials(db, user)
    assert creds is not None
    assert creds.token == "at-new"
    row = db.get(OAuthToken, user.id)
    assert row is not None
    assert row.expires_at is not None
    assert crypto.decrypt(row.access_token) == "at-new"
    assert row.expires_at > _now()


def test_failed_refresh_reports_signed_out(db: Session, monkeypatch):
    user = _make_user_with_token(db, expires_at=_now() - timedelta(minutes=1))

    def boom(creds):
        raise RuntimeError("invalid_grant")

    monkeypatch.setattr(oauth_transport, "refresh_credentials", boom)
    assert credentials.get_google_credentials(db, user) is None


def test_stale_scope_set_forces_a_new_consent(db: Session):
    user = _make_user_with_token(
        db, expires_at=_now() + timedelta(hours=1), scopes=["openid"]
    )
    assert credentials.get_google_credentials(db, user) is None
    # The unusable row is dropped so the next login re-consents.
    assert db.get(OAuthToken, user.id) is None


def test_valid_token_is_returned_without_a_refresh(db: Session, monkeypatch):
    user = _make_user_with_token(db, expires_at=_now() + timedelta(hours=1))

    def unexpected(creds):  # pragma: no cover - must never run
        raise AssertionError("a valid token must not be refreshed")

    monkeypatch.setattr(oauth_transport, "refresh_credentials", unexpected)
    creds = credentials.get_google_credentials(db, user)
    assert creds is not None and creds.token == "at-old"


# ------------------------------------------------------------------ crypto


def test_token_crypto_roundtrip_and_plaintext_rejection(monkeypatch):
    ciphertext = crypto.encrypt("secret-value")
    assert ciphertext.startswith("enc.v1:")
    assert "secret-value" not in ciphertext
    assert crypto.decrypt(ciphertext) == "secret-value"
    with pytest.raises(crypto.TokenEncryptionError):
        crypto.decrypt("plaintext-value")
    # A wrong key must not silently decrypt garbage.
    from cryptography.fernet import Fernet

    monkeypatch.setenv(crypto.KEY_ENV_VAR, Fernet.generate_key().decode("ascii"))
    with pytest.raises(crypto.TokenEncryptionError):
        crypto.decrypt(ciphertext)


def test_safe_relative_only_allows_same_origin_paths():
    assert hosted._safe_relative("/subjects/1") == "/subjects/1"
    assert hosted._safe_relative("//evil.example") == "/"
    assert hosted._safe_relative("https://evil.example/x") == "/"
    assert hosted._safe_relative("/a\\b") == "/"
    assert hosted._safe_relative("/a\nb") == "/"
