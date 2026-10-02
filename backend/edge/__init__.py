"""The production edge (ADR-0039): everything that stands IN FRONT of the app.

``main.py`` used to build four nested middleware closures, the Host/Origin
guard, the CSP and the static mount inline, which made ``create_app`` 310
lines long and left each piece reachable only through a full app. Split out,
each one is a named factory a test can build and call on its own.

Order matters and is decided by ``main.py``, not here: Starlette runs the
LAST registered middleware outermost, so the call order in ``create_app``
(throttle → session gate → CORS → Host/Origin guard → security headers) is
the actual execution order. A module here adds exactly one middleware; the
assembly stays visible in one place.

Budget: ≤ 400 lines per module (docs/BACKEND_STRUCTURE.md).

- ``lifespan`` — DB init and the background schedules (ADR-0015, ADR-0023).
- ``middleware`` — the middleware factories themselves.
- ``origin_guard`` — the Host/Origin allow-list decisions (§27/§28).
- ``security`` — the Content-Security-Policy of the hosted edge (§48).
- ``static`` — the built SPA with its client-side-routing fallback (§35).
"""

# The modules are imported by ``main.py`` individually; importing this package
# must not pull FastAPI, the database or any domain module, so nothing is
# re-exported here (a sibling module reached through the package object is the
# pattern the rest of the backend uses — see docs/BACKEND_STRUCTURE.md).
