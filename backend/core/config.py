"""Application paths and configuration.

All path resolution lives in path_config.py (RESOURCE_DIR vs DATA_DIR,
development vs compiled build). Secrets (OAuth client credentials, tokens)
are kept outside the source code: they live in files that are git-ignored
and can be relocated with environment variables.
"""

import logging
import os
from pathlib import Path

from core import origins
from core.origins import normalize_origin
from path_config import DATA_DIR, PROJECT_DIR, ensure_data_dirs

# The origin/host NORMALIZATION rules live in ``core/origins.py`` (ADR-0039):
# they are pure functions with no environment access, and keeping them apart is
# what lets the Host/Origin guard be tested without a configured process.
#
# ``core.proxy`` and ``edge.origin_guard`` are bound to the module objects, but
# the tests have always read these two through ``config``; binding them to the
# SAME function objects (not copies) keeps both spellings working and keeps a
# monkeypatch visible from either side.
canonical_origin = origins.canonical_origin
host_and_port_from_value = origins.host_and_port_from_value

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


def normalize_email(value: str | None) -> str:
    """Trim and lower-case an address; ``""`` for None/blank.

    The ONE normalization of the whole feature (ADR-0036): the environment
    value, a row of the ``admins`` table and the address of the signed-in
    session all pass through it, so a case or a stray space can never make two
    spellings of one account look like two different people. It is deliberately
    not a validation — a syntactically broken value stays a string here and is
    rejected (or ignored) by the caller that needs it to be an address.
    """
    return (value or "").strip().lower()


# ------------------------------------------------------ super admin (ADR-0036)
# The ONE account that may manage the administrator registry. Unlike the
# ordinary administrators it is NOT a database row: it lives in the process
# environment, unprefixed (like COOKIE_SECURE / APP_BASE_URL /
# TURNSTILE_SITE_KEY) because it is an authorization value, not a tuning knob.
#
# Fail CLOSED (D6): unset, empty, whitespace-only or a value without "@" means
# NOBODY is a Super Admin. A typo must never widen access, so a malformed value
# is treated exactly like a missing one instead of half-matching an address.
#
# The value never reaches React, never becomes a /api/config field, never
# appears in the OpenAPI document and is never written to a log line: the
# frontend learns the single boolean ``UserOut.is_super_admin`` and nothing
# else. Changing it takes effect after a restart of `web`, with no code change.
# The previous ADR-0035 allow-list (``ADMIN_EMAILS``) is GONE (D5): the normal
# administrators live in the ``admins`` table and nowhere else.
_normalized_super_admin = normalize_email(os.environ.get("SUPER_ADMIN_EMAIL"))
SUPER_ADMIN_EMAIL: str | None = (
    _normalized_super_admin if "@" in _normalized_super_admin else None
)

# Stage-9 hosted Postgres pool (section 45/88): small on purpose. Sync no
# longer holds a connection across the Google fetch, so a handful covers
# web requests plus the bounded scheduler on the 2 vCPU / 2 GB target.
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
# Coarse per-IP cap in front of the feedback POSTs (ADR-0035). Generous on
# purpose: it exists to stop one address from streaming multipart bodies into
# the single web replica, while the actual per-user budget lives in the
# endpoints (FEEDBACK_TICKETS_PER_HOUR / FEEDBACK_REPLIES_PER_HOUR) — a school
# NAT shares an address between many legitimate users.
RATE_LIMIT_FEEDBACK_PER_MINUTE = _int_env(
    "GC_DASHBOARD_RATE_LIMIT_FEEDBACK_PER_MINUTE", 30, minimum=1
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


# ----------------------------------------------- feedback tickets (ADR-0035)
# Limits of the ticket feature. They are TUNING knobs, so they take the
# GC_DASHBOARD_ prefix (unlike ADMIN_EMAILS above, which is an authorization
# value). Defaults are the conservative first-production numbers from the
# feature plan: the hosted service is a 1-2 vCPU VPS with a single web replica,
# multipart bodies are parsed in-process, and one message may carry up to 3
# files / 10 MB in total.
#
# The per-user buckets are token buckets with an hourly window, so a user who
# exhausted the allowance recovers gradually instead of waiting for a fixed
# wall-clock hour (rate_limit.RateLimiter).
FEEDBACK_TICKETS_PER_HOUR = _int_env(
    "GC_DASHBOARD_FEEDBACK_TICKETS_PER_HOUR", 5, minimum=1
)
FEEDBACK_REPLIES_PER_HOUR = _int_env(
    "GC_DASHBOARD_FEEDBACK_REPLIES_PER_HOUR", 30, minimum=1
)
# Content limits (characters). A subject is a title, not a document; a message
# is a support reply, not a paste of a log file.
FEEDBACK_MAX_SUBJECT_CHARS = _int_env(
    "GC_DASHBOARD_FEEDBACK_MAX_SUBJECT_CHARS", 200, minimum=1
)
FEEDBACK_MAX_MESSAGE_CHARS = _int_env(
    "GC_DASHBOARD_FEEDBACK_MAX_MESSAGE_CHARS", 20000, minimum=1
)
# Attachments per message (bytes). The 64 MB figure of the reference product is
# deliberately NOT adopted: the edge and the web process both hold the body.
FEEDBACK_MAX_ATTACHMENTS = _int_env(
    "GC_DASHBOARD_FEEDBACK_MAX_ATTACHMENTS", 3, minimum=1
)
FEEDBACK_MAX_ATTACHMENT_BYTES = _int_env(
    "GC_DASHBOARD_FEEDBACK_MAX_ATTACHMENT_BYTES", 5 * 1024 * 1024, minimum=1
)
FEEDBACK_MAX_TOTAL_BYTES = _int_env(
    "GC_DASHBOARD_FEEDBACK_MAX_TOTAL_BYTES", 10 * 1024 * 1024, minimum=1
)
# The public label an administrator replies under when they do not choose one.
FEEDBACK_DEFAULT_ADMIN_NAME = "GoogleClassHelp Support"
# Hard cap on the administrator's chosen public display name (characters).
FEEDBACK_MAX_DISPLAY_NAME_CHARS = _int_env(
    "GC_DASHBOARD_FEEDBACK_MAX_DISPLAY_NAME_CHARS", 100, minimum=1
)

# Background sync: runs once at startup, then every SYNC_INTERVAL_MINUTES.
# 0 disables the schedule entirely (no startup sync, no repeats).
SYNC_INTERVAL_MINUTES = _int_env("GC_DASHBOARD_SYNC_INTERVAL_MINUTES", 10)


# ------------------------------------------------- per-user sync (stage 5)
#
# The scheduler picks users up individually instead of running one global
# loop (migration prompt В§18/В§19). These knobs bound the work it may create:
#
# - SYNC_MAX_CONCURRENT_USERS: how many users may sync at the same time
#   across the whole worker. Each user's sync uses SYNC_MAX_WORKERS threads,
#   so the total thread budget is the product of the two (and the Google
#   per-project quota budget is shared by all of them).
# - SYNC_SCAN_INTERVAL_SECONDS: how often the scheduler looks for due users;
#   every found user is then staggered and bounded, so a short scan interval
#   does not mean a sync storm.
# - SYNC_STARTUP_STAGGER_SECONDS: upper bound of the deterministic first-run
#   offset (migration prompt В§64). A deployment restart must not sync every
#   account at the same instant; each user's offset is derived from its id,
#   so it is stable across restarts yet spread across the window.
# - SYNC_CLAIM_STALE_SECONDS: a sync_status row left in "running" longer
#   than this is treated as a crashed worker and may be re-claimed (В§19).
# - SYNC_STUCK_SECONDS: how long a running sync may last before the dashboard
#   calls it stuck AND `POST /api/sync?restart=true` is allowed to abandon it
#   (ADR-0032). It is the USER-facing threshold, so it must stay above the
#   worst legitimate Classroom import — a sync that is still making progress is
#   never interrupted. It is deliberately independent of
#   SYNC_CLAIM_STALE_SECONDS: that one is the silent backstop for a dead
#   worker, this one is what the user is offered a restart for.
SYNC_MAX_CONCURRENT_USERS = _int_env(
    "GC_DASHBOARD_SYNC_MAX_CONCURRENT_USERS", 2, minimum=1
)
SYNC_SCAN_INTERVAL_SECONDS = _int_env("GC_DASHBOARD_SYNC_SCAN_INTERVAL_SECONDS", 60)
SYNC_STARTUP_STAGGER_SECONDS = _int_env(
    "GC_DASHBOARD_SYNC_STARTUP_STAGGER_SECONDS", 300
)
SYNC_CLAIM_STALE_SECONDS = _int_env("GC_DASHBOARD_SYNC_CLAIM_STALE_SECONDS", 3600)
SYNC_STUCK_SECONDS = _int_env("GC_DASHBOARD_SYNC_STUCK_SECONDS", 300, minimum=1)


# Opt-in only: run the per-user scheduler inside the web process. The
# supported deployment is the dedicated worker container (ADR-0023); this
# exists for a single-replica instance that cannot run a second process.
# Duplicate jobs are impossible even then — the DB claim in sync_store
# serializes users across processes.
EMBEDDED_SCHEDULER = bool(_bool_env("GC_DASHBOARD_EMBEDDED_SCHEDULER"))

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------- environment layer
#
# Explicit configuration layers (migration stage 7, В§30/В§51): one variable
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

# Google web OAuth client of the hosted service (migration prompt В§4/В§9):
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

# Migration stage 8 (В§36): production OAuth never runs over plain HTTP —
# the callback redirect URI (and the base URL it is derived from) must be
# https, or the deployment fails at startup instead of silently issuing
# codes over an insecure channel. Desktop mode is unaffected: its redirect
# is the loopback http://127.0.0.1:<port>/ of auth._CallbackServer (В§75).
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
            "to the https:// origin (В§36)."
        )


# The HTTP-exposure values live in ``core/http_config.py`` (ADR-0039). They are
# re-bound here so every existing ``from core.config import ALLOWED_HOSTS``
# keeps working during the restructure; these are the SAME objects, so a test
# that patches ``http_config.X`` still sees the change wherever it is read.
# Import them from ``core.http_config`` in new code.
from core.http_config import (  # noqa: F401  (re-export; http_config imports config)
    ALLOWED_HOSTS,
    COOKIE_HOST_PREFIX,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    CORS_ORIGINS,
    FRONTEND_ORIGINS,
    HSTS_MAX_AGE,
    TRUSTED_PROXIES,
    TURNSTILE_ENABLED,
    TURNSTILE_SECRET_KEY,
    TURNSTILE_SITE_KEY,
    _default_allowed_hosts,
)
