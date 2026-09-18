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
TOKEN_FILE = Path(
    os.environ.get("GC_DASHBOARD_TOKEN", DATA_DIR / "token.json")
)
DATABASE_FILE = DATA_DIR / "classroom.db"

# Development-only fallback: the visible credentials.json in the project
# tree. In production builds the client config is embedded (see
# build_secrets.py / auth.py) and this file is not distributed.
CREDENTIALS_FILE = Path(
    os.environ.get("GC_DASHBOARD_CREDENTIALS", PROJECT_DIR / "backend" / "credentials.json")
)


# Sync concurrency. Classroom API quotas: 1200 queries/min per user (~20 QPS)
# and 3000/min per client. 16 workers keeps a typical sync under the per-user
# quota while still saturating network latency; raise via env only together
# with quota monitoring (429s are retried with exponential backoff).
def _sync_max_workers() -> int:
    """Resolve the sync pool size; an invalid env value falls back to 16."""
    raw = os.environ.get("GC_DASHBOARD_SYNC_WORKERS", "")
    try:
        return max(1, int(raw)) if raw else 16
    except ValueError:
        return 16


SYNC_MAX_WORKERS = _sync_max_workers()


def _sync_interval_minutes() -> int:
    """Resolve the background sync interval in minutes; invalid values fall back to 10."""
    raw = os.environ.get("GC_DASHBOARD_SYNC_INTERVAL_MINUTES", "")
    try:
        return max(0, int(raw)) if raw else 10
    except ValueError:
        return 10


# Background sync: runs once at startup, then every SYNC_INTERVAL_MINUTES.
# 0 disables the schedule entirely (no startup sync, no repeats).
SYNC_INTERVAL_MINUTES = _sync_interval_minutes()

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Local app: the frontend dev server origin is the only browser origin.
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
