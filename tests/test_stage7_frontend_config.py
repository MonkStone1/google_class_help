# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Stage 7 configuration and browser-boundary tests (§26-§31, §51).

These tests pin the environment-driven decisions that keep the hosted service
on one public origin: exact Host/Origin matching, a credentialed CORS list
without a wildcard, forwarded headers honoured only from configured proxies,
cookie flags, the Linux/container data path, and the 401/login boundary.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.requests import Request

import config
import hosted_auth
import main
import path_config
import proxy

PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_DIR / "backend"


def _request(
    *,
    host: str = "gch.test",
    scheme: str = "https",
    client: tuple[str, int] | None = ("203.0.113.7", 40000),
    headers: dict[str, str] | None = None,
) -> Request:
    """Build a minimal Starlette request without a running server."""
    raw_headers = [(b"host", host.encode("ascii"))]
    for name, value in (headers or {}).items():
        raw_headers.append((name.encode("ascii"), value.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": scheme,
            "server": ("internal", 8000),
            "client": client,
            "path": "/api/health",
            "query_string": b"",
            "headers": raw_headers,
        }
    )


def _new_client(host: str = "api.example") -> TestClient:
    return TestClient(main.create_app(hosted=False), base_url=f"https://{host}")


# ------------------------------------------------------- environment layer


class TestEnvironmentLayer:
    def test_production_defaults_to_the_public_host_only(self, monkeypatch):
        monkeypatch.setattr(config, "IS_PRODUCTION", True)
        monkeypatch.setattr(config, "APP_ORIGIN", "https://monkstonecor.pp.ua")
        assert config._default_allowed_hosts() == ["monkstonecor.pp.ua"]

    def test_development_defaults_keep_loopback(self, monkeypatch):
        monkeypatch.setattr(config, "IS_PRODUCTION", False)
        monkeypatch.setattr(config, "APP_ORIGIN", "https://dev.example")
        assert config._default_allowed_hosts() == [
            "dev.example",
            "localhost",
            "127.0.0.1",
        ]

    def test_wildcard_cors_is_dropped_and_origins_are_normalized(self):
        assert config._normalize_origins(["*"]) == ()
        assert config._normalize_origins(
            ["*", "HTTP://Trusted.Example:80/", "https://trusted.example:443"]
        ) == ("http://trusted.example", "https://trusted.example")

    def test_invalid_boolean_is_unset_not_false(self, monkeypatch):
        monkeypatch.setenv("STAGE7_BOOL", "maybe")
        assert config._bool_env("STAGE7_BOOL") is None
        monkeypatch.setenv("STAGE7_BOOL", "off")
        assert config._bool_env("STAGE7_BOOL") is False

    def test_samesite_none_forces_secure_cookie(self, tmp_path):
        env = os.environ.copy()
        env.update(
            {
                "APP_ENV": "production",
                "APP_BASE_URL": "https://environ.example",
                "GC_DASHBOARD_DATA_DIR": str(tmp_path),
                "GC_DASHBOARD_HOSTED": "0",
                "COOKIE_SECURE": "false",
                "COOKIE_SAMESITE": "none",
            }
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json, config; "
                    "print(json.dumps({'secure': config.COOKIE_SECURE, "
                    "'samesite': config.COOKIE_SAMESITE}))"
                ),
            ],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        assert payload == {"secure": True, "samesite": "none"}

    def test_production_env_derives_public_origin_and_redirect(self, tmp_path):
        env = os.environ.copy()
        env.update(
            {
                "APP_ENV": "production",
                "APP_BASE_URL": "https://environ.example",
                "GC_DASHBOARD_DATA_DIR": str(tmp_path),
                "GC_DASHBOARD_HOSTED": "0",
            }
        )
        env.pop("GC_DASHBOARD_ALLOWED_HOSTS", None)
        env.pop("GC_DASHBOARD_CORS_ORIGINS", None)
        env.pop("GOOGLE_REDIRECT_URI", None)
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json, config; "
                    "print(json.dumps({"
                    "'allowed': list(config.ALLOWED_HOSTS), "
                    "'cors': list(config.CORS_ORIGINS), "
                    "'origin': config.APP_ORIGIN, "
                    "'redirect': config.GOOGLE_REDIRECT_URI"
                    "}))"
                ),
            ],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        assert payload["allowed"] == ["environ.example"]
        assert payload["cors"] == []
        assert payload["origin"] == "https://environ.example"
        assert payload["redirect"] == "https://environ.example/api/auth/callback"


# ----------------------------------------------------- Host / Origin guard


class TestHostAndOriginGuard:
    def test_host_allowed_ignores_port_and_case(self, monkeypatch):
        monkeypatch.setattr(main, "ALLOWED_HOSTS", ("gch.test", "127.0.0.1"))
        assert main._host_allowed("GCH.test:443") is True
        assert main._host_allowed("127.0.0.1:8000") is True
        assert main._host_allowed("evil.test") is False
        assert main._host_allowed("gch.test:not-a-port") is False
        assert main._host_allowed("gch.test, evil.test") is False
        assert main._host_allowed("") is False

    def test_origin_requires_exact_scheme_and_port(self, monkeypatch):
        monkeypatch.setattr(main, "CORS_ORIGINS", ())
        monkeypatch.setattr(main, "APP_ORIGIN", "https://gch.test")
        monkeypatch.setattr(main, "IS_PRODUCTION", True)
        request = _request()
        assert main._origin_allowed("https://gch.test", request) is True
        assert main._origin_allowed("https://gch.test:443", request) is True
        assert main._origin_allowed("http://gch.test", request) is False
        assert main._origin_allowed("https://gch.test:8443", request) is False
        assert main._origin_allowed("https://gch.test.evil", request) is False
        assert main._origin_allowed("null", request) is False
        assert main._origin_allowed("https://gch.test/path", request) is False

    def test_production_rejects_localhost_without_explicit_cors(self, monkeypatch):
        monkeypatch.setattr(main, "APP_ORIGIN", "https://gch.test")
        monkeypatch.setattr(main, "IS_PRODUCTION", True)
        monkeypatch.setattr(main, "CORS_ORIGINS", ())
        assert main._origin_allowed("http://localhost:5173", _request()) is False
        monkeypatch.setattr(main, "CORS_ORIGINS", ("http://localhost:5173",))
        assert main._origin_allowed("http://localhost:5173", _request()) is True

    def test_development_keeps_the_vite_origins(self, monkeypatch):
        monkeypatch.setattr(main, "IS_PRODUCTION", False)
        monkeypatch.setattr(main, "CORS_ORIGINS", ())
        monkeypatch.setattr(main, "FRONTEND_ORIGINS", ("http://localhost:5173",))
        assert main._origin_allowed("http://localhost:5173", _request()) is True

    def test_cross_origin_preflight_uses_the_exact_configured_origin(self, monkeypatch):
        monkeypatch.setattr(main, "ALLOWED_HOSTS", ("api.example",))
        monkeypatch.setattr(main, "CORS_ORIGINS", ("https://frontend.example",))
        client = _new_client()
        try:
            response = client.options(
                "/api/health",
                headers={
                    "Origin": "https://frontend.example",
                    "Access-Control-Request-Method": "GET",
                    "Host": "api.example",
                },
            )
        finally:
            client.close()
        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"]
            == "https://frontend.example"
        )
        assert response.headers["access-control-allow-credentials"] == "true"

    def test_foreign_host_preflight_is_rejected_before_cors(self, monkeypatch):
        monkeypatch.setattr(main, "ALLOWED_HOSTS", ("api.example",))
        monkeypatch.setattr(main, "CORS_ORIGINS", ("https://frontend.example",))
        client = _new_client()
        try:
            response = client.options(
                "/api/health",
                headers={
                    "Origin": "https://frontend.example",
                    "Access-Control-Request-Method": "GET",
                    "Host": "evil.example",
                },
            )
        finally:
            client.close()
        assert response.status_code == 403

    def test_foreign_origin_is_rejected_before_cors(self, monkeypatch):
        monkeypatch.setattr(main, "ALLOWED_HOSTS", ("api.example",))
        monkeypatch.setattr(main, "CORS_ORIGINS", ("https://frontend.example",))
        client = _new_client()
        try:
            response = client.options(
                "/api/health",
                headers={
                    "Origin": "https://evil.example",
                    "Access-Control-Request-Method": "GET",
                    "Host": "api.example",
                },
            )
        finally:
            client.close()
        assert response.status_code == 403

    def test_same_origin_request_needs_no_cors_entry(self, monkeypatch):
        monkeypatch.setattr(main, "ALLOWED_HOSTS", ("api.example",))
        monkeypatch.setattr(main, "CORS_ORIGINS", ())
        monkeypatch.setattr(main, "APP_ORIGIN", "https://api.example")
        monkeypatch.setattr(main, "IS_PRODUCTION", True)
        client = _new_client()
        try:
            response = client.get(
                "/api/health",
                headers={"Origin": "https://api.example", "Host": "api.example"},
            )
        finally:
            client.close()
        assert response.status_code == 200


# --------------------------------------------------------- trusted proxy


class TestTrustedProxy:
    def test_untrusted_forwarded_headers_are_ignored(self, monkeypatch):
        monkeypatch.setattr(proxy, "TRUSTED_PROXIES", ())
        request = _request(
            scheme="http",
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "gch.test",
            },
        )
        assert proxy.external_scheme(request) == "http"
        assert proxy.effective_authority(request) == ("gch.test", None)
        assert proxy.public_origin(request) == "http://gch.test"

    def test_trusted_proxy_controls_scheme_and_host(self, monkeypatch):
        monkeypatch.setattr(proxy, "TRUSTED_PROXIES", ("203.0.113.0/24",))
        monkeypatch.setattr(proxy, "ALLOWED_HOSTS", ("gch.test",))
        request = _request(
            scheme="http",
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "gch.test",
            },
        )
        assert proxy.external_scheme(request) == "https"
        assert proxy.public_origin(request) == "https://gch.test"

    def test_disallowed_forwarded_host_fails_closed(self, monkeypatch):
        monkeypatch.setattr(proxy, "TRUSTED_PROXIES", ("203.0.113.7",))
        monkeypatch.setattr(proxy, "ALLOWED_HOSTS", ("gch.test",))
        request = _request(headers={"x-forwarded-host": "evil.test"})
        assert proxy.effective_authority(request) is None

    def test_malformed_proxy_entries_are_ignored(self, monkeypatch):
        monkeypatch.setattr(proxy, "TRUSTED_PROXIES", ("not-an-ip", "203.0.113.7"))
        assert proxy.peer_is_trusted_proxy(_request(client=("203.0.113.7", 1)))
        assert not proxy.peer_is_trusted_proxy(_request(client=("198.51.100.9", 1)))


# ------------------------------------------------------------ cookie flags


class TestCookieFlags:
    def test_explicit_cookie_secure_wins(self, monkeypatch):
        monkeypatch.setattr(hosted_auth, "COOKIE_SECURE", False)
        assert hosted_auth._session_cookie_secure(_request(scheme="https")) is False
        monkeypatch.setattr(hosted_auth, "COOKIE_SECURE", True)
        assert hosted_auth._session_cookie_secure(_request(scheme="http")) is True

    def test_cookie_secure_trusts_only_a_configured_proxy(self, monkeypatch):
        monkeypatch.setattr(hosted_auth, "COOKIE_SECURE", None)
        monkeypatch.setattr(proxy, "TRUSTED_PROXIES", ())
        assert (
            hosted_auth._session_cookie_secure(
                _request(scheme="http", headers={"x-forwarded-proto": "https"})
            )
            is False
        )
        monkeypatch.setattr(proxy, "TRUSTED_PROXIES", ("203.0.113.0/24",))
        assert (
            hosted_auth._session_cookie_secure(
                _request(scheme="http", headers={"x-forwarded-proto": "https"})
            )
            is True
        )


# --------------------------------------------------------- hosted data path


class TestHostedDataPath:
    def test_explicit_override_wins_over_every_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GC_DASHBOARD_DATA_DIR", str(tmp_path / "override"))
        monkeypatch.setattr(path_config, "HOSTED_MODE", True)
        monkeypatch.setattr(path_config, "IS_FROZEN", True)
        assert path_config._resolve_data_dir() == tmp_path / "override"

    def test_hosted_posix_uses_the_data_volume(self, monkeypatch):
        monkeypatch.delenv("GC_DASHBOARD_DATA_DIR", raising=False)
        monkeypatch.setattr(path_config, "HOSTED_MODE", True)
        monkeypatch.setattr(path_config, "IS_FROZEN", False)
        monkeypatch.setattr(path_config.os, "name", "posix")
        assert path_config._resolve_data_dir() == path_config.HOSTED_DATA_DIR

    def test_compiled_desktop_uses_localappdata(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GC_DASHBOARD_DATA_DIR", raising=False)
        monkeypatch.setattr(path_config, "HOSTED_MODE", False)
        monkeypatch.setattr(path_config, "IS_FROZEN", True)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
        assert path_config._resolve_data_dir() == tmp_path / "Local" / "GoogleClassHelp"


# ------------------------------------------------------ browser boundary


def test_hosted_unauthenticated_requests_return_401(hosted_client):
    assert hosted_client.get("/api/courses").status_code == 401
    assert hosted_client.get("/api/status").status_code == 401


def test_hosted_login_is_a_redirect_not_a_loopback_post(hosted_client):
    assert hosted_client.post("/api/auth/login").status_code == 405
    redirect = hosted_client.get("/api/auth/login", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"].startswith("https://accounts.google.com/")
