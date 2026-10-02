"""Serve the built SPA from the app itself (migration stage 8, §35 Option A).

Caddy/Caddy-style deployment is out of the picture: the FastAPI process
serves ``frontend/dist`` on the same origin, so the browser never makes a
cross-origin request to the API and the CSRF story stays as simple as
"same-origin only".

``FRONTEND_DIST_DIR`` is read through the module object, so a test can point
the mount at a temporary directory (that is what
``tests/test_stage8_coexistence.py`` does) without a rebuild.
"""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import path_config

logger = logging.getLogger(__name__)


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
            # Bundled assets never fall back to the shell: a missing
            # hashed file must stay a 404. The path may arrive with the
            # mount prefix stripped or not, with "/" or Windows "\"
            # separators (development on Windows) — normalize first.
            normalized = path.replace("\\", "/").lstrip("/")
            if normalized.startswith("assets/"):
                raise
            return await super().get_response("index.html", scope)


def mount_frontend(app: FastAPI) -> None:
    """Mount the built SPA at /, after the API routes.

    Registered after the /api router: API routes always win. The mount is
    skipped when frontend/dist has not been built yet (development).
    """
    if path_config.FRONTEND_DIST_DIR.is_dir():
        app.mount(
            "/",
            SPAStaticFiles(directory=path_config.FRONTEND_DIST_DIR, html=True),
            name="frontend",
        )
    else:
        logger.warning(
            "frontend/dist not found at %s — production frontend is not served "
            "(run `npm run build`, or use the Vite dev server).",
            path_config.FRONTEND_DIST_DIR,
        )
