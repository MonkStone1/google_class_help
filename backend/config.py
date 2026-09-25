"""Application paths and configuration.

All path resolution lives in path_config.py (RESOURCE_DIR vs DATA_DIR,
development vs compiled build). Secrets (OAuth client credentials, tokens)
are kept outside the source code: they live in files that are git-ignored
and can be relocated with environment variables.
"""

import logging
import os
import urllib.parse
from pathlib import Path
from typing import Literal

from path_config import DATA_DIR, PROJECT_DIR, ensure_data_dirs

logger = logging.getLogger(__name__)

ensure_data_dirs()

# User-writable OAuth token. In production: %LOCALAPPDATA%\GoogleClassHelp\token.json
TOKEN_FILE = Path(os.environ.get("GC_DASHBOARD_TOKEN", DATA_DIR / "token.json"))
DATABASE_FILE = DATA_DIR / "classroom.db"

# Development-only fallback: the visible credentials.json in the project
# tree. In production builds the client config is embedded (see
# build_secrets.py / auth.py) and this file is not distributed.
CREDENTIALS_FILE = Path(
    os.environ.get(
        "GC_DASHBOARD_CREDENTIALS", PROJECT_DIR / "backend" / "credentials.json"
    )
)


# Sync concurrency. Classroom API quotas: 1200 queries/min per user (~20 QPS)
# and 3000/min per client. 16 workers keeps a typical sync under the per-user
# quota while still saturating network latency; raise via env only together
# with quota monitoring (429s are retried with exponential backoff).
def _int_env(name: str, default: int, *, minimum: int = 0) -> int:
    """Read a non-negative integer env var; invalid values fall back."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _bool_env(name: str) -> bool | None:
    """Read a tri-state boolean env var; unset/invalid means "not set"."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    logger.warning("Ignoring invalid boolean value %r for %s.", raw, name)
    return None


def _csv_env(name: str) -> list[str]:
    """Read a comma-separated list env var (empty items dropped)."""
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def canonical_origin(scheme: str, hostname: str, port: int | None) -> str | None:
    """Return a normalized ``scheme://host[:port]`` origin.

    Invalid schemes/hosts and non-default ports that cannot be represented are
    rejected. Default ports are omitted so ``https://host:443`` and
    ``https://host`` compare equal.
    """
    scheme = scheme.strip().lower()
    hostname = hostname.strip().lower().rstrip(".")
    if scheme not in {"http", "https"} or not hostname:
        return None
    try:
        normalized_port = int(port) if port is not None else None
    except (TypeError, ValueError):
        return None
    if normalized_port is not None and not 1 <= normalized_port <= 65535:
        return None
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if normalized_port is not None and not (
        (scheme == "http" and normalized_port == 80)
        or (scheme == "https" and normalized_port == 443)
    ):
        hostname = f"{hostname}:{normalized_port}"
    return f"{scheme}://{hostname}"


def _origin_from_value(value: str) -> str | None:
    """Normalize an origin value, rejecting paths, credentials and fragments."""
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return canonical_origin(parsed.scheme, parsed.hostname, port)


def _host_from_value(value: str) -> str | None:
    """Normalize a host or URL authority to a hostname only."""
    authority = host_and_port_from_value(value)
    return authority[0] if authority is not None else None


def host_and_port_from_value(value: str) -> tuple[str, int | None] | None:
    """Return a normalized ``(host, port)`` authority.

    This is shared by the Host guard and trusted-proxy handling so both use
    the same IPv6, port and malformed-input rules.
    """
    raw = value.strip()
    if not raw or any(character in raw for character in (",", "\r", "\n")):
        return None
    try:
        if "://" in raw:
            parsed = urllib.parse.urlsplit(raw)
            if parsed.path or parsed.query or parsed.fragment:
                return None
        else:
            parsed = urllib.parse.urlsplit(f"//{raw}")
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    if port is not None and not 1 <= port <= 65535:
        return None
    return parsed.hostname.strip().lower().rstrip("."), port


def normalize_host(value: str) -> str | None:
    """Public host-normalization helper used by middleware and tests."""
    authority = host_and_port_from_value(value)
    return authority[0] if authority is not None else None


def normalize_origin(value: str) -> str | None:
    """Public origin-normalization helper used by middleware and tests."""
    return _origin_from_value(value)


def _normalize_origins(values: list[str]) -> tuple[str, ...]:
    """Normalize an origin allow-list and remove the credentialed wildcard."""
    normalized: list[str] = []
    wildcard = False
    for value in values:
        if value == "*":
            wildcard = True
            continue
        origin = _origin_from_value(value)
        if origin is not None:
            normalized.append(origin)
    if wildcard:
        logger.warning(
            "An origin allow-list contained '*'; ignoring it — a wildcard "
            "origin is never combined with credentialed cookies (§27)."
        )
    return tuple(dict.fromkeys(normalized))


# Stage-9 hosted Postgres pool (section 45/88): small on purpose. Sync no
# longer holds a connection across the Google fetch, so a handful covers
# web requests plus the bounded scheduler on the 1 vCPU / 1 GB target.
DB_POOL_SIZE = _int_env("GC_DASHBOARD_DB_POOL_SIZE", 5, minimum=1)
DB_MAX_OVERFLOW = _int_env("GC_DASHBOARD_DB_MAX_OVERFLOW", 5, minimum=0)


# Stage-9 knobs (ADR-0027): abuse controls and the manual-sync cooldown.
# Login/callback buckets are per IP; the callback bucket counts REJECTED
# attempts only, so a classroom behind one school NAT can still sign in.
RATE_LIMIT_LOGIN_PER_MINUTE = _int_env(
    "GC_DASHBOARD_RATE_LIMIT_LOGIN_PER_MINUTE", 30, minimum=1
)
RATE_LIMIT_CALLBACK_FAILURES_PER_MINUTE = _int_env(
    "GC_DASHBOARD_RATE_LIMIT_CALLBACK_FAILURES_PER_MINUTE", 20, minimum=1
)
# Manual sync (section 39): per-IP bucket plus a per-user cooldown below.
RATE_LIMIT_SYNC_PER_MINUTE = _int_env(
    "GC_DASHBOARD_RATE_LIMIT_SYNC_PER_MINUTE", 60, minimum=1
)
# Destructive cache clears (sections 44/66): rare operator action.
RATE_LIMIT_CACHE_CLEAR_PER_MINUTE = _int_env(
    "GC_DASHBOARD_RATE_LIMIT_CACHE_CLEAR_PER_MINUTE", 10, minimum=1
)
# Per-user manual-sync cooldown, seconds (section 39): pressing Sync twice
# reuses the in-flight run (409) or gets 429 instead of a second fan-out.
# The scheduler is NOT throttled by this - planned syncs bypass it.
SYNC_MANUAL_COOLDOWN_SECONDS = _int_env(
    "GC_DASHBOARD_SYNC_MANUAL_COOLDOWN_SECONDS", 60, minimum=0
)

# Retention sweep cadence, seconds (stage 9, section 44): expired/revoked
# sessions and expired OAuth login attempts are removed by the worker at
# most this often. 0 disables the sweep (tests).
RETENTION_SWEEP_SECONDS = _int_env(
    "GC_DASHBOARD_RETENTION_SWEEP_SECONDS", 3600, minimum=0
)


SYNC_MAX_WORKERS = _int_env("GC_DASHBOARD_SYNC_WORKERS", 4, minimum=1)

# Background sync: runs once at startup, then every SYNC_INTERVAL_MINUTES.
# 0 disables the schedule entirely (no startup sync, no repeats).
SYNC_INTERVAL_MINUTES = _int_env("GC_DASHBOARD_SYNC_INTERVAL_MINUTES", 10)


# ------------------------------------------------- per-user sync (stage 5)
#
# The scheduler picks users up individually instead of running one global
# loop (migration prompt §18/§19). These knobs bound the work it may create:
#
# - SYNC_MAX_CONCURRENT_USERS: how many users may sync at the same time
#   across the whole worker. Each user's sync uses SYNC_MAX_WORKERS threads,
#   so the total thread budget is the product of the two (and the Google
#   per-project quota budget is shared by all of them).
# - SYNC_SCAN_INTERVAL_SECONDS: how often the scheduler looks for due users;
#   every found user is then staggered and bounded, so a short scan interval
#   does not mean a sync storm.
# - SYNC_STARTUP_STAGGER_SECONDS: upper bound of the deterministic first-run
#   offset (migration prompt §64). A deployment restart must not sync every
#   account at the same instant; each user's offset is derived from its id,
#   so it is stable across restarts yet spread across the window.
# - SYNC_CLAIM_STALE_SECONDS: a sync_status row left in "running" longer
#   than this is treated as a crashed worker and may be re-claimed (§19).
SYNC_MAX_CONCURRENT_USERS = _int_env(
    "GC_DASHBOARD_SYNC_MAX_CONCURRENT_USERS", 2, minimum=1
)
SYNC_SCAN_INTERVAL_SECONDS = _int_env("GC_DASHBOARD_SYNC_SCAN_INTERVAL_SECONDS", 60)
SYNC_STARTUP_STAGGER_SECONDS = _int_env(
    "GC_DASHBOARD_SYNC_STARTUP_STAGGER_SECONDS", 300
)
SYNC_CLAIM_STALE_SECONDS = _int_env("GC_DASHBOARD_SYNC_CLAIM_STALE_SECONDS", 3600)


# Opt-in only: run the per-user scheduler inside the web process. The
# supported deployment is the dedicated worker container (ADR-0023); this
# exists for a single-replica instance that cannot run a second process.
# Duplicate jobs are impossible even then — the DB claim in sync_store
# serializes users across processes.
EMBEDDED_SCHEDULER = bool(_bool_env("GC_DASHBOARD_EMBEDDED_SCHEDULER"))

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------- environment layer
#
# Explicit configuration layers (migration stage 7, §30/§51): one variable
# names the environment, and every environment-sensitive value below derives
# its default from it. Development and production therefore cannot silently
# share a host allow-list or a CORS list.
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower() or "development"
IS_PRODUCTION = APP_ENV == "production"

# --------------------------------------------------------------- hosted mode


# Hosted service switch (migration stage 2, ADR-0020): GC_DASHBOARD_HOSTED=1
# replaces the desktop loopback OAuth with the web OAuth flow, sessions and
# DB-stored tokens. Desktop builds never set it and keep their ADR-0019 flow.
HOSTED_MODE = bool(_bool_env("GC_DASHBOARD_HOSTED"))

# Google web OAuth client of the hosted service (migration prompt §4/§9):
# a client of type "Web application" in the same GCP project, whose
# authorized redirect URI must exactly match GOOGLE_REDIRECT_URI (default
# derived from APP_BASE_URL). The client_id is public; the client_secret is
# a server-only secret and must be injected via the environment — never
# committed, never shipped to the browser, never in frontend assets.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
APP_ORIGIN = normalize_origin(APP_BASE_URL) if APP_BASE_URL else None
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "").strip() or (
    f"{APP_BASE_URL}/api/auth/callback" if APP_BASE_URL else ""
)

# Migration stage 8 (§36): production OAuth never runs over plain HTTP —
# the callback redirect URI (and the base URL it is derived from) must be
# https, or the deployment fails at startup instead of silently issuing
# codes over an insecure channel. Desktop mode is unaffected: its redirect
# is the loopback http://127.0.0.1:<port>/ of auth._CallbackServer (§75).
if IS_PRODUCTION and HOSTED_MODE:
    _bad_scheme_urls = [
        f"{name}={value!r}"
        for name, value in (
            ("APP_BASE_URL", APP_BASE_URL),
            ("GOOGLE_REDIRECT_URI", GOOGLE_REDIRECT_URI),
        )
        if value and not value.startswith("https://")
    ]
    if _bad_scheme_urls:
        raise RuntimeError(
            "Production hosted mode requires HTTPS: "
            + ", ".join(_bad_scheme_urls)
            + ". Terminate TLS at the reverse proxy (Caddy) and set APP_BASE_URL "
            "to the https:// origin (§36)."
        )


# ------------------------------------------------- public-origin config (§27/§28)
#
# Hosted deployment: browser and API share one public origin, so the values
# below are about validating THAT origin, not about enabling cross-origin
# access. The production hostname is never hard-coded: it comes from
# GC_DASHBOARD_ALLOWED_HOSTS or, when that is unset, from the host of
# APP_BASE_URL — one place, the same one the OAuth redirect already uses.


FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _default_allowed_hosts() -> list[str]:
    """Hosts accepted in the Host header when none are configured.

    Production: only the public host of APP_BASE_URL. Development adds the
    loopback names so the local workflow keeps working unchanged.
    """
    hosts: list[str] = []
    if APP_ORIGIN:
        hosts.append(normalize_host(APP_ORIGIN) or "")
    if not IS_PRODUCTION:
        hosts.extend(["localhost", "127.0.0.1"])
    return [host for host in hosts if host]


_raw_allowed_hosts = os.environ.get("GC_DASHBOARD_ALLOWED_HOSTS")
ALLOWED_HOSTS: tuple[str, ...] = (
    tuple(
        dict.fromkeys(
            host
            for item in _csv_env("GC_DASHBOARD_ALLOWED_HOSTS")
            if (host := normalize_host(item)) is not None
        )
    )
    if _raw_allowed_hosts is not None
    else tuple(_default_allowed_hosts())
)

# CORS (§27). Same-origin production traffic needs no permissive CORS, so the
# list is empty there and the middleware never echoes a foreign Origin.
# Development keeps the Vite dev-server origins; an intentional cross-origin
# frontend lists its exact origins in GC_DASHBOARD_CORS_ORIGINS. "*" is never
# valid — it is rejected below rather than combined with credentials.
_raw_cors_origins = os.environ.get("GC_DASHBOARD_CORS_ORIGINS")
CORS_ORIGINS: tuple[str, ...] = (
    _normalize_origins(_csv_env("GC_DASHBOARD_CORS_ORIGINS"))
    if _raw_cors_origins is not None
    else (() if IS_PRODUCTION else tuple(FRONTEND_ORIGINS))
)

# Trusted reverse proxies (§29). ``X-Forwarded-Proto`` is honoured only when
# the direct peer is in this list, so a client reaching the app directly can
# never change the scheme the session cookie is issued for. Empty means "no
# proxy in front": the request's own scheme is authoritative.
TRUSTED_PROXIES: tuple[str, ...] = tuple(_csv_env("GC_DASHBOARD_TRUSTED_PROXIES"))

# Session cookie (§30/ADR-0020). Secure follows the request scheme unless
# COOKIE_SECURE is set explicitly; SameSite stays Lax because the OAuth
# callback arrives as a cross-site top-level redirect.
COOKIE_SECURE: bool | None = _bool_env("COOKIE_SECURE")
_COOKIE_SAMESITE_ALLOWED = ("lax", "strict", "none")
COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
_raw_samesite = os.environ.get("COOKIE_SAMESITE", "lax").strip().lower() or "lax"
if _raw_samesite in _COOKIE_SAMESITE_ALLOWED:
    COOKIE_SAMESITE = _raw_samesite  # type: ignore[assignment]
    if _raw_samesite == "none" and not COOKIE_SECURE:
        logger.warning(
            "COOKIE_SAMESITE=none requires a Secure cookie; setting COOKIE_SECURE=true."
        )
        COOKIE_SECURE = True
else:
    logger.warning(
        "COOKIE_SAMESITE=%r is not one of %s; falling back to 'lax'.",
        _raw_samesite,
        ", ".join(_COOKIE_SAMESITE_ALLOWED),
    )

# §37: the optional __Host- prefix is exactly the constraint set this app
# already enforces for the session cookie (Secure + Path=/ + no Domain).
# Off by default so development over plain http keeps working; enabling it
# without a Secure cookie makes browsers REJECT the cookie (login breaks),
# which is warned about here rather than discovered at runtime.
COOKIE_HOST_PREFIX: str = (
    "__Host-" if bool(_bool_env("GC_DASHBOARD_COOKIE_HOST_PREFIX")) else ""
)
if COOKIE_HOST_PREFIX and COOKIE_SECURE is not True and not IS_PRODUCTION:
    logger.warning(
        "GC_DASHBOARD_COOKIE_HOST_PREFIX is set but COOKIE_SECURE is not "
        "true outside production: browsers reject __Host- cookies without "
        "the Secure attribute, so sign-in will fail on plain-http origins."
    )

# §36/§48: HSTS is opt-in. Send it only after HTTPS behaviour is confirmed
# (migration stage 10); the value is max-age seconds, 0 = header off.
# The reverse proxy may set the header instead — then keep this at 0 to
# avoid duplicates.
HSTS_MAX_AGE = _int_env("GC_DASHBOARD_HSTS_MAX_AGE", 0)


def hosted_oauth_client_config() -> dict | None:
    """OAuth client config of the hosted web client, or None.

    Mirrors the ``{"web": {"client_id", "client_secret", "token_uri",
    "redirect_uri"}}`` shape google-auth libraries use for web clients so
    the token-exchange helpers in auth.py work unchanged. Returns None when
    the configuration is incomplete — hosted endpoints then fail closed.
    """
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI):
        return None
    return {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uri": GOOGLE_REDIRECT_URI,
    }
