"""Google OAuth 2.0 authentication for a local installed application.

The OAuth client configuration comes from, in order:

1. an explicit file via ``GC_DASHBOARD_CREDENTIALS`` (development);
2. ``backend/credentials.json`` (development fallback, git-ignored);
3. the embedded client config generated at build time
   (``embedded_secrets.py``, produced by build_secrets.py) — the
   production path: no plaintext credentials file is shipped or written.
   The blob is base64, not encrypted: it keeps the plaintext out of the
   shipped build, nothing more (review §2.5).

The issued token is cached per user in ``DATA_DIR/token.json``
(``%LOCALAPPDATA%\\GoogleClassHelp\\token.json`` in a compiled build)
and refreshed automatically. No secrets are stored in source code.

The consent flow is owned by this module rather than by
``InstalledAppFlow.run_local_server`` (ADR-0019):

- the loopback callback server is a plain ``http.server`` bound to
  ``127.0.0.1``; the redirect URI advertises the very address that was
  bound, so the browser cannot deliver the callback to another interface
  (``run_local_server`` advertises ``localhost`` while binding IPv4 only),
  and no ``SO_EXCLUSIVEADDRUSE`` is set — google-auth-oauthlib sets it on
  Windows and Wine rejects the option with WSAEINVAL;
- the consent URL is logged and published through ``login_status()``, so a
  user whose shell cannot open a browser (Wine) can still complete sign-in;
- the token exchange tries the library transport (requests/urllib3) first
  and falls back to httplib2, the transport every other Google call in this
  application already uses.
"""

import json
import logging
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import cast

import google_auth_httplib2
import httplib2
from fastapi import HTTPException
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from config import CREDENTIALS_FILE, TOKEN_FILE

logger = logging.getLogger(__name__)

# Read-only scopes for both modes. The student route needs courses.readonly
# plus student-submissions.me.readonly. Teacher mode adds two read-only
# scopes:
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
# Every scope stays read-only — the app never writes to Google Classroom.
SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
]

# Seconds the user has to finish the consent screen before the callback
# server gives up, and the socket timeout for the token endpoint.
CONSENT_TIMEOUT_SECONDS = 300
TOKEN_TIMEOUT_SECONDS = 30
# Never block the callback wait on a silent socket (browsers preconnect).
CALLBACK_POLL_SECONDS = 0.5
CALLBACK_SOCKET_TIMEOUT_SECONDS = 10

_SUCCESS_PAGE = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    "<title>GoogleClassHelp</title></head>"
    '<body style="font-family:system-ui,sans-serif;padding:40px">'
    "<h2>Google sign-in completed</h2>"
    "<p>You can close this window and return to the dashboard.</p>"
    "</body></html>"
)

_login_lock = threading.Lock()
_login_state: dict = {"in_progress": False, "error": None, "auth_url": None}

# Serializes token refreshes (review §1.4): the refresh is a network call
# (up to ~30 s), so two API threads hitting an expired token at once must
# not both POST to the token endpoint. The login lock above protects only
# the tiny _login_state dict and never covers network I/O.
_refresh_lock = threading.Lock()


def _client_config() -> dict | None:
    """Load the OAuth client configuration, in memory only.

    Never writes a plaintext credentials.json on the user's machine.
    Returns None when no configuration is available.
    """
    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    try:
        # Generated by build_secrets.py; compiled into the executable.
        # Dynamic import: the module exists only in production builds.
        import importlib

        module = importlib.import_module("embedded_secrets")
        return module.get_client_config()
    except ImportError:
        return None


def load_credentials() -> Credentials | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    except Exception:  # noqa: BLE001 - a corrupt token file must not crash the API
        return None


def _save_credentials(creds: Credentials) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")


def _httplib2_request() -> google_auth_httplib2.Request:
    """Google API request adapter over httplib2 (the app's transport)."""
    return google_auth_httplib2.Request(httplib2.Http(timeout=TOKEN_TIMEOUT_SECONDS))


def _refresh_credentials(creds: Credentials) -> None:
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


def get_valid_credentials() -> Credentials | None:
    """Return valid credentials, refreshing them when possible.

    A cached token that lacks any of the required scopes (e.g. issued before
    the scope list changed) is treated as not authenticated so the user is
    sent through consent again instead of getting 403s from Google.
    """
    creds = load_credentials()
    if not creds:
        return None
    if not set(SCOPES).issubset(set(creds.scopes or [])):
        logout()
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        with _refresh_lock:  # only one thread actually refreshes (§1.4)
            # Double-check: while we waited, another thread may already have
            # refreshed the token on disk — reload instead of refreshing twice.
            creds = load_credentials() or creds
            if creds.valid:
                return creds
            try:
                _refresh_credentials(creds)
            except Exception:  # noqa: BLE001 - refresh failures are reported as signed-out
                return None
            _save_credentials(creds)
        return creds
    return None


class _CallbackHandler(BaseHTTPRequestHandler):
    """Captures the OAuth redirect; every other request is ignored.

    Browsers ask for /favicon.ico (and may preconnect) before or besides the
    redirect, so the handler must not treat the first request as the answer.
    """

    server_version = "GoogleClassHelp"
    # A socket that connects and stays silent must not stall the wait loop.
    timeout = CALLBACK_SOCKET_TIMEOUT_SECONDS

    def do_GET(self) -> None:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        server = cast("_CallbackServer", self.server)
        if "code" in params or "error" in params:
            server.params = params
            self._respond(200, _SUCCESS_PAGE)
        else:
            self._respond(404, "<!doctype html><title>Not found</title>Not found")

    def _respond(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        logger.debug("OAuth callback request: " + format, *args)


class _CallbackServer(HTTPServer):
    """Loopback server that waits for exactly one OAuth redirect.

    Plain ``http.server`` on purpose: no wsgiref, no ``SO_EXCLUSIVEADDRUSE``
    (google-auth-oauthlib's ``_ExclusiveWSGIServer`` sets it on Windows, and
    Wine fails that call with WSAEINVAL — errno 22).
    """

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _CallbackHandler)
        self.params: dict[str, list[str]] | None = None
        self.timeout = CALLBACK_POLL_SECONDS

    @property
    def redirect_uri(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/"

    def wait_for_callback(self, timeout_seconds: int) -> dict[str, list[str]]:
        """Block until the redirect arrives; raise TimeoutError if it never does."""
        deadline = time.monotonic() + timeout_seconds
        while self.params is None:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"No Google redirect arrived within {timeout_seconds} seconds."
                )
            # Returns after one request, or after `self.timeout` when idle.
            try:
                self.handle_request()
            except OSError as exc:
                # Browsers open and drop connections (preconnect, cancelled
                # favicon fetch); that must not abort the whole wait.
                logger.debug("Ignoring a failed callback connection: %r", exc)
        return self.params

    def handle_error(self, request, client_address) -> None:
        """A browser that drops the callback connection is not an incident.

        The default handler prints a traceback to stderr; in this flow a reset
        connection is routine browser behaviour.
        """
        logger.debug("Callback connection from %s ended early.", client_address)


def _post_token_request(
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


def _credentials_from_payload(client_config: dict, payload: dict) -> Credentials:
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


def _exchange_code(flow: InstalledAppFlow, code: str, redirect_uri: str) -> Credentials:
    """Redeem the code: library transport first, httplib2 as the fallback.

    The library posts through requests/urllib3. Under Wine that stack has
    been observed to fail with an unmapped socket error (errno 22) right
    after consent, while httplib2 — already the transport for every
    Classroom call — keeps working, so a transport-level failure is retried
    on httplib2 instead of failing the whole sign-in (ADR-0019).
    """
    try:
        flow.fetch_token(code=code)
        logger.info("Authorization code exchanged via requests.")
        return cast(Credentials, flow.credentials)
    except OSError as exc:
        logger.warning(
            "Token exchange via requests failed (%r); retrying over httplib2.", exc
        )
    payload = _post_token_request(
        flow.client_config, code, redirect_uri, flow.code_verifier
    )
    logger.info("Authorization code exchanged via httplib2.")
    return _credentials_from_payload(flow.client_config, payload)


def _run_consent_flow(config: dict) -> Credentials:
    """Run consent against our own loopback server and return credentials."""
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    with _CallbackServer() as server:
        redirect_uri = server.redirect_uri
        flow.redirect_uri = redirect_uri
        # The library turns this into an offline (refresh-token) request and
        # adds PKCE parameters.
        auth_url, state = flow.authorization_url()
        logger.info("Google sign-in: waiting for the redirect on %s", redirect_uri)
        logger.info("Google sign-in URL: %s", auth_url)
        with _login_lock:
            _login_state["auth_url"] = auth_url
        if not webbrowser.open(auth_url, new=2, autoraise=True):
            logger.warning(
                "No browser could be opened for the consent page; "
                "the URL is in the dashboard and in this log."
            )
        params = server.wait_for_callback(CONSENT_TIMEOUT_SECONDS)

    # The code came back through the loopback socket; validate the state
    # here, because the code-only exchange below does not check it (the
    # library's own helper passes the whole response URI instead).
    returned_state = (params.get("state") or [""])[0]
    if returned_state != state:
        raise RuntimeError(
            "Google sign-in state mismatch: the redirect does not belong to this attempt."
        )
    if "error" in params:
        detail = (params.get("error_description") or params["error"])[0]
        raise RuntimeError(f"Google refused the sign-in: {detail}")
    code = (params.get("code") or [""])[0]
    if not code:
        raise RuntimeError("The Google redirect carried no authorization code.")
    return _exchange_code(flow, code, redirect_uri)


def _run_login_flow() -> None:
    """Executed in a background thread: opens the browser for consent.

    ``in_progress`` is already set by :func:`start_login` under the lock;
    this flow only clears it (review §1.5).
    """
    try:
        config = _client_config()
        if config is None:
            raise RuntimeError("OAuth client configuration not available")
        creds = _run_consent_flow(config)
        _save_credentials(creds)
        # First sync right after consent so the dashboard is not empty until
        # the next background tick. Deferred import avoids a module cycle
        # (auth <- sync <- background_sync).
        from background_sync import request_soon

        request_soon()
    except Exception as exc:
        # The dashboard shows the short form; the log keeps the whole stack,
        # which is the only way to diagnose a platform-specific failure
        # (e.g. a Wine build of the exe) after the fact.
        logger.exception("Google sign-in failed")
        with _login_lock:
            _login_state["error"] = repr(exc)
    finally:
        with _login_lock:
            _login_state["in_progress"] = False
            _login_state["auth_url"] = None


def start_login() -> dict:
    """Start the consent flow; a second click never opens a second flow.

    The flag is set HERE, under the same lock that checked it (review §1.5):
    between the old check and the first tick of the flow thread, two quick
    clicks could open two OAuth consent windows.
    """
    with _login_lock:
        if _login_state["in_progress"]:
            return {"started": True, "already_running": True}
        if _client_config() is None:
            return {
                "started": False,
                "error": "OAuth client configuration is missing in this build. "
                "See README for setup instructions.",
            }
        _login_state["in_progress"] = True
        _login_state["error"] = None
        _login_state["auth_url"] = None
    threading.Thread(target=_run_login_flow, daemon=True).start()
    return {"started": True, "already_running": False}


def login_status() -> dict:
    # The token refresh is a network call: it must run OUTSIDE _login_lock,
    # which protects only the tiny _login_state dict (review §1.4).
    authenticated = get_valid_credentials() is not None
    with _login_lock:
        return {
            "authenticated": authenticated,
            "login_in_progress": _login_state["in_progress"],
            "error": _login_state["error"],
            # Single-use consent URL: only while the flow is waiting for it.
            "auth_url": _login_state["auth_url"],
        }


def logout() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def require_credentials() -> Credentials:
    creds = get_valid_credentials()
    if creds is None:
        raise HTTPException(
            status_code=401,
            detail="Not signed in to Google. Please sign in again.",
        )
    return creds
