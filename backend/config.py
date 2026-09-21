"""Application paths and configuration.

All path resolution lives in path_config.py (RESOURCE_DIR vs DATA_DIR,
development vs compiled build). Secrets (OAuth client credentials, tokens)
are kept outside the source code: they live in files that are git-ignored
and can be relocated with environment variables.
"""

import os
from pathlib import Path

from path_config import DATA_DIR, PROJECT_DIR, ensure_data_dirs

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


SYNC_MAX_WORKERS = _int_env("GC_DASHBOARD_SYNC_WORKERS", 16, minimum=1)

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
def _embedded_scheduler_enabled() -> bool:
    return os.environ.get("GC_DASHBOARD_EMBEDDED_SCHEDULER", "").strip() in {
        "1",
        "true",
        "TRUE",
        "True",
        "yes",
    }


EMBEDDED_SCHEDULER = _embedded_scheduler_enabled()

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Local app: the frontend dev server origin is the only browser origin.
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


# --------------------------------------------------------------- hosted mode


# Hosted service switch (migration stage 2, ADR-0020): GC_DASHBOARD_HOSTED=1
# replaces the desktop loopback OAuth with the web OAuth flow, sessions and
# DB-stored tokens. Desktop builds never set it and keep their ADR-0019 flow.
def _hosted_enabled() -> bool:
    return os.environ.get("GC_DASHBOARD_HOSTED", "").strip() in {
        "1",
        "true",
        "TRUE",
        "True",
        "yes",
    }


HOSTED_MODE = _hosted_enabled()

# Google web OAuth client of the hosted service (migration prompt §4/§9):
# a client of type "Web application" in the same GCP project, whose
# authorized redirect URI must exactly match GOOGLE_REDIRECT_URI (default
# derived from APP_BASE_URL). The client_id is public; the client_secret is
# a server-only secret and must be injected via the environment — never
# committed, never shipped to the browser, never in frontend assets.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "").strip() or (
    f"{APP_BASE_URL}/api/auth/callback" if APP_BASE_URL else ""
)


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
