# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Stage 8 coexistence and production-edge tests (§32–§38, §48–§50, §74–§76).

Pins the decisions of this stage:

- §32/§74: the hosted startup path imports no desktop module, and the
  desktop path (security headers off, schedule intact) stays as it was;
- §36: production hosted refuses a non-HTTPS OAuth redirect at startup,
  uvicorn access-log queries are redacted, HSTS is opt-in;
- §37: session-cookie shape (finite TTL, optional __Host- prefix);
- §38: CSRF — unsafe methods without an allowed Origin are checked against
  Fetch Metadata in hosted mode, safe methods and desktop unaffected;
- §48: security headers (CSP/nosniff/Referrer-Policy/frame) on API and
  static responses, Cache-Control: no-store on /api;
- §49: no secret-shaped material in the frontend sources or build output;
- §50: public /privacy/ and /terms/ pages exist and are served by the app
  (Option A static strategy, §35).
"""

import inspect
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import access_log
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import hosted_auth
import main

PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_DIR / "backend"
FRONTEND_DIR = PROJECT_DIR / "frontend"


def _subprocess_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    """Hermetic env for a config/app subprocess (fresh data dir, no shell strays)."""
    env = os.environ.copy()
    for name in list(env):
        if name.startswith(("GC_DASHBOARD_", "COOKIE_", "APP_", "GOOGLE_")):
            env.pop(name)
    env.update(
        {
            "GC_DASHBOARD_DATA_DIR": str(tmp_path),
            "GC_DASHBOARD_ALLOWED_HOSTS": "localhost,127.0.0.1",
            **overrides,
        }
    )
    return env


def _run(code: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


# ------------------------------------------------------ §32/§74 import split


def test_hosted_startup_imports_no_desktop_module(tmp_path):
    """Importing the hosted app must not load any desktop-only module (§32)."""
    env = _subprocess_env(
        tmp_path,
        GC_DASHBOARD_HOSTED="1",
        APP_ENV="development",
        # Hosted mode requires PostgreSQL (stage 3); create_engine is lazy,
        # so the dummy URL satisfies the import without a running server.
        DATABASE_URL="postgresql+psycopg://gch_test:not-used@localhost:5432/gch_test",
    )
    completed = _run(
        "import sys, main\n"
        "desktop_modules = {'launcher', 'background_sync', 'auth', 'pystray'}\n"
        "found = sorted(desktop_modules & set(sys.modules))\n"
        "print(found)\n"
        "raise SystemExit(1 if found else 0)\n",
        env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_desktop_startup_still_loads_background_sync(tmp_path):
    """The desktop lifespan branch keeps its global schedule (ADR-0015, §74)."""
    env = _subprocess_env(tmp_path, GC_DASHBOARD_HOSTED="0")
    completed = _run(
        "import sys\n"
        "import main\n"
        "assert main.app.state.hosted is False\n"
        "import inspect\n"
        "source = inspect.getsource(main.lifespan)\n"
        "assert 'background_sync' in source\n"
        "print('ok')\n",
        env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_desktop_app_has_no_security_headers(client):
    """§74/§48: the production edge is hosted-only; desktop stays byte-identical."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert "x-content-type-options" not in response.headers
    assert "strict-transport-security" not in response.headers


# ------------------------------------------------- §36 HTTPS and log hygiene


def test_production_hosted_refuses_plain_http_redirect(tmp_path):
    """§36: no production OAuth callback over plain HTTP — fail at startup."""
    env = _subprocess_env(
        tmp_path,
        GC_DASHBOARD_HOSTED="1",
        APP_ENV="production",
        APP_BASE_URL="http://insecure.example",
    )
    completed = _run("import config", env)
    assert completed.returncode != 0, "plain-http production startup must fail"
    assert "requires HTTPS" in completed.stderr


def test_production_hosted_accepts_https_redirect(tmp_path):
    env = _subprocess_env(
        tmp_path,
        GC_DASHBOARD_HOSTED="1",
        APP_ENV="production",
        APP_BASE_URL="https://secure.example",
    )
    completed = _run("import config; print(config.GOOGLE_REDIRECT_URI)", env)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "https://secure.example/api/auth/callback"


def test_desktop_mode_has_no_https_requirement(tmp_path):
    """§75: the desktop loopback redirect stays http://127.0.0.1 by design."""
    env = _subprocess_env(
        tmp_path,
        GC_DASHBOARD_HOSTED="0",
        APP_ENV="production",
        APP_BASE_URL="http://localhost:8000",
    )
    completed = _run("import config; print('ok')", env)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_access_log_redacts_query_strings():
    """§36: an authorization code in the access log is never written."""
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '10.0.0.9:51234 - "GET /api/auth/callback?code=S4%2Fabc&state=xyz HTTP/1.1" 302',
        None,
        None,
    )
    assert access_log.RedactQueryFilter().filter(record)
    message = record.getMessage()
    assert "/api/auth/callback" in message
    assert "code=" not in message and "state=" not in message


def test_query_redaction_installed_once_for_hosted():
    main.create_app(hosted=True)
    main.create_app(hosted=True)
    logger = logging.getLogger("uvicorn.access")
    filters = [f for f in logger.filters if isinstance(f, access_log.RedactQueryFilter)]
    assert len(filters) == 1


# ----------------------------------------------------------- §37/§38 cookies


def test_session_cookie_defaults_and_ttl():
    """§37: finite TTL, prefix off by default, names stay readable in docs."""
    assert hosted_auth.SESSION_COOKIE_NAME == "gch_session"
    assert hosted_auth.NONCE_COOKIE_NAME == "gch_oauth_nonce"
    assert hosted_auth.SESSION_TTL_SECONDS == 14 * 24 * 60 * 60


def test_session_cookie_host_prefix_opt_in(tmp_path):
    """§37: GC_DASHBOARD_COOKIE_HOST_PREFIX=1 yields __Host- cookies."""
    env = _subprocess_env(tmp_path, GC_DASHBOARD_COOKIE_HOST_PREFIX="1")
    completed = _run("import hosted_auth; print(hosted_auth.SESSION_COOKIE_NAME)", env)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "__Host-gch_session"


def test_cross_site_unsafe_request_is_rejected(hosted_client):
    """§38: unsafe method, no Origin, cross-site Fetch Metadata → 403."""
    response = hosted_client.post("/api/sync", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    assert "Cross-site" in response.json()["detail"]


def test_same_origin_unsafe_request_passes_the_csrf_check(hosted_client):
    """§38: same-origin Fetch Metadata reaches the session gate (401 here)."""
    response = hosted_client.post(
        "/api/sync", headers={"Sec-Fetch-Site": "same-origin"}
    )
    assert response.status_code == 401


def test_safe_methods_ignore_fetch_metadata(hosted_client):
    response = hosted_client.get(
        "/api/health", headers={"Sec-Fetch-Site": "cross-site"}
    )
    assert response.status_code == 200


def test_session_gate_dispatches_its_database_lookup_to_a_thread():
    """The session gate must not resolve the session inline in async middleware.

    Regression for a hard deadlock found by the local load stand
    (docs/LOAD_TEST_LOCAL.md §6): ``require_session`` is an ``async``
    middleware, so calling the blocking ``resolve_session_user`` directly froze
    the event loop for the length of the query. With the production pool of 5
    (ADR-0028 §2.2) the loop then blocked in ``QueuePool.get()`` — and because
    endpoint cleanup runs on that loop, no connection ever came back, so the
    process stopped answering even ``/api/health`` until it was restarted.

    The check is structural, like ``test_desktop_startup_still_loads_background_sync``
    above: a thread-identity assertion cannot work here because ``TestClient``
    drives the app from its own portal thread. The behavioural proof is the
    load run in docs/LOAD_TEST_LOCAL.md §3; this test only keeps the mistake
    from being reintroduced silently.
    """
    source = inspect.getsource(main.create_app)
    gate = source.split("async def require_session", 1)[1].split("@app.middleware", 1)[
        0
    ]
    # The exact call, not just the name: the surrounding comment mentions
    # run_in_threadpool by name and must not satisfy this check.
    assert "await run_in_threadpool(" in gate, (
        "require_session must dispatch the blocking session lookup with "
        "`await run_in_threadpool(...)`; running it inline deadlocks the "
        "connection pool at capacity"
    )


def test_foreign_origin_unsafe_request_is_rejected(hosted_client):
    """§38 layer 2: exact Origin matching still cuts foreign origins first."""
    response = hosted_client.post(
        "/api/sync", headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert "origin" in response.json()["detail"].lower()


# ------------------------------------------------------ §48 security headers


def test_hosted_api_carries_security_headers(hosted_client, monkeypatch):
    monkeypatch.setattr(main, "HSTS_MAX_AGE", 0)
    response = hosted_client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["X-Frame-Options"] == "DENY"
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    # No inline-script escape hatch: the theme script is an external file.
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "frame-ancestors 'none'" in csp
    assert "Strict-Transport-Security" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"


def test_401_responses_carry_security_headers_too(hosted_client):
    """The headers middleware wraps the guard and the session gate."""
    response = hosted_client.get("/api/courses")
    assert response.status_code == 401
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_hsts_sent_only_when_enabled_over_https(hosted_client, monkeypatch):
    monkeypatch.setattr(main, "HSTS_MAX_AGE", 31536000)
    response = hosted_client.get("/api/health")
    assert response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )
    monkeypatch.setattr(main, "HSTS_MAX_AGE", 0)
    response = hosted_client.get("/api/health")
    assert "Strict-Transport-Security" not in response.headers


def test_hsts_not_sent_on_plain_http(monkeypatch):
    """§48: HSTS is an https-only header even when the env enables it."""
    monkeypatch.setattr(main, "HSTS_MAX_AGE", 31536000)
    client = TestClient(main.create_app(hosted=True), base_url="http://gch.test")
    try:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "Strict-Transport-Security" not in response.headers
    finally:
        client.close()


# --------------------------------------------- §35/§49/§50 static + scanning


def test_public_legal_pages_exist_as_sources():
    """§50: /privacy and /terms must be publicly reachable without a session."""
    privacy = FRONTEND_DIR / "public" / "privacy" / "index.html"
    terms = FRONTEND_DIR / "public" / "terms" / "index.html"
    assert privacy.is_file() and terms.is_file()
    privacy_text = privacy.read_text(encoding="utf-8")
    terms_text = terms.read_text(encoding="utf-8")
    assert "<h1>Privacy Policy</h1>" in privacy_text
    assert "classroomhelp.pp.ua" in privacy_text
    assert "Google" in privacy_text and "read-only" in privacy_text
    assert "<h1>Terms of Service</h1>" in terms_text
    # No scripts on the legal pages: they must render under script-src 'self'.
    assert "<script" not in privacy_text and "<script" not in terms_text


# ------------------------------------------------- favicon (ADR-0031)


def test_site_ships_a_generated_favicon():
    """ADR-0031: the browser tab must show the brand mark, not a blank page.

    The icon is generated by tools/make_icon.py into frontend/public, so Vite
    copies it into dist and it reaches the Docker image. This pins both halves:
    the files are committed, and every HTML surface links at least one of them.
    """
    public = FRONTEND_DIR / "public"
    names = ("favicon.svg", "favicon.ico", "favicon-32x32.png", "apple-touch-icon.png")
    for name in names:
        path = public / name
        assert path.is_file(), f"missing generated favicon: {name}"
        assert path.stat().st_size > 0, f"empty favicon: {name}"

    svg = (public / "favicon.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") and "#188038" in svg

    # The SPA shell and both legal pages must reference the icon.
    pages = [
        FRONTEND_DIR / "index.html",
        public / "privacy" / "index.html",
        public / "terms" / "index.html",
    ]
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert 'rel="icon"' in text, f"no favicon link in {page.name}"
        assert "/favicon.svg" in text, f"no SVG favicon in {page.name}"


def test_donation_qr_codes_are_shipped_and_referenced():
    """ADR-0037: the donation codes must survive the build and be reachable.

    They live in `frontend/public/donate/`, which Vite copies into `dist` for
    both the Docker image and the desktop exe. This pins the half that a
    frontend unit test cannot see: that the FILES are there and that the
    component points at those exact names.

    A typo in the path would not fail loudly: `SPAStaticFiles` answers an
    unknown non-`assets/` path with the SPA shell and HTTP 200, so the browser
    would render HTML where a PNG was expected and the page would only look
    broken. Hence the explicit reference check.
    """
    donate = FRONTEND_DIR / "public" / "donate"
    component = (FRONTEND_DIR / "src" / "components" / "DonateCards.tsx").read_text(
        encoding="utf-8"
    )

    for name in ("monobank.png", "privatbank.png"):
        path = donate / name
        assert path.is_file(), f"missing donation code: {name}"
        assert path.stat().st_size > 0, f"empty donation code: {name}"
        # Both banks' exports carry a .png name but are actually JPEG, which is
        # why the browsers accept them and why the type is sniffed rather than
        # trusted. The check is therefore that Pillow can DECODE the file, not
        # that it starts with the PNG signature: a truncated or renamed file
        # would still be served and would still "pass" an existence check.
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                real_width, real_height = image.size
        except OSError as exc:  # pragma: no cover - only on a corrupt file
            pytest.fail(f"{name} is not a decodable image: {exc}")
        assert name in component, f"{name} is shipped but never referenced"

        # The dimensions declared in the component must match the real file.
        # They are what the browser reserves before the image loads, and a
        # stale pair would shift the layout — or, with a fixed CSS height,
        # stretch the code until the bank app stops reading it. The two banks
        # differ (1051×1280 vs 1056×1280), so each carries its own pair.
        stem = name.removesuffix(".png")
        assert (
            f'file: "{name}"' in component
        ), f"{name} is not declared in the banks list"
        declared = re.search(
            rf'id: "{stem}".*?width: (\d+),\s*height: (\d+)',
            component,
            re.DOTALL,
        )
        assert declared is not None, f"no declared size for {name}"
        assert (int(declared.group(1)), int(declared.group(2))) == (
            real_width,
            real_height,
        ), (
            f"{name} is {real_width}x{real_height} on disk but the component "
            f"declares {declared.group(1)}x{declared.group(2)}"
        )

    # The codes are same-origin, which is what the CSP allows (§48).
    assert "/donate/" in component
    assert "http://" not in component and "https://" not in component


def test_support_answer_has_no_white_background_in_css():
    """п.4: a support answer must not render as a white block inside its card.

    The regression this pins is a class-name mismatch, not a missing rule. The
    read-only renderer (``MDEditor.Markdown``) emits ``.wmde-markdown``, which
    the library styles with ``background-color: var(--color-canvas-default)``
    (i.e. ``#ffffff`` in the light theme). An override aimed at
    ``.markdown-body .w-md-editor`` — the EDITING surface's class — matched
    nothing, so the answer kept its white block while the text turned blue: the
    exact "синий текст на белом фоне" that was reported.

    Reading the stylesheet is the only honest place for this: Vitest does not
    load the app's CSS, so a jsdom ``getComputedStyle`` assertion would pass
    without ever looking at the rule.
    """
    css = (FRONTEND_DIR / "src" / "styles" / "pages.css").read_text(
        encoding="utf-8"
    )
    # Comments are stripped before any selector check: the paragraph above the
    # rule NAMES the wrong selector on purpose, to explain why it is wrong, and a
    # naive substring search would match that prose and fail forever.
    rules = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)

    # The override must name the class that actually carries the background.
    assert (
        ".ticket-message-admin .markdown-body .wmde-markdown" in css
    ), "the support answer must override .wmde-markdown, not .w-md-editor"
    match = re.search(
        r"\.ticket-message-admin \.markdown-body \.wmde-markdown\s*\{([^}]*)\}",
        rules,
    )
    assert match is not None
    assert "background: transparent" in match.group(1), (
        "the answer must let the card's accent surface show through, otherwise "
        "the library's white .wmde-markdown background wins"
    )
    assert "color: var(--accent)" in match.group(1), (
        "the answer's own text must take the accent colour"
    )

    # Code must be STRONGER than that text (п.4), so it gets the filled chip.
    code_rule = re.search(
        r"\.ticket-message-admin \.markdown-body pre,\s*"
        r"\.ticket-message-admin \.markdown-body code\s*\{([^}]*)\}",
        rules,
    )
    assert code_rule is not None
    assert "background: var(--accent)" in code_rule.group(1)
    assert "color: #fff" in code_rule.group(1)

    # The dead selector must be gone, or someone will "fix" the background
    # against it a second time.
    assert ".markdown-body .w-md-editor" not in rules, (
        ".w-md-editor is the editing surface; the read-only renderer emits "
        ".wmde-markdown, so this selector matches nothing"
    )


def test_donation_codes_are_not_recolored_by_css():
    """ADR-0037: the artwork must render exactly as the bank ships it.

    The QR codes come on a coloured background of the bank's own. Putting a
    white plate, a tint or a filter UNDER the code is the classic way to make
    it stop scanning, and the failure is silent — the page looks fine and the
    money never arrives. The theme is therefore carried by `.donate-card`, the
    frame around the image, and `.donate-qr` only sizes the artwork.

    The assertion lives here rather than in a component test because Vitest
    does not load the app's stylesheets: a jsdom `getComputedStyle` check would
    pass without ever reading the rule it claims to verify.
    """
    css = (FRONTEND_DIR / "src" / "styles" / "components.css").read_text(
        encoding="utf-8"
    )
    for selector in (r"\.donate-qr\s*\{", r"\.donate-preview-image\s*\{"):
        match = re.search(selector + r"([^}]*)\}", css)
        assert match is not None, f"the {selector} rule is missing"
        declarations = match.group(1)
        for forbidden in ("background", "filter", "mix-blend-mode", "opacity"):
            assert forbidden not in declarations, (
                f"{selector} must not set `{forbidden}`: it would alter the code"
            )

    # The artwork is portrait and the two banks differ (1051×1280 vs 1056×1280).
    # A fixed `height` next to the width is what would stretch a QR past the
    # point a bank app can read it, so only the width may be constrained.
    for selector in (r"\.donate-qr\s*\{", r"\.donate-preview-image\s*\{"):
        declarations = re.search(selector + r"([^}]*)\}", css).group(1)
        assert "height: auto" in declarations, (
            f"{selector} must keep `height: auto` so the QR is never stretched"
        )


def test_make_icon_tool_is_wired_into_the_build():
    """ADR-0031: build.bat must generate the icon BEFORE the frontend build.

    Vite copies frontend/public into dist during `npm run build`, so an icon
    generated afterwards would never reach the shipped bundle.
    """
    # Compare the executable commands only: the header comment block also
    # mentions both steps, and matching there would test nothing.
    commands = "\n".join(
        line
        for line in (PROJECT_DIR / "build.bat")
        .read_text(encoding="utf-8")
        .lower()
        .splitlines()
        if not line.strip().startswith("rem")
    )
    icon_step = commands.index("make_icon.py")
    frontend_step = commands.index("npm run build")
    assert icon_step < frontend_step, (
        "make_icon.py must run before `npm run build` so the favicons are "
        "copied into frontend/dist"
    )


def test_static_strategy_option_a_serves_legal_pages_and_spa(tmp_path, monkeypatch):
    """§35 Option A: FastAPI serves the SPA and directory index pages."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA-SHELL</html>", encoding="utf-8")
    (dist / "privacy").mkdir()
    (dist / "privacy" / "index.html").write_text(
        "<html>PRIVACY-PAGE</html>", encoding="utf-8"
    )
    monkeypatch.setattr(main, "FRONTEND_DIST_DIR", dist)
    client = TestClient(main.create_app(hosted=True), base_url="https://gch.test")
    try:
        # §50: reachable without any session (the gate only covers /api).
        page = client.get("/privacy/")
        assert page.status_code == 200
        assert "PRIVACY-PAGE" in page.text
        assert page.headers["X-Content-Type-Options"] == "nosniff"
        # The extension-less URL reaches the same page (redirect or direct).
        short = client.get("/privacy")
        if short.status_code in (307, 308, 301, 302):
            short = client.get(short.headers["location"])
        assert short.status_code == 200
        assert "PRIVACY-PAGE" in short.text
        # SPA fallback still works for React routes, assets still 404.
        shell = client.get("/subjects/123")
        assert "SPA-SHELL" in shell.text
        assert client.get("/assets/missing.js").status_code == 404
    finally:
        client.close()


_SECRET_PATTERNS = [
    re.compile(r"GOCSPX-[0-9A-Za-z_\-]+"),  # Google client secret shape
    re.compile(r"AIzaSy[0-9A-Za-z_\-]{30,}"),  # Google API key shape
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"(?:client_secret|refresh_token|encryption_key)\s*[:=]\s*[\"'][^\"']{8,}[\"']",
        re.IGNORECASE,
    ),
    re.compile(r"(?:postgres(?:ql)?|postgresql\+psycopg)://[^\"'\s]+"),
]


def _scan(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        if path.is_dir():
            files = [p for p in path.rglob("*") if p.is_file()]
        elif path.is_file():
            files = [path]
        else:
            continue
        for file in files:
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern.search(text):
                    hits.append(f"{file}: {pattern.pattern}")
    return hits


def test_frontend_sources_contain_no_secret_material():
    """§49: anything in frontend/dist is public — sources must stay clean."""
    scan_paths = [
        FRONTEND_DIR / "src",
        FRONTEND_DIR / "public",
        FRONTEND_DIR / "index.html",
    ]
    dist = FRONTEND_DIR / "dist"
    if dist.is_dir():  # the built bundle too, when it exists
        scan_paths.append(dist)
    hits = _scan(scan_paths)
    assert hits == [], f"secret-shaped material in the public frontend: {hits}"
