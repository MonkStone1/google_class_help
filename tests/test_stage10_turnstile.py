# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Turnstile guard for login initiation (DDoS plan §17; stage 10 deferred item).

Both keys empty (the default) → the flow is exactly the stage-2 one. Keys
configured → the direct GET bypass is closed, POST /api/auth/login/start
verifies the widget token fail-closed, and the CSP gains the widget origin
for scripts and frames only.
"""

from __future__ import annotations

import hosted_auth
import main
from models_auth import OAuthLoginState


def _enable_turnstile(monkeypatch, site_key="test-site-key", secret="test-secret"):
    monkeypatch.setattr(hosted_auth, "TURNSTILE_SITE_KEY", site_key)
    monkeypatch.setattr(hosted_auth, "TURNSTILE_SECRET_KEY", secret)


def test_turnstile_is_disabled_by_default(hosted_client):
    response = hosted_client.get("/api/auth/turnstile")
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "site_key": None}


def test_login_start_without_turnstile_needs_no_token(hosted_client, db):
    response = hosted_client.post("/api/auth/login/start", json={})
    assert response.status_code == 200
    assert "accounts.google.com" in response.json()["redirect_url"]
    assert db.query(OAuthLoginState).count() == 1


def test_direct_login_redirects_to_google_when_turnstile_is_off(hosted_client):
    response = hosted_client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 302
    assert "accounts.google.com" in response.headers["location"]


def test_turnstile_config_reports_site_key_when_enabled(monkeypatch, hosted_client):
    _enable_turnstile(monkeypatch)
    body = hosted_client.get("/api/auth/turnstile").json()
    assert body == {"enabled": True, "site_key": "test-site-key"}


def test_direct_login_bypass_is_closed_when_turnstile_is_enabled(
    monkeypatch, hosted_client
):
    """§17: GET /api/auth/login must not skip the challenge."""
    _enable_turnstile(monkeypatch)
    response = hosted_client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("/?challenge=required")
    assert "accounts.google.com" not in location


def test_login_start_without_token_is_rejected_when_enabled(
    monkeypatch, hosted_client, db
):
    _enable_turnstile(monkeypatch)
    before = db.query(OAuthLoginState).count()
    response = hosted_client.post("/api/auth/login/start", json={})
    assert response.status_code == 403
    assert "challenge" in response.json()["detail"].lower()
    assert db.query(OAuthLoginState).count() == before


def test_login_start_with_valid_token_builds_the_google_redirect(
    monkeypatch, hosted_client, db
):
    _enable_turnstile(monkeypatch)
    seen: list[str] = []
    monkeypatch.setattr(
        hosted_auth, "_verify_turnstile", lambda token: seen.append(token) or True
    )
    response = hosted_client.post(
        "/api/auth/login/start", json={"token": "widget-token"}
    )
    assert response.status_code == 200
    assert "accounts.google.com" in response.json()["redirect_url"]
    assert seen == ["widget-token"]
    assert db.query(OAuthLoginState).count() == 1
    # The browser binding travels with the response (nonce cookie).
    assert hosted_auth.NONCE_COOKIE_NAME in response.cookies


def test_login_start_with_failed_verification_is_rejected(
    monkeypatch, hosted_client, db
):
    _enable_turnstile(monkeypatch)
    before = db.query(OAuthLoginState).count()
    monkeypatch.setattr(hosted_auth, "_verify_turnstile", lambda token: False)
    response = hosted_client.post(
        "/api/auth/login/start", json={"token": "forged-token"}
    )
    assert response.status_code == 403
    assert db.query(OAuthLoginState).count() == before


def test_verify_turnstile_fails_closed_when_siteverify_is_unreachable(
    monkeypatch, hosted_client
):
    """Any transport/parse problem = rejection (no fail-open)."""
    _enable_turnstile(monkeypatch)

    class _BrokenHttp:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            raise RuntimeError("network down")

    monkeypatch.setattr(hosted_auth.httplib2, "Http", _BrokenHttp)
    assert hosted_auth._verify_turnstile("token") is False


def test_csp_is_same_origin_without_turnstile():
    csp = main._build_content_security_policy("")
    assert "script-src 'self';" in csp
    assert "challenges.cloudflare.com" not in csp
    assert "frame-src" not in csp


def test_csp_adds_only_the_turnstile_origin_when_configured():
    csp = main._build_content_security_policy("test-site-key")
    assert "script-src 'self' https://challenges.cloudflare.com;" in csp
    assert "frame-src 'self' https://challenges.cloudflare.com;" in csp
    # No accidental loosening of the other directives.
    assert "'unsafe-inline'" in csp  # style-src only
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "connect-src 'self';" in csp
