"""Cloudflare Turnstile: guards login initiation only (ADR-0039 split).

Split out because the abuse control is OPTIONAL and because its secret must be
readable in exactly one place. When both keys are absent — the default, and the
case in every test — nothing here calls the network, so the login flow behaves
exactly as it did before Turnstile existed.

The verification is fail-CLOSED, and that is the whole point: if Turnstile
cannot be reached, login stops rather than continuing unprotected. A DDoS
control that silently turns itself off under load is worse than no control,
because the configuration still says it is on.
"""

import json
import logging
import urllib.parse

import httplib2
from pydantic import BaseModel

from core.config import TURNSTILE_SECRET_KEY, TURNSTILE_SITE_KEY
from gapi import oauth_transport

logger = logging.getLogger(__name__)

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class LoginStartIn(BaseModel):
    """The body of the JSON login-start call."""

    """Body of POST /api/auth/login/start (DDoS plan §17)."""

    token: str | None = None


def _turnstile_enabled() -> bool:
    """Both keys must be configured (config.TURNSTILE_ENABLED at startup).

    Read through the module attributes so tests can toggle the combination
    without re-importing the application.
    """
    return bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)


def _verify_turnstile(token: str) -> bool:
    """Verify one Turnstile response token against Cloudflare siteverify.

    Fail-closed: any transport/parse problem counts as a rejection. The
    token and the secret key are never logged (DDoS plan §21).
    """
    if not _turnstile_enabled():
        return True
    body = urllib.parse.urlencode({"secret": TURNSTILE_SECRET_KEY, "response": token}).encode(
        "utf-8"
    )
    http = httplib2.Http(timeout=oauth_transport.TOKEN_TIMEOUT_SECONDS)
    try:
        response, content = http.request(
            _TURNSTILE_VERIFY_URL,
            "POST",
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        payload = json.loads(content.decode("utf-8"))
    except Exception:  # noqa: BLE001 — fail closed on any verification error
        logger.warning("Turnstile verification failed: siteverify unreachable")
        return False
    return response.status == 200 and bool(payload.get("success"))
