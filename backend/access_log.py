"""Uvicorn access-log query redaction (migration stage 8, §36).

The OAuth callback arrives as ``GET /api/auth/callback?code=...&state=...``;
an authorization code in an access log is a credential-bearing URL, and §36
forbids logging or caching such URLs. This module strips every query
string from ``uvicorn.access`` records before any handler sees them, so
the log keeps the useful line (client, method, path, status) without the
query.

The filter is attached by logger NAME: ``logging.getLogger("uvicorn.access")``
resolves to the same object uvicorn logs through, whether uvicorn created
it before or after this module ran — installation order does not matter,
and calling :func:`install_query_redaction` twice is a no-op.
"""

import logging
import re

# From the first "?" to the next whitespace: in an access-log line the path
# with query is always followed by the HTTP-version token ("... ?a=1 HTTP/1.1").
_QUERY_IN_MESSAGE = re.compile(r"\?\S*")


class RedactQueryFilter(logging.Filter):
    """Rewrite a record's message with its query string removed."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - logging must never raise
            return True
        redacted = _QUERY_IN_MESSAGE.sub("", message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def install_query_redaction() -> None:
    """Attach the redaction filter to the uvicorn access logger (idempotent)."""
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(existing, RedactQueryFilter) for existing in logger.filters):
        logger.addFilter(RedactQueryFilter())
