"""FastAPI application entry point.

Development: run from the backend directory with

    uvicorn main:app --reload

and use the Vite dev server (http://localhost:5173) for the frontend.

Production: backend/launcher.py starts this app and serves the frontend
built with `npm run build` from frontend/dist on the same origin, so the
browser only ever talks to http://127.0.0.1:<port>.

Hosted mode (GC_DASHBOARD_HOSTED=1, migration stage 2 / ADR-0020) builds a
different app: web OAuth + sessions (hosted_auth.py) are mounted in front
of the API and every data endpoint is gated on an application session. The
desktop build keeps its exact pre-migration behaviour.

Coexistence and the production edge (migration stage 8, §32–§38/§48):

- the hosted startup path imports NO desktop module — background_sync
  (desktop global schedule) is loaded lazily inside the desktop lifespan
  branch, and launcher.py/tray/single-instance/Nuitka artifacts are never
  reachable from here (§32/§74);
- hosted additionally installs security headers (CSP, nosniff,
  Referrer-Policy, frame options, opt-in HSTS), the CSRF fetch-metadata
  check on state-changing methods, ``Cache-Control: no-store`` on /api and
  uvicorn query redaction (§36/§38/§48);
- static assets are served by THIS app (Option A of §35, Caddy → FastAPI).

This module is the composition root and nothing else (ADR-0039 stage 2): the
lifespan, the four middleware, the Host/Origin guard, the CSP and the static
mount live in ``edge/``, so each is reachable on its own instead of only
through a 517-line file. What stays here is the ORDER, which is itself the
contract: routers are included so that the hosted ``/api/auth/*`` shadows the
desktop one, and middleware is registered inside-out exactly as documented in
``edge/middleware.py``.
"""

import logging

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api import router
from api.routes import admins as admins_routes
from api.routes import feedback as feedback_routes
from api.routes import feedback_admin as feedback_admin_routes
from core import rate_limit
from core.config import HOSTED_MODE
from core.logging_filters import install_query_redaction
from db.session import get_db
from edge import static
from edge.lifespan import lifespan
from edge.middleware import (
    install_cors,
    install_host_guard,
    install_security_headers,
    install_session_gate,
    install_throttle,
)

logger = logging.getLogger(__name__)


def create_app(hosted: bool = False) -> FastAPI:
    """Build the FastAPI app for one deployment mode.

    Desktop (default): loopback OAuth (ADR-0019), env-driven Host/Origin
    guard, global background sync — byte-for-byte the pre-migration
    behaviour.

    Hosted: web OAuth + sessions (ADR-0020). The hosted /api/auth/* router
    is included BEFORE the api router so its GET /auth/status, GET+POST
    /auth/login and POST /auth/logout shadow the desktop ones; a session
    gate closes every other /api path, and since stage 4 every data
    endpoint additionally resolves its user through the
    ``ownership.get_current_user`` dependency (§13) — the gate is the
    outermost check, the dependency is the authoritative one.

    Middleware order (last added is outermost): security headers → Host/Origin
    guard → CORS → session gate → throttle. CORS sits outside the gate so error
    responses (401/403) still carry the headers a browser needs to read them.
    """
    app = FastAPI(
        title="Local Google Classroom Dashboard", version="1.0.0", lifespan=lifespan
    )
    app.state.hosted = hosted
    # Stage 9 (§39): in-memory token buckets live on the app instance, not in
    # a module global — two apps in one process (desktop + hosted in tests)
    # never share quota, and a fresh app starts with fresh buckets.
    app.state.rate_limiter = rate_limit.RateLimiter()

    if hosted:
        install_throttle(app)
        install_session_gate(app)

        # Imported HERE, not at module level: the hosted deployment must never
        # load the desktop OAuth modules (stage 8, §32/§74). The router is
        # included BEFORE the api router below so its /api/auth/* shadow the
        # desktop ones.
        from auth.hosted import router as hosted_router

        app.include_router(hosted_router)

    install_cors(app)
    install_host_guard(app, hosted)

    app.include_router(router)

    # Ticket feature (ADR-0035). Included from here, inside the hosted
    # middleware stack, so the session gate, the Host/Origin guard, the CSRF
    # check and Cache-Control: no-store already apply to every feedback
    # endpoint — no state-changing endpoint gets a weaker protection of its own.
    # Administrator management (ADR-0036), Super-Admin-only. Included from here,
    # inside the hosted middleware stack, so the session gate, the Host/Origin
    # guard, the CSRF check and Cache-Control: no-store apply to it exactly as
    # they do to every other /api endpoint — the registry is not a weaker
    # surface than the tickets.
    #
    # These three live in ``api/routes/`` but are mounted by ``create_app``
    # instead of by ``api/__init__.py``, because they are hosted-only: putting
    # them into the shared router would expose them on the desktop build.
    app.include_router(feedback_routes.router)
    app.include_router(feedback_admin_routes.router)
    app.include_router(admins_routes.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/ready")
    def ready(db: Session = Depends(get_db)) -> JSONResponse:  # noqa: B008
        """Readiness check (migration stage 10, §58 / DDoS plan §24).

        Verifies that the database connection pool and engine are operational
        without leaking infrastructure details, environment variables, or credentials.
        Returns 200 {"ok": True, "db": "up"} or 503 {"ok": False, "db": "down"}.
        """
        try:
            db.execute(select(1))
            return JSONResponse({"ok": True, "db": "up"}, status_code=200)
        except SQLAlchemyError as exc:
            logger.warning("Readiness probe database check failed: %s", exc)
            return JSONResponse({"ok": False, "db": "down"}, status_code=503)

    # Registered after the /api router: API routes always win. The mount is
    # skipped when frontend/dist has not been built yet (development).
    static.mount_frontend(app)

    if hosted:
        # Production edge of the hosted service (§36/§38/§48). Installed
        # LAST, so it wraps every other middleware — including the guard's
        # own 403 answers. The desktop build gets none of this: it is bound
        # to loopback and keeps byte-for-byte its pre-stage-8 behaviour (§74).
        install_query_redaction()
        install_security_headers(app)

    return app


app = create_app(hosted=HOSTED_MODE)
