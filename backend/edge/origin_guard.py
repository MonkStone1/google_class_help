"""Host/Origin allow-list decisions for the HTTP boundary (§27/§28).

These are pure functions over configuration and a request: they decide, they
do not enforce. The middleware that CALLS them lives in
``edge.middleware.install_host_guard`` — keeping the policy here means the
answer to "is this host/origin acceptable?" can be tested without an app,
which is exactly what ``tests/test_stage7_frontend_config.py`` does.

The configuration is read through the ``config`` module object rather than
imported by value, so a test that patches ``config.ALLOWED_HOSTS`` changes
what these functions see. ``main.ALLOWED_HOSTS`` no longer exists: the
monkeypatch targets moved here with the code (ADR-0039 stage 2).
"""

from fastapi import Request

import config
from proxy import effective_authority, host_and_port_from_value, public_origin

# Migration stage 7 (§27/§28): the accepted Host names are configuration, not
# code. Desktop development keeps localhost/127.0.0.1 (the default), the
# hosted service answers on its public domain (from
# GC_DASHBOARD_ALLOWED_HOSTS or the host of APP_BASE_URL). The guard runs in
# BOTH modes: hosted mode has real authentication, but a correct Host check is
# still the first line of defence against DNS-rebinding style requests.


def _host_allowed(host_header: str) -> bool:
    """Return whether a Host-header authority is on the configured allow-list."""
    authority = host_and_port_from_value(host_header)
    return authority is not None and authority[0] in config.ALLOWED_HOSTS


def _request_host_allowed(request: Request) -> bool:
    """Validate the effective public authority, including trusted proxies."""
    authority = effective_authority(request)
    return authority is not None and authority[0] in config.ALLOWED_HOSTS


def _origin_allowed(origin: str, request: Request | None = None) -> bool:
    """Allow only exact configured origins or the request's own origin.

    Hostname-only matching is deliberately not enough: scheme and port are
    part of origin identity.  Development keeps the Vite origins; production
    requires an explicit CORS entry for a cross-origin frontend.
    """
    normalized = config.normalize_origin(origin)
    if normalized is None:
        return False
    if normalized in config.CORS_ORIGINS:
        return True
    if not config.IS_PRODUCTION and normalized in config.FRONTEND_ORIGINS:
        return True
    if request is None:
        return config.APP_ORIGIN is not None and normalized == config.APP_ORIGIN
    request_origin = public_origin(request)
    return request_origin is not None and normalized == request_origin
