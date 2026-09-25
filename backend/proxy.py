"""Trusted reverse-proxy helpers for the hosted HTTP boundary.

Uvicorn may sit behind Caddy/Nginx, but forwarded headers are useful only
when the immediate peer is an explicitly configured proxy.  This module keeps
that trust decision in one place and exposes the effective public origin used
by host/origin validation and cookie flags.
"""

import ipaddress
import logging

from fastapi import Request

from config import (
    ALLOWED_HOSTS,
    TRUSTED_PROXIES,
    canonical_origin,
    host_and_port_from_value,
)

logger = logging.getLogger(__name__)


def _first_forwarded_value(value: str) -> str | None:
    """Return the first value from a comma-separated proxy header."""
    first = value.split(",", 1)[0].strip()
    return first or None


def _trusted_proxy_entry(
    entry: str,
) -> (
    ipaddress.IPv4Address
    | ipaddress.IPv6Address
    | ipaddress.IPv4Network
    | ipaddress.IPv6Network
    | None
):
    """Parse one trusted-proxy IP/CIDR entry; invalid entries are rejected."""
    try:
        if "/" in entry:
            return ipaddress.ip_network(entry, strict=False)
        return ipaddress.ip_address(entry)
    except ValueError:
        logger.warning(
            "Ignoring malformed GC_DASHBOARD_TRUSTED_PROXIES entry %r.", entry
        )
        return None


def _entry_contains(
    trusted: ipaddress.IPv4Address
    | ipaddress.IPv6Address
    | ipaddress.IPv4Network
    | ipaddress.IPv6Network,
    peer: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    if isinstance(trusted, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
        return peer in trusted
    return peer == trusted


def peer_is_trusted_proxy(request: Request) -> bool:
    """Return whether the immediate peer is a configured reverse proxy."""
    if not TRUSTED_PROXIES or request.client is None:
        return False
    try:
        peer = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return any(
        _entry_contains(trusted, peer)
        for entry in TRUSTED_PROXIES
        if (trusted := _trusted_proxy_entry(entry)) is not None
    )


def external_scheme(request: Request) -> str:
    """Return the public http/https scheme without trusting client headers.

    When Uvicorn has already applied trusted proxy headers, ``request.url.scheme``
    is already the external scheme.  When it has not (for example in tests or
    a deployment that leaves proxy handling to the app), a trusted peer may
    supply ``X-Forwarded-Proto``.  An untrusted or malformed header is ignored.
    """
    forwarded = _first_forwarded_value(request.headers.get("x-forwarded-proto", ""))
    if forwarded in {"http", "https"} and peer_is_trusted_proxy(request):
        return forwarded
    return request.url.scheme


def effective_authority(
    request: Request,
) -> tuple[str, int | None] | None:
    """Return the validated public ``(host, port)`` authority.

    ``X-Forwarded-Host`` is accepted only from a trusted proxy and only when
    its host is on the configured allow-list.  Otherwise the ordinary Host
    header is authoritative.  Malformed or disallowed authorities fail closed.
    """
    host_header = request.headers.get("host", "")
    authority = host_and_port_from_value(host_header)
    if authority is None:
        return None

    if peer_is_trusted_proxy(request):
        forwarded_host = _first_forwarded_value(
            request.headers.get("x-forwarded-host", "")
        )
        if forwarded_host:
            forwarded_authority = host_and_port_from_value(forwarded_host)
            if forwarded_authority is None:
                return None
            if forwarded_authority[0] not in ALLOWED_HOSTS:
                return None
            return forwarded_authority
    return authority


def public_origin(request: Request) -> str | None:
    """Return the normalized public origin for same-origin checks."""
    authority = effective_authority(request)
    if authority is None:
        return None
    return canonical_origin(external_scheme(request), authority[0], authority[1])


def client_ip(request: Request) -> str:
    """Best-effort client identity for abuse throttling (stage 9, section 39).

    The direct TCP peer by default; the leftmost X-Forwarded-For entry only
    when that peer is a configured reverse proxy (same trust rule as the
    scheme/host helpers above) — otherwise a client could pick any identity
    and dodge the bucket. The value is a throttle key only, never an auth
    decision.
    """
    peer = request.client.host if request.client is not None else "unknown"
    if peer_is_trusted_proxy(request):
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded
    return peer
