"""Storage: engine, sessions and the mapped models (ADR-0039).

One direction only: ``db/`` reads ``core/`` and knows nothing about ``gapi/``,
``sync/`` or the HTTP layer. The engine is built from configuration here and
the models are pure SQLAlchemy — no business rule lives in either file.

- ``session``        — engine, ``SessionLocal``, ``Base``, ``get_db``, ``init_db``.
- ``models/classroom`` — the Google Classroom cache tables (ADR-0003).
- ``models/accounts`` — users, sessions, OAuth tokens and login states.
- ``models/feedback`` — the ticket tables (ADR-0035).
- ``models/admins``   — the administrator registry (ADR-0036).

A new table is registered in three places, and missing one is silent: the module
itself, ``db/session.py::_import_models`` (which ``init_db`` calls) and
``migrations/env.py`` (so a bare ``alembic`` CLI run sees the same metadata).

Budget: ≤ 400 lines per module.
"""

# Nothing is re-exported: ``db.models`` imports its submodules for the Alembic
# metadata, but application code must name the table module it uses, so a
# ``Course`` is always ``db.models.classroom.Course``.
