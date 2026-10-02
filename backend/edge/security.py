"""Content-Security-Policy of the hosted edge (ADR-0026, §48).

A pure function of the Turnstile site key, so the policy can be asserted
without starting an app. The header is attached by
``edge.middleware.install_security_headers``, which reads
``CONTENT_SECURITY_POLICY`` from here through the module object.
"""

from core import config


# §48: CSP matched to the ACTUAL React bundle — every origin is same-origin
# because the frontend only calls the local /api (verified by the §49 secret
# scan: no secret-shaped URLs in the source tree). The pre-paint script of
# index.html lives in /prepaint-init.js (no inline script), so script-src needs
# no hash and no 'unsafe-inline'. style-src keeps 'unsafe-inline' for React
# inline styles. Top-level navigation to accounts.google.com is not a
# fetch/frame/form and is not restricted by these directives; the OAuth
# redirect is a server-side 302. frame-ancestors 'none' answers the
# framing question together with X-Frame-Options below.
#
# Turnstile (DDoS plan §17, stage 10): when TURNSTILE_SITE_KEY is set the
# widget loads its script and iframe from challenges.cloudflare.com — those
# two origins are then added to script-src/frame-src and nowhere else.
def _build_content_security_policy(site_key: str) -> str:
    """CSP for the hosted edge (§48).

    Same-origin by default; when Turnstile is configured (site key present)
    the widget's origin is additionally allowed for scripts and frames —
    and never anywhere else.
    """
    turnstile = " https://challenges.cloudflare.com" if site_key else ""
    frame = f"frame-src 'self'{turnstile}; " if turnstile else ""
    return (
        "default-src 'self'; "
        f"script-src 'self'{turnstile}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        f"{frame}"
        "frame-ancestors 'none'"
    )


CONTENT_SECURITY_POLICY = _build_content_security_policy(config.TURNSTILE_SITE_KEY)
