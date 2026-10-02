"""How this deployment is exposed over HTTP: origins, hosts, cookies, HSTS.

Split out of ``config.py`` (ADR-0039) because these values answer one question —
"what does a legitimate request from this deployment look like?" — and they are
read almost exclusively by the HTTP edge (``core/proxy.py``,
``edge/origin_guard.py``, ``edge/cookies.py``, ``main.py``). The worker and the
sync scheduler never read them, so keeping them here means importing
``core.config`` for the OAuth or the sync knobs does not drag the whole public
surface in behind it.

``APP_ORIGIN`` and ``IS_PRODUCTION`` are read, not redefined: they belong to the
deployment identity that ``config.py`` establishes, and two sources of truth for
one origin is how a Host allow-list ends up disagreeing with the OAuth redirect.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from core.config import APP_ORIGIN, IS_PRODUCTION, _bool_env, _csv_env, _int_env
from core.origins import normalize_host, normalize_origin_list

logger = logging.getLogger(__name__)

# ------------------------------------------------- public-origin config (В§27/В§28)
#
# Hosted deployment: browser and API share one public origin, so the values
# below are about validating THAT origin, not about enabling cross-origin
# access. The production hostname is never hard-coded: it comes from
# GC_DASHBOARD_ALLOWED_HOSTS or, when that is unset, from the host of
# APP_BASE_URL — one place, the same one the OAuth redirect already uses.


FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _default_allowed_hosts() -> list[str]:
    """Hosts accepted in the Host header when none are configured.

    Production: only the public host of APP_BASE_URL. Development adds the
    loopback names so the local workflow keeps working unchanged.
    """
    hosts: list[str] = []
    if APP_ORIGIN:
        hosts.append(normalize_host(APP_ORIGIN) or "")
    if not IS_PRODUCTION:
        hosts.extend(["localhost", "127.0.0.1"])
    return [host for host in hosts if host]


_raw_allowed_hosts = os.environ.get("GC_DASHBOARD_ALLOWED_HOSTS")
ALLOWED_HOSTS: tuple[str, ...] = (
    tuple(
        dict.fromkeys(
            host
            for item in _csv_env("GC_DASHBOARD_ALLOWED_HOSTS")
            if (host := normalize_host(item)) is not None
        )
    )
    if _raw_allowed_hosts is not None
    else tuple(_default_allowed_hosts())
)

# CORS (В§27). Same-origin production traffic needs no permissive CORS, so the
# list is empty there and the middleware never echoes a foreign Origin.
# Development keeps the Vite dev-server origins; an intentional cross-origin
# frontend lists its exact origins in GC_DASHBOARD_CORS_ORIGINS. "*" is never
# valid — it is rejected below rather than combined with credentials.
_raw_cors_origins = os.environ.get("GC_DASHBOARD_CORS_ORIGINS")
CORS_ORIGINS: tuple[str, ...] = (
    normalize_origin_list(_csv_env("GC_DASHBOARD_CORS_ORIGINS"))
    if _raw_cors_origins is not None
    else (() if IS_PRODUCTION else tuple(FRONTEND_ORIGINS))
)

# Trusted reverse proxies (В§29). ``X-Forwarded-Proto`` is honoured only when
# the direct peer is in this list, so a client reaching the app directly can
# never change the scheme the session cookie is issued for. Empty means "no
# proxy in front": the request's own scheme is authoritative.
TRUSTED_PROXIES: tuple[str, ...] = tuple(_csv_env("GC_DASHBOARD_TRUSTED_PROXIES"))

# Session cookie (В§30/ADR-0020). Secure follows the request scheme unless
# COOKIE_SECURE is set explicitly; SameSite stays Lax because the OAuth
# callback arrives as a cross-site top-level redirect.
COOKIE_SECURE: bool | None = _bool_env("COOKIE_SECURE")
_COOKIE_SAMESITE_ALLOWED = ("lax", "strict", "none")
COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
_raw_samesite = os.environ.get("COOKIE_SAMESITE", "lax").strip().lower() or "lax"
if _raw_samesite in _COOKIE_SAMESITE_ALLOWED:
    COOKIE_SAMESITE = _raw_samesite  # type: ignore[assignment]
    if _raw_samesite == "none" and not COOKIE_SECURE:
        logger.warning(
            "COOKIE_SAMESITE=none requires a Secure cookie; setting COOKIE_SECURE=true."
        )
        COOKIE_SECURE = True
else:
    logger.warning(
        "COOKIE_SAMESITE=%r is not one of %s; falling back to 'lax'.",
        _raw_samesite,
        ", ".join(_COOKIE_SAMESITE_ALLOWED),
    )

# В§37: the optional __Host- prefix is exactly the constraint set this app
# already enforces for the session cookie (Secure + Path=/ + no Domain).
# Off by default so development over plain http keeps working; enabling it
# without a Secure cookie makes browsers REJECT the cookie (login breaks),
# which is warned about here rather than discovered at runtime.
COOKIE_HOST_PREFIX: str = (
    "__Host-" if bool(_bool_env("GC_DASHBOARD_COOKIE_HOST_PREFIX")) else ""
)
if COOKIE_HOST_PREFIX and COOKIE_SECURE is not True and not IS_PRODUCTION:
    logger.warning(
        "GC_DASHBOARD_COOKIE_HOST_PREFIX is set but COOKIE_SECURE is not "
        "true outside production: browsers reject __Host- cookies without "
        "the Secure attribute, so sign-in will fail on plain-http origins."
    )

# В§36/В§48: HSTS is opt-in. Send it only after HTTPS behaviour is confirmed
# (migration stage 10); the value is max-age seconds, 0 = header off.
# The reverse proxy may set the header instead — then keep this at 0 to
# avoid duplicates. Production .env.example ships 31536000 (1 year).
HSTS_MAX_AGE = _int_env("GC_DASHBOARD_HSTS_MAX_AGE", 0)

# --------------------------------------------- Turnstile (DDoS plan В§17)
# Cloudflare Turnstile guards ONLY login initiation, and only when both keys
# are configured — empty values (the default) keep the flow unchanged, so
# development and tests never talk to Cloudflare. The SECRET key is
# server-only: it never reaches the React bundle, logs or Git; the site key
# is public by design (it goes to the browser widget).
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "").strip()
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
# Enabled only when BOTH are present: a site key without a secret would show
# the challenge but let the backend skip verification (fail-open) — refuse
# that combination instead.
TURNSTILE_ENABLED = bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)
