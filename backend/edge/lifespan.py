"""Start and stop the background schedules around the app (ADR-0019, §19).

Extracted from ``main.py`` verbatim in ADR-0039 stage 2: the lifespan was a
310-line closure factory's neighbour and could not be exercised without
building a whole app.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import EMBEDDED_SCHEDULER
from core.logging_filters import install_secret_redaction
from db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Init the DB, start the background schedule, stop it on shutdown.

    Replaces the deprecated @app.on_event("startup") (review §1.9).

    - Desktop: the single-user schedule (ADR-0015) — sync right after
      startup, then every interval.
    - Hosted: per-user scheduling belongs to the dedicated worker container
      (migration stage 5, §19, ADR-0023), so the web process does NOT start
      it. ``GC_DASHBOARD_EMBEDDED_SCHEDULER=1`` opts a single-replica
      deployment into running the scheduler here; duplicate jobs remain
      impossible because every sync claims its user in the database.
    """
    init_db()
    # Stage 9 (§42): hosted application logs go to stdout/stderr (Docker and
    # systemd capture them — no RotatingFileHandler like the desktop
    # launcher's logs/app.log). The secret filter is a safety net on top of
    # "never log credentials": a stray token-shaped value degrades to
    # [REDACTED] instead of a leak. Desktop keeps its file log untouched.
    if app.state.hosted:
        install_secret_redaction()
    user_scheduler = None
    if not app.state.hosted:
        # Desktop-only schedule (ADR-0015). Imported HERE, not at module
        # level: the hosted deployment must never load the desktop global
        # scheduler (migration stage 8, §32/§74).
        from sync.background import start as start_background_sync

        start_background_sync()
    elif EMBEDDED_SCHEDULER:
        from sync.scheduler import start as start_user_scheduler

        user_scheduler = start_user_scheduler()
    yield
    if not app.state.hosted:
        from sync.background import stop as stop_background_sync

        stop_background_sync()
    elif user_scheduler is not None:
        user_scheduler.stop()
