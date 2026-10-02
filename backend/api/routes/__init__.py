"""One module per HTTP resource (ADR-0039).

A handler here does dependency resolution, validation and HTTP mapping, then
delegates: SQL lives in ``api/queries/*``, 404/403 mapping in ``api/guards.py``,
identity in ``api/identity.py``, Google and cache writes nowhere near.

Budget: ≤ 250 lines per module (docs/BACKEND_STRUCTURE.md). When one grows
past that, the next change is either a new module named after the resource or
an extracted query — not a bigger file.

Two invariants that this package must not break:

- every handler is reached through THIS module object, never through a direct
  ``from api.routes.x import handler`` elsewhere, so tests patching
  ``api.identity.*`` keep working;
- no ``tags=`` are added and no handler is renamed without regenerating
  ``frontend/openapi.json`` — ``operationId`` is derived from the function
  name (``tests/test_api_contract.py``).
"""