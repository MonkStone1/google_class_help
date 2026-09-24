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

Stage 9 (§42) adds :class:`RedactSecretsFilter`: hosted application logs go
to stdout/stderr (Docker/systemd capture), so any record that accidentally
carries token/cookie/secret material is scrubbed before it is emitted.
The filter redacts ``key=value``/``key: value`` pairs and bare token
shapes (``ya29.``, ``ya29:``, ``glpat-``, ``gho_``, long Bearer strings)
while leaving operational fields (user ids, counts, durations) intact.
Structured extra fields are redacted in place; the log call itself never
raises because of it.
"""

import logging
import re

# From the first "?" to the next whitespace: in an access-log line the path
# with query is always followed by the HTTP-version token ("... ?a=1 HTTP/1.1").
_QUERY_IN_MESSAGE = re.compile(r"\?\S*")

# Stage 9 (§42): credential-shaped material that must never reach stdout.
# Keyed pairs first (case-insensitive), then bare Google token shapes.
_SECRET_PAIR = re.compile(
    r"(?i)\b(access_token|refresh_token|id_token|client_secret|authorization"
    r"|cookie|set-cookie|session|api[_-]?key)\b\s*[:=]\s*([^\s;,}]+)"
)
_BEARER = re.compile(r"(?i)\b(bearer)\b\s+([A-Za-z0-9\-._~+/=]{8,})")
_BARE_TOKEN = re.compile(
    r"\b(ya29\.[A-Za-z0-9\-_]+|ya29:[A-Za-z0-9\-_]+|glpat-[A-Za-z0-9\-_]+|gho_[A-Za-z0-9]+)\b"
)
_REDACTED = r"\1=[REDACTED]"
_REDACTED_BEARER = r"\1 [REDACTED]"


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


def redact_secrets_in_text(text: str) -> str:
    """Scrub credential-shaped material from one log string (§42)."""
    redacted = _SECRET_PAIR.sub(_REDACTED, text)
    redacted = _BEARER.sub(_REDACTED_BEARER, redacted)
    return _BARE_TOKEN.sub("[REDACTED]", redacted)


class RedactSecretsFilter(logging.Filter):
    """Scrub token/secret material from application log records (§42).

    Hosted logs go to stdout/stderr where Docker captures them; a stray
    ``logger.info("token=%s", access_token)`` must degrade to
    ``token=[REDACTED]`` instead of a credential leak. Operates on the
    rendered message plus string-valued ``record.args``; never raises.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - logging must never raise
            return True
        redacted = redact_secrets_in_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        try:
            args = record.args
            if isinstance(args, dict):
                for key, value in list(args.items()):
                    if isinstance(value, str):
                        scrubbed = redact_secrets_in_text(value)
                        if scrubbed != value:
                            args[key] = scrubbed
            elif isinstance(args, tuple):
                scrubbed_args = tuple(
                    redact_secrets_in_text(item) if isinstance(item, str) else item
                    for item in args
                )
                if scrubbed_args != args:
                    record.args = scrubbed_args
        except Exception:  # noqa: BLE001 - logging must never raise
            return True
        return True


def install_secret_redaction(
    logger_names: tuple[str, ...] = (
        "api",
        "hosted_auth",
        "google_credentials",
        "sync_service",
        "sync_scheduler",
        "sync_worker",
        "oauth_transport",
        "main",
    ),
) -> None:
    """Attach the secret filter to the app loggers (idempotent, §42)."""
    for name in logger_names:
        target = logging.getLogger(name)
        if not any(
            isinstance(existing, RedactSecretsFilter) for existing in target.filters
        ):
            target.addFilter(RedactSecretsFilter())
