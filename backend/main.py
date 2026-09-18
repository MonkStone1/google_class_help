"""FastAPI application entry point.

Development: run from the backend directory with

    uvicorn main:app --reload

and use the Vite dev server (http://localhost:5173) for the frontend.

Production: backend/launcher.py starts this app and serves the frontend
built with `npm run build` from frontend/dist on the same origin, so the
browser only ever talks to http://127.0.0.1:<port>.
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
from config import FRONTEND_ORIGINS
from database import init_db
from path_config import FRONTEND_DIST_DIR

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Init the DB, start the background schedule, stop it on shutdown.

    Replaces the deprecated @app.on_event("startup") (review §1.9).
    """
    init_db()
    # Sync right after startup, then automatically every interval (ADR-0015).
    start_background_sync()
    yield
    stop_background_sync()


app = FastAPI(
    title="Local Google Classroom Dashboard", version="1.0.0", lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------- local guard


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
