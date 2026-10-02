"""Infrastructure: configuration, paths, logging, metrics, crypto (ADR-0039).

The bottom of the dependency graph (``core/ ← db/ ← gapi/ ← sync/ ← api/routes
← main.py``, docs/BACKEND_STRUCTURE.md). Nothing in this package knows about
FastAPI, SQLAlchemy sessions, Google or the domain — the three rules below are
what keep that true, and ``tests/test_backend_structure.py`` enforces them.

1. **No domain.** A value that only makes sense to a Classroom user belongs in
   ``db/``, ``gapi/`` or ``api/``, not here.
2. **No framework.** ``fastapi``/``starlette`` are HTTP concerns and live in
   ``api/`` and ``edge/``.
3. **Configuration is read through the module object.** Consumers write
   ``config.RATE_LIMIT_*``, never ``from config import RATE_LIMIT_*``: a
   by-value import makes a second copy of the constant, and a test that patches
   ``core.config`` stops being seen by the module that copied it. The
   exceptions are the pure value bundles a consumer genuinely re-exports (the
   session TTLs, the origins of a cookie), and each is commented where it is
   declared.

- ``config``          — every environment-derived constant, parsed once.
- ``origins``         — origin/host normalization (pure functions).
- ``logging_filters`` — access-log query redaction and secret scrubbing.
- ``metrics``         — in-process counters (§60).
- ``rate_limit``      — token buckets behind the abuse surfaces (ADR-0027).
- ``capacity``        — the planning arithmetic of ADR-0027/§88.
- ``crypto``          — Fernet encryption of the stored OAuth tokens.
- ``proxy``           — trusted reverse-proxy decisions for the HTTP boundary.

Budget: ≤ 400 lines per module (``tests/test_backend_structure.py``).
"""

# The modules are imported individually (``from core import config``); importing
# this package must not pull FastAPI, the database or any domain module, so
# nothing is re-exported here — a sibling module reached through the package
# object is the pattern the rest of the backend uses.
