"""Check the Google consent flow without a browser.

Drives the parts of ``backend/auth.py`` that a browser would otherwise
exercise: the loopback callback server, the state check and both token
transports. The token endpoint is called with a bogus authorization code on
purpose — Google answering ``invalid_grant`` proves the TLS path works end to
end, and no real user consent is ever needed.

Usage (from the project root):

    .venv\\Scripts\\python.exe tools\\check_oauth_flow.py

Exit code 0 means every check passed. The script is deliberately standalone:
the project has no test runner, the same way ``backend/test_classroom.py`` is
run by hand.
"""

import logging
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
# Isolate the run: a temporary data dir keeps the real token untouched.
os.environ.setdefault(
    "GC_DASHBOARD_DATA_DIR", tempfile.mkdtemp(prefix="gc-oauth-check-")
)
sys.path.insert(0, str(PROJECT_DIR / "backend"))

import auth

RESULTS: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}".rstrip(), flush=True)


def get(url: str, timeout: float = 10) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:  # a 404 for favicon is expected
        return exc.code, ""


def wait_for(predicate, seconds: float = 30) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def check_callback_server() -> None:
    print("== loopback callback server ==", flush=True)
    server = auth._CallbackServer()
    host, port = server.server_address[:2]
    waiter = threading.Thread(
        target=lambda: server.wait_for_callback(20), name="waiter"
    )
    waiter.start()
    try:
        check("binds 127.0.0.1 only", host == "127.0.0.1", f"host={host}")
        check(
            "redirect URI equals the bound address",
            server.redirect_uri == f"http://127.0.0.1:{port}/",
            server.redirect_uri,
        )
        check(
            "no exclusive-address option (the Wine failure mode)",
            server.allow_reuse_address and not getattr(server, "exclusive", False),
        )

        status, _body = get(f"{server.redirect_uri}favicon.ico")
        check("unrelated request answers 404", status == 404, f"status={status}")
        check("unrelated request did not satisfy the callback", server.params is None)

        # A browser that resets a preconnected socket must not abort the wait.
        reset = socket.create_connection(("127.0.0.1", port))
        reset.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        reset.close()
        time.sleep(0.3)
        check("wait survives a reset connection", waiter.is_alive())

        status, body = get(f"{server.redirect_uri}?code=abc123&state=st-1")
        check(
            "callback answers the browser with 200", status == 200, f"status={status}"
        )
        check("success page asks the user to return", "close this window" in body)
        check(
            "code and state were captured",
            server.params == {"code": ["abc123"], "state": ["st-1"]},
            str(server.params),
        )
    finally:
        waiter.join(timeout=25)
        server.server_close()
    check("wait loop finished after the callback", not waiter.is_alive())

    server = auth._CallbackServer()
    started = time.monotonic()
    try:
        server.wait_for_callback(1)
        check("a missing redirect times out", False, "no exception raised")
    except TimeoutError as exc:
        check(
            "a missing redirect times out",
            "No Google redirect" in str(exc),
            f"{time.monotonic() - started:.1f}s",
        )
    finally:
        server.server_close()


def check_transports() -> bool:
    """Exercise both token transports; returns False when config is missing."""
    print("== token transports ==", flush=True)
    config = auth._client_config()
    if config is None:
        check(
            "OAuth client config is available",
            False,
            "no credentials.json / embedded config",
        )
        return False
    check("OAuth client config is available", True)

    flow = auth.InstalledAppFlow.from_client_config(config, auth.SCOPES)
    redirect_uri = "http://127.0.0.1:9/"
    flow.redirect_uri = redirect_uri
    auth_url, _state = flow.authorization_url()
    check("consent URL asks for offline access", "access_type=offline" in auth_url)
    check("consent URL carries PKCE", "code_challenge=" in auth_url)

    client = config.get("installed") or config.get("web") or config
    try:
        auth.post_token_request(client, "bogus-code", redirect_uri, flow.code_verifier)
        check("httplib2 reaches the token endpoint", False, "no error raised")
    # The `and` in this handler's body is not an `except` expression; the
    # rule matches descendants and flags a false positive.
    except RuntimeError as exc:  # pi-lens-ignore: no-boolean-in-except
        text = str(exc)
        rejected_by_google = "400" in text and "code" in text.lower()
        check(
            "httplib2 reaches the token endpoint (Google rejects the code)",
            rejected_by_google,
            text[:110],
        )
        check(
            "httplib2 failure is Google's answer, not a socket error",
            "Invalid argument" not in text,
        )

    real_fetch_token = flow.fetch_token

    def failing_fetch_token(**_kwargs):
        raise OSError(22, "Invalid argument")

    flow.fetch_token = failing_fetch_token
    try:
        auth._exchange_code(flow, "bogus-code", redirect_uri)
        check("OSError falls back to httplib2", False, "no error raised")
    except RuntimeError as exc:
        check(
            "OSError falls back to httplib2 (Google answers)",
            "code" in str(exc).lower(),
            str(exc)[:110],
        )
    finally:
        flow.fetch_token = real_fetch_token
    return True


def check_login_flow() -> None:
    print("== login flow as the dashboard triggers it ==", flush=True)
    opened: dict[str, str] = {}
    auth.webbrowser = types.SimpleNamespace(
        open=lambda url, **_kwargs: opened.setdefault("url", url) or True
    )

    auth.start_login()
    check(
        "start_login starts a background flow", auth.login_status()["login_in_progress"]
    )
    check(
        "consent URL is published while waiting",
        wait_for(lambda: auth.login_status().get("auth_url") is not None),
    )

    auth_url = opened.get("url") or auth.login_status()["auth_url"]
    params = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
    check(
        "consent URL advertises the loopback redirect",
        params.get("redirect_uri", [""])[0].startswith("http://127.0.0.1:"),
        params.get("redirect_uri", [""])[0],
    )

    status, _body = get(
        f"{params['redirect_uri'][0]}?code=bogus&state={params['state'][0]}"
    )
    check("browser-facing callback answers 200", status == 200, f"status={status}")
    check(
        "flow finishes",
        wait_for(lambda: not auth.login_status()["login_in_progress"], 40),
    )
    error = auth.login_status().get("error") or ""
    check(
        "Google's rejection is reported, not a socket error",
        "invalid_grant" in error or "code" in error.lower(),
        error[:110],
    )
    check(
        "consent URL is cleared afterwards", auth.login_status().get("auth_url") is None
    )

    # A redirect from another attempt must be refused.
    opened.clear()
    auth.start_login()
    wait_for(lambda: auth.login_status().get("auth_url") is not None)
    foreign = urllib.parse.parse_qs(
        urllib.parse.urlparse(auth.login_status()["auth_url"]).query
    )
    get(f"{foreign['redirect_uri'][0]}?code=bogus&state=not-the-real-state")
    wait_for(lambda: not auth.login_status()["login_in_progress"], 20)
    check(
        "state mismatch is reported",
        "state mismatch" in (auth.login_status().get("error") or ""),
        (auth.login_status().get("error") or "")[:110],
    )


def main() -> int:
    logging.basicConfig(level=logging.CRITICAL)  # the checks report themselves
    check_callback_server()
    if check_transports():
        check_login_flow()
    print(f"\nSUMMARY: {sum(RESULTS)}/{len(RESULTS)} passed", flush=True)
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
