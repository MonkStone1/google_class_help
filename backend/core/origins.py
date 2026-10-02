"""Origin and host normalization — pure functions (ADR-0039).

Split out of ``config.py`` because these are RULES, not values: everything here
answers "is this string the same origin as that one", and none of it reads the
environment. Keeping them apart means the allow-list constants in ``config.py``
are visibly derived from functions that can be tested without a configured
process, and the ``Host``/``Origin`` guard can be reasoned about on its own.

The rules that matter, and why each is a rule rather than a convenience:

- an origin is ``scheme://host[:port]`` with NO path, query, fragment or
  userinfo — a browser never sends those in an ``Origin`` header, so accepting
  them would make two different strings compare as one origin;
- default ports are dropped, so ``https://host:443`` equals ``https://host``;
- an IPv6 literal is bracketed, so ``[::1]:8000`` parses;
- anything malformed returns ``None`` rather than a best guess — the callers
  fail closed on ``None`` and a permissive guess here becomes a 403 that is very
  hard to reproduce.
"""

import logging
import urllib.parse

logger = logging.getLogger(__name__)


def canonical_origin(scheme: str, hostname: str, port: int | None) -> str | None:
    """Return a normalized ``scheme://host[:port]`` origin.

    Invalid schemes/hosts and non-default ports that cannot be represented are
    rejected. Default ports are omitted so ``https://host:443`` and
    ``https://host`` compare equal.
    """
    scheme = scheme.strip().lower()
    hostname = hostname.strip().lower().rstrip(".")
    if scheme not in {"http", "https"} or not hostname:
        return None
    try:
        normalized_port = int(port) if port is not None else None
    except (TypeError, ValueError):
        return None
    if normalized_port is not None and not 1 <= normalized_port <= 65535:
        return None
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if normalized_port is not None and not (
        (scheme == "http" and normalized_port == 80)
        or (scheme == "https" and normalized_port == 443)
    ):
        hostname = f"{hostname}:{normalized_port}"
    return f"{scheme}://{hostname}"


def origin_from_value(value: str) -> str | None:
    """Normalize an origin value, rejecting paths, credentials and fragments."""
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return canonical_origin(parsed.scheme, parsed.hostname, port)


def host_from_value(value: str) -> str | None:
    """Normalize a host or URL authority to a hostname only."""
    authority = host_and_port_from_value(value)
    return authority[0] if authority is not None else None


def host_and_port_from_value(value: str) -> tuple[str, int | None] | None:
    """Return a normalized ``(host, port)`` authority.

    This is shared by the Host guard and trusted-proxy handling so both use
    the same IPv6, port and malformed-input rules.
    """
    raw = value.strip()
    if not raw or any(character in raw for character in (",", "\r", "\n")):
        return None
    try:
        if "://" in raw:
            parsed = urllib.parse.urlsplit(raw)
            if parsed.path or parsed.query or parsed.fragment:
                return None
        else:
            parsed = urllib.parse.urlsplit(f"//{raw}")
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    if port is not None and not 1 <= port <= 65535:
        return None
    return parsed.hostname.strip().lower().rstrip("."), port


def normalize_host(value: str) -> str | None:
    """Public host-normalization helper used by middleware and tests."""
    authority = host_and_port_from_value(value)
    return authority[0] if authority is not None else None


def normalize_origin(value: str) -> str | None:
    """Public origin-normalization helper used by middleware and tests."""
    return origin_from_value(value)


def normalize_origin_list(values: list[str]) -> tuple[str, ...]:
    """Normalize an origin allow-list and remove the credentialed wildcard."""
    normalized: list[str] = []
    wildcard = False
    for value in values:
        if value == "*":
            wildcard = True
            continue
        origin = origin_from_value(value)
        if origin is not None:
            normalized.append(origin)
    if wildcard:
        logger.warning(
            "An origin allow-list contained '*'; ignoring it — a wildcard "
            "origin is never combined with credentialed cookies (§27)."
        )
    return tuple(dict.fromkeys(normalized))