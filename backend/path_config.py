"""Path abstraction for development and production (Nuitka) builds.

Distinguishes two kinds of locations:

RESOURCE_DIR — read-only resources bundled with the application. In a
Nuitka standalone/onefile build this is the dist/extraction directory that
contains every data file added with ``--include-data-dir`` (e.g.
``frontend/dist``). In development it is the ``backend/`` directory of the
project tree.

DATA_DIR — user-specific writable data (OAuth token, SQLite database,
logs). In a compiled build this lives under
``%LOCALAPPDATA%\\GoogleClassHelp`` so the application works when installed
into a read-only location such as ``C:\\Program Files\\GoogleClassHelp``.
In development it stays in the project tree (``<project>/data``) so the
existing workflow is untouched. The hosted service is neither: it has no
per-machine desktop state, so it uses an explicit container path
(``/data``, a mounted volume) instead of any Windows location (§31).

The hosted application must not depend on the process working directory:
every path here is absolute and derived from this file's location or an
explicit environment variable.

No code outside this module may use ``Path.cwd()`` or hard-coded paths:
the application must run from any install directory.
"""

import os
import sys
from pathlib import Path

# Nuitka sets the __compiled__ attribute in every module it compiles;
# sys.frozen is set for standalone/onefile builds. Under plain CPython
# neither exists, so this is a reliable dev/production switch.
IS_FROZEN = "__compiled__" in globals() or hasattr(sys, "frozen")

# Hosted container path (§31, §51): the deploy mounts a volume here. Read
# straight from the environment, not from config, because config imports
# this module (a config import here would be a cycle).
HOSTED_MODE = os.environ.get("GC_DASHBOARD_HOSTED", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
HOSTED_DATA_DIR = Path("/data")

BACKEND_DIR = Path(__file__).resolve().parent

if IS_FROZEN:
    # Data files included by Nuitka are placed relative to the compiled
    # modules inside the dist/extraction directory.
    RESOURCE_DIR = BACKEND_DIR
    PROJECT_DIR = BACKEND_DIR
    # Bundled by the Nuitka build next to the compiled modules.
    FRONTEND_DIST_DIR: Path = RESOURCE_DIR / "frontend/dist"
else:
    PROJECT_DIR = BACKEND_DIR.parent
    RESOURCE_DIR = BACKEND_DIR
    # Regular project output of `npm run build` in development.
    FRONTEND_DIST_DIR = PROJECT_DIR / "frontend/dist"


def _resolve_data_dir() -> Path:
    """Writable data directory for this deployment (§31).

    Precedence:

    1. ``GC_DASHBOARD_DATA_DIR`` — explicit override, any environment;
    2. hosted mode — the container volume ``/data`` (never
       ``%LOCALAPPDATA%``, never the working directory);
    3. compiled desktop build — ``%LOCALAPPDATA%\\GoogleClassHelp``;
    4. development — ``<project>/data``.
    """
    override = os.environ.get("GC_DASHBOARD_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if HOSTED_MODE and os.name == "posix":
        return HOSTED_DATA_DIR
    if IS_FROZEN:
        local_appdata = os.environ.get("LOCALAPPDATA")
        base = (
            Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        )
        return base / "GoogleClassHelp"
    # Development keeps writable data inside the project tree.
    return PROJECT_DIR / "data"


DATA_DIR: Path = _resolve_data_dir()
LOGS_DIR: Path = DATA_DIR / "logs"


def ensure_data_dirs() -> None:
    """Create writable directories on demand (token, database, logs)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
