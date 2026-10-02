"""Shared Google OAuth scopes and token-endpoint I/O.

Migration stage 8 (§32/§33): the middle layer both deployment modes share.
Neither mode's startup imports the other mode's authentication flow, but
both redeem and refresh authorization codes through this one transport
("единый HTTPS-транспорт", ADR-0019):

    hosted_auth.py   (web OAuth + sessions, ADR-0020)  ─┐
    auth.py          (desktop loopback flow, ADR-0019) ─┴→  this module
    google_credentials.py (per-user layer, §15)        ───→  this module
                                                             ↓
                                              Google token endpoint

Contents are deliberately narrow: no browser flow, no local callback
server, no token storage, no environment decisions — only

- the read-only Classroom scope list and the OIDC identity scopes used by
  userinfo (ADR-0002, identical in both modes),
- the token-endpoint exchange (``post_token_request``),
- payload → ``Credentials`` parsing (``credentials_from_payload``),
- the httplib2-preferred refresh (``refresh_credentials``).

The module imports nothing from ``auth``/``hosted_auth``/``launcher``, so
the hosted service never loads desktop authentication code (§32/§74).
"""

import json
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone

import google_auth_httplib2
import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

# Shared OAuth scopes for both deployment modes. The OIDC identity scopes are
# included because the hosted flow calls Google's userinfo endpoint to resolve
# the stable `sub` and the local profile (`name`/`email`) before Classroom sync.
# None of these scopes grants Classroom write access.

# Read-only Classroom scopes for both modes. The student route needs
# courses.readonly plus student-submissions.me.readonly. Teacher mode adds two
# read-only scopes:
#
# - classroom.student-submissions.students.readonly lets a teacher list ALL
#   coursework of a course (courses.courseWork.list) and read every
#   student's submissions (studentSubmissions.list). This is the scope
#   Google actually grants for the teacher view: requesting the older
#   coursework.students.readonly makes the consent screen swap it for this
#   one ("Scope has changed" warning) — the `.students.` coursework and
#   submissions scopes were merged, the same way `.me.` ones were in
#   ADR-0002. Requesting coursework.students.readonly would therefore be
#   granted never, and the token subset check in
#   get_valid_credentials() would sign the user out on every launch.
# - classroom.rosters.readonly lists the students enrolled in a course.
#
# Every Classroom scope stays read-only — the app never writes to Google
# Classroom. The OIDC identity scopes above only identify the signed-in user.
SCOPES = [
    "openid",
    "profile",
    "email",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
]

# Socket timeout for the token endpoint (both the code exchange and refresh).
TOKEN_TIMEOUT_SECONDS = 30


def _httplib2_request() -> google_auth_httplib2.Request:
    """Google API request adapter over httplib2 (the app's transport)."""
    return google_auth_httplib2.Request(httplib2.Http(timeout=TOKEN_TIMEOUT_SECONDS))


def refresh_credentials(creds: Credentials) -> None:
    """Refresh the access token, preferring the httplib2 transport.

    requests/urllib3 is not used anywhere else in this application, so a
    broken urllib3 stack must not be able to sign the user out while the
    Classroom calls themselves would still work (ADR-0019).
    """
    attempts = (("httplib2", _httplib2_request), ("requests", Request))
    errors: list[str] = []
    for name, make_request in attempts:
        try:
            creds.refresh(make_request())
            logger.info("Google credentials refreshed via %s.", name)
            return
        except Exception as exc:  # noqa: BLE001 - try the next transport
            errors.append(f"{name}: {exc!r}")
            logger.warning("Refreshing via %s failed: %r", name, exc)
    raise RuntimeError(
        "Could not refresh the Google credentials (" + "; ".join(errors) + ")"
    )


def post_token_request(
    client_config: dict, code: str, redirect_uri: str, code_verifier: str | None
) -> dict:
    """Redeem the authorization code over httplib2; returns the token payload."""
    fields = {
        "code": code,
        "client_id": client_config["client_id"],
        "client_secret": client_config["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    if code_verifier:
        fields["code_verifier"] = code_verifier
    http = httplib2.Http(timeout=TOKEN_TIMEOUT_SECONDS)
    try:
        response, content = http.request(
            client_config["token_uri"],
            "POST",
            body=urllib.parse.urlencode(fields),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    except Exception as exc:  # report the transport, not a bare socket error
        logger.exception("Token exchange over httplib2 failed")
        raise RuntimeError(f"Token exchange over httplib2 failed: {exc!r}") from exc
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Token endpoint answered with status {response.status} and unreadable body."
        ) from exc
    if response.status != 200:
        detail = payload.get("error_description") or payload.get("error") or payload
        raise RuntimeError(
            f"Token endpoint rejected the sign-in ({response.status}): {detail}"
        )
    return payload


def credentials_from_payload(client_config: dict, payload: dict) -> Credentials:
    """Build credentials from the token endpoint's answer (untrusted input)."""
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("The Google token endpoint returned no access token.")
    expiry = None
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, str)):
        try:
            expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                seconds=int(expires_in)
            )
        except ValueError:
            # No usable lifetime in the answer: google-auth then treats the
            # token as valid until Google rejects it, which is still better
            # than failing a sign-in that did work.
            logger.warning(
                "Token endpoint returned an unusable expires_in: %r", expires_in
            )
    elif expires_in is not None:
        logger.warning("Token endpoint returned an unusable expires_in: %r", expires_in)
    return Credentials(
        token=token,
        refresh_token=payload.get("refresh_token"),
        token_uri=client_config["token_uri"],
        client_id=client_config["client_id"],
        client_secret=client_config["client_secret"],
        scopes=SCOPES,
        expiry=expiry,
    )
