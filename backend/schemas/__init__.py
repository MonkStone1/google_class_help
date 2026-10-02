"""Response models (Pydantic) — no SQL, no Google, no HTTP (ADR-0039).

An OpenAPI schema is a contract with the frontend: ``frontend/openapi.json`` is
committed and ``src/api-schema.d.ts`` is generated from it, so a field that
moves or disappears here breaks ``tsc``. Every model is therefore named after
what it carries, not after the endpoint that returns it.

- ``dashboard`` — the courses/assignments/grades/status payloads of the app.
- ``feedback``  — the ticket models, split into the user-facing projection and
  the administrator one (the second carries the author's real e-mail, which the
  first has no field for at all).
- ``admins``    — the administrator registry payloads (ADR-0036).

Handlers import from the module they actually need; nothing is re-exported here,
because ``from schemas.feedback import TicketOut`` must make the "regular user,
no author address" guarantee visible at the import site.

Budget: ≤ 400 lines per module.
"""
