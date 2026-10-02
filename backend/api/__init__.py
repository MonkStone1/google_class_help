"""HTTP API surface of the dashboard, assembled from one router per resource.

``main.py`` mounts ``from api import router`` — the same import it used when
this was a single 1692-line ``api.py`` (ADR-0039). ``router`` keeps its
``/api`` prefix, and the sub-routers below carry the full paths, so every path,
method, handler name and therefore OpenAPI ``operationId`` is exactly what it
was. ``tests/test_api_contract.py`` pins that set, so a careless move here
fails a test instead of reaching the frontend's generated types.

Layer rules (docs/BACKEND_STRUCTURE.md):

- ``routes/*`` — dependencies, validation, HTTP status codes. No SQL.
- ``queries/*`` — cache reads. No ``fastapi``, no ``HTTPException``.
- ``identity.py`` — the profile cache and the ``UserOut``/``AuthStatus``
  projection, shared with ``hosted_auth.py``.
- ``guards.py`` — the only place a cache fact becomes 404 or 403.

Order of the ``include_router`` calls below follows the original file. It does
not decide any match today (no static path here competes with a parameterised
one), but keeping it means a later move cannot silently change which route
wins. The routers that DO shadow — hosted ``/api/auth/*`` over the desktop ones
— are included by ``main.py`` before this router, which is why it must stay
there.
"""

from fastapi import APIRouter

from api.routes import (
    account,
    assignments,
    auth,
    cache,
    calendar,
    courses,
    grades,
    status,
    sync,
)

router = APIRouter(prefix="/api")
router.include_router(auth.router)
router.include_router(assignments.router)
router.include_router(courses.router)
router.include_router(grades.router)
router.include_router(calendar.router)
router.include_router(status.router)
router.include_router(sync.router)
router.include_router(cache.router)
router.include_router(account.router)