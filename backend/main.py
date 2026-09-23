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
"""

# isort: off
# Grouped per ruff.toml's known-first-party list.  The isort: off/on pair
# keeps that project grouping authoritative even for tools that run
# `ruff --isolated` and therefore cannot see the same first-party list.
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import router
from background_sync import start as start_background_sync
from background_sync import stop as stop_background_sync
from config import (
    ALLOWED_HOSTS,
    APP_ORIGIN,
    CORS_ORIGINS,
    EMBEDDED_SCHEDULER,
    FRONTEND_ORIGINS,
    HOSTED_MODE,
    IS_PRODUCTION,
    normalize_origin,
)
from database import SessionLocal, init_db
from path_config import FRONTEND_DIST_DIR
from proxy import effective_authority, host_and_port_from_value, public_origin
# isort: on

logger = logging.getLogger(__name__)


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
    user_scheduler = None
    if not app.state.hosted:
        # Sync right after startup, then automatically every interval (ADR-0015).
        start_background_sync()
    elif EMBEDDED_SCHEDULER:
        from sync_scheduler import start as start_user_scheduler

        user_scheduler = start_user_scheduler()
    yield
    if not app.state.hosted:
        stop_background_sync()
    elif user_scheduler is not None:
        user_scheduler.stop()


# ------------------------------------------------------- Host/Origin guard
#
# Migration stage 7 (§27/§28): the accepted Host names are configuration, not
# code. Desktop development keeps localhost/127.0.0.1 (the default), the
# hosted service answers on its public domain (from
# GC_DASHBOARD_ALLOWED_HOSTS or the host of APP_BASE_URL). The guard runs in
# BOTH modes: hosted mode has real authentication, but a correct Host check is
# still the first line of defence against DNS-rebinding style requests.


def _host_allowed(host_header: str) -> bool:
    """Return whether a Host-header authority is on the configured allow-list."""
    authority = host_and_port_from_value(host_header)
    return authority is not None and authority[0] in ALLOWED_HOSTS


def _request_host_allowed(request: Request) -> bool:
    """Validate the effective public authority, including trusted proxies."""
    authority = effective_authority(request)
    return authority is not None and authority[0] in ALLOWED_HOSTS


def _origin_allowed(origin: str, request: Request | None = None) -> bool:
    """Allow only exact configured origins or the request's own origin.

    Hostname-only matching is deliberately not enough: scheme and port are
    part of origin identity.  Development keeps the Vite origins; production
    requires an explicit CORS entry for a cross-origin frontend.
    """
    normalized = normalize_origin(origin)
    if normalized is None:
        return False
    if normalized in CORS_ORIGINS:
        return True
    if not IS_PRODUCTION and normalized in FRONTEND_ORIGINS:
        return True
    if request is None:
        return APP_ORIGIN is not None and normalized == APP_ORIGIN
    request_origin = public_origin(request)
    return request_origin is not None and normalized == request_origin


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

    Middleware order (last added is outermost): session gate → Host/Origin
    guard → CORS. CORS is outermost so error responses (401/403) still
    carry the headers a browser needs to read them.
    """
    app = FastAPI(
        title="Local Google Classroom Dashboard", version="1.0.0", lifespan=lifespan
    )
    app.state.hosted = hosted

    if hosted:
        from hosted_auth import resolve_session_user
        from hosted_auth import router as hosted_router

        # Added FIRST so CORS (added below) wraps the gate: 401 responses
        # still carry CORS headers and the frontend can read them (§7).
        @app.middleware("http")
        async def require_session(request: Request, call_next):
            path = request.url.path
            # The auth flow itself, the health probe and CORS preflights
            # must stay reachable without a session.
            if (
                request.method == "OPTIONS"
                or path == "/api/health"
                or path.startswith("/api/auth/")
            ):
                return await call_next(request)
            db = SessionLocal()
            try:
                # Sync call inside async middleware. Since stage 4 the
                # authoritative user resolution is the get_current_user
                # dependency inside each endpoint; this gate only fails the
                # request early, before route dispatch.
                user = resolve_session_user(request, db)
            except StarletteHTTPException:
                return JSONResponse({"detail": "Not signed in."}, status_code=401)
            finally:
                db.close()
            request.state.user_id = user.id
            return await call_next(request)

        app.include_router(hosted_router)

    # CORS is intentionally inside the Host/Origin guard: a foreign Host or
    # Origin never reaches Starlette's preflight responder.  For an allowed
    # cross-origin request, CORS remains outside the session gate so 401/403
    # responses are readable by the browser (§27).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def enforce_allowed_host(request: Request, call_next):
        if not _request_host_allowed(request):
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        # Browser requests from foreign pages are cut by exact Origin matching;
        # non-browser requests send no Origin and remain limited by the session
        # gate (hosted) or the loopback bind (desktop).
        origin = request.headers.get("origin")
        if origin is not None and not _origin_allowed(origin, request):
            return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
        return await call_next(request)

    app.include_router(router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    class SPAStaticFiles(StaticFiles):
        """Static files with SPA fallback.

        The frontend uses client-side routing (BrowserRouter); unknown paths
        (e.g. /subjects/123) must return index.html so React Router can take
        over, while missing static assets still return a normal 404.
        """

        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404:
                    raise
                if path.startswith("assets/"):
                    raise
                return await super().get_response("index.html", scope)

    # Registered after the /api router: API routes always win. The mount is
    # skipped when frontend/dist has not been built yet (development).
    if FRONTEND_DIST_DIR.is_dir():
        app.mount(
            "/", SPAStaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend"
        )
    else:
        logger.warning(
            "frontend/dist not found at %s — production frontend is not served "
            "(run `npm run build`, or use the Vite dev server).",
            FRONTEND_DIST_DIR,
        )
    return app


app = create_app(hosted=HOSTED_MODE)
