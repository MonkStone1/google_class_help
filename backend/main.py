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

import logging
import urllib.parse
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import router
from background_sync import start as start_background_sync
from background_sync import stop as stop_background_sync
from config import EMBEDDED_SCHEDULER, FRONTEND_ORIGINS, HOSTED_MODE
from database import SessionLocal, init_db
from path_config import FRONTEND_DIST_DIR

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


# ----------------------------------------------------- desktop local guard


# The server binds to 127.0.0.1 only (launcher); the middleware below is the
# second line of defence against DNS rebinding / foreign pages (review §2.4).
TRUSTED_HOSTS = ("127.0.0.1", "localhost")


def _origin_allowed(origin: str) -> bool:
    """The Vite dev origin, or the dashboard's own same-origin POSTs.

    A same-origin fetch sends its own origin (e.g. http://127.0.0.1:8000),
    which is trusted by construction — the check only needs to reject
    origins from foreign pages, whose host is not ours.
    """
    if origin in FRONTEND_ORIGINS:
        return True
    try:
        return urllib.parse.urlparse(origin).hostname in TRUSTED_HOSTS
    except ValueError:
        return False


def create_app(hosted: bool = False) -> FastAPI:
    """Build the FastAPI app for one deployment mode.

    Desktop (default): loopback OAuth (ADR-0019), 127.0.0.1 guards, global
    background sync — byte-for-byte the pre-migration behaviour.

    Hosted: web OAuth + sessions (ADR-0020). The hosted /api/auth/* router
    is included BEFORE the api router so its GET /auth/status, GET+POST
    /auth/login and POST /auth/logout shadow the desktop ones; a session
    gate closes every other /api path, and since stage 4 every data
    endpoint additionally resolves its user through the
    ``ownership.get_current_user`` dependency (§13) — the gate is the
    outermost check, the dependency is the authoritative one.
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if not hosted:
        # Desktop only: the local-only Host/Origin guard. Hosted replaces
        # it with real authentication; env-driven trusted hosts for the
        # production domain arrive with stage 7.
        @app.middleware("http")
        async def enforce_local_only(request: Request, call_next):
            host = request.headers.get("host", "").split(":")[0].lower()
            origin = request.headers.get("origin")
            if host not in TRUSTED_HOSTS:
                return JSONResponse({"detail": "Forbidden"}, status_code=403)
            # Browser requests from foreign pages are cut by Origin; non-browser
            # requests (curl) send no Origin and are limited by the 127.0.0.1 bind.
            if origin is not None and not _origin_allowed(origin):
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
