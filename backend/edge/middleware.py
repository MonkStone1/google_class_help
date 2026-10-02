"""The four middleware of the production edge, as one factory each.

They were four nested closures inside ``create_app`` (ADR-0039 stage 2); as
named functions each one can be installed on a bare app in a test and its
source inspected, which is how the session-gate deadlock regression test
(``tests/test_stage8_coexistence.py``) keeps working.

ORDER IS THE CONTRACT. Starlette runs the last-registered middleware
outermost, so the registration order in ``main.create_app`` —
throttle → session gate → CORS → Host/Origin guard → security headers — is
the runtime order, outside-in. Do not reorder those calls:

- security headers wrap the guard's own 403 answers (§48);
- the Host/Origin guard is outside CORS, so a foreign Origin never reaches
  Starlette's preflight responder;
- CORS is outside the session gate, so 401/403 stay readable by a browser;
- the throttle is innermost, after authentication has decided who the caller
  is.

Each factory is a module-level function and reads its limits through the
``config`` module object, so a test patches ``config.RATE_LIMIT_*`` and the
next request sees the new value.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from core import config
from core.proxy import client_ip, external_scheme
from db.session import SessionLocal
from edge import origin_guard, security


def install_throttle(app: FastAPI) -> None:
    """Per-IP buckets in front of the abuse surfaces (stage 9, §39).

    Hosted only: the desktop build is bound to loopback and keeps its
    unrestricted local endpoints (§74).
    """

    def _throttled(request: Request, key: str, capacity: int) -> bool:
        limiter = request.app.state.rate_limiter
        return limiter.allow(
            key,
            capacity=capacity,
            refill_per_second=capacity / 60.0,
        )

    def _retry_later(detail: str) -> JSONResponse:
        # 429 carries Retry-After so a well-behaved client backs off
        # instead of hammering the bucket (section 59 error mapping).
        return JSONResponse(
            {"detail": detail},
            status_code=429,
            headers={"Retry-After": "60"},
        )

    @app.middleware("http")
    async def throttle_abuse_surfaces(request: Request, call_next):
        # Stage 9 (section 39), hosted only: per-IP buckets in front of
        # the credential-adjacent and fan-out-adjacent endpoints. Desktop
        # never runs this middleware. Buckets answer 429; they never
        # authenticate, never touch Google, never touch the database.
        # The bucket is keyed by (surface, ip) so one hot endpoint cannot
        # exhaust the allowance of another.
        path = request.url.path
        method = request.method
        surface: str | None = None
        if method == "GET" and path == "/api/auth/login":
            surface = "login"
        elif method == "POST" and path == "/api/auth/login/start":
            # Turnstile-guarded start (DDoS §17) shares the login bucket:
            # it is the same credential-adjacent surface.
            surface = "login"
        elif method == "POST" and path == "/api/sync":
            surface = "sync"
        elif method == "DELETE" and path in {"/api/cache", "/api/me/cache"}:
            surface = "cache"
        elif method == "POST" and (
            path == "/api/feedback/tickets"
            or path.startswith("/api/feedback/tickets/")
            and path.endswith("/messages")
            or path.startswith("/api/admin/feedback/tickets/")
            and path.endswith("/messages")
        ):
            # ADR-0035: a COARSE per-IP cap in front of the upload-heavy
            # endpoints, so one address cannot stream a body's worth of
            # multipart parts into the single web replica. The real
            # control is the per-USER bucket inside the endpoints
            # (feedback_service) — a school NAT shares an address between
            # many legitimate users, so an IP-only limit would punish the
            # wrong people.
            surface = "feedback"
        if surface is not None:
            capacity = {
                "login": config.RATE_LIMIT_LOGIN_PER_MINUTE,
                "sync": config.RATE_LIMIT_SYNC_PER_MINUTE,
                "cache": config.RATE_LIMIT_CACHE_CLEAR_PER_MINUTE,
                "feedback": config.RATE_LIMIT_FEEDBACK_PER_MINUTE,
            }[surface]
            if not _throttled(request, f"{surface}:{client_ip(request)}", capacity):
                return _retry_later(
                    "Too many requests for this action; try again later."
                )
        return await call_next(request)


def install_session_gate(app: FastAPI) -> None:
    """Close every /api path that is not part of the auth flow (§50).

    Added FIRST so CORS (added below in ``create_app``) wraps the gate: 401
    responses still carry CORS headers and the frontend can read them (§7).
    """
    # Lazy import: the desktop build must never load the hosted OAuth
    # module (§32/§74). Only the hosted branch calls this factory.
    from auth.hosted import resolve_session_user

    def _resolve_gate_user(request: Request) -> int:
        """Session cookie -> user id, in a worker thread.

        Runs the blocking SQLAlchemy lookup OFF the event loop. The gate
        is an ``async`` middleware, so calling the synchronous
        ``resolve_session_user`` directly froze the whole loop for the
        duration of the query — and that turned a brief pool shortage into
        a permanent one (see the comment at the call site).
        """
        db = SessionLocal()
        try:
            return resolve_session_user(request, db).id
        finally:
            # Releasing the connection HERE is what keeps the pool from
            # leaking: while the loop was blocked, no endpoint could reach
            # its ``get_db`` cleanup, so nothing returned a connection.
            db.close()

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        path = request.url.path
        # The gate closes /api/* ONLY (migration stage 8, §50): the
        # static SPA shell, the public /privacy/ and /terms/ pages and
        # hashed assets must load without a session — the login screen
        # itself is part of that shell. The auth flow, the health probe
        # and CORS preflights additionally stay reachable under /api.
        if (
            request.method == "OPTIONS"
            or not path.startswith("/api/")
            or path in ("/api/health", "/api/ready")
            or path.startswith("/api/auth/")
        ):
            return await call_next(request)
        try:
            # Since stage 4 the authoritative user resolution is the
            # get_current_user dependency inside each endpoint; this gate
            # only fails the request early, before route dispatch.
            #
            # run_in_threadpool is not an optimisation, it is the fix for a
            # hard deadlock found by the local load stand
            # (docs/LOAD_TEST_LOCAL.md): the production pool is
            # DB_POOL_SIZE + DB_MAX_OVERFLOW = 5 (ADR-0028 §2.2), and with
            # the lookup inline the event loop blocked in
            # QueuePool.get() as soon as those 5 were busy. Endpoint
            # cleanup (get_db's `finally: db.close()`) runs on the loop, so
            # a blocked loop meant no connection ever came back: the pool
            # stayed empty and even /api/health — which touches no database
            # — stopped answering until the process was restarted.
            user_id = await run_in_threadpool(_resolve_gate_user, request)
        except StarletteHTTPException:
            return JSONResponse({"detail": "Not signed in."}, status_code=401)
        request.state.user_id = user_id
        return await call_next(request)


def install_cors(app: FastAPI) -> None:
    """Credentialed CORS for the explicitly configured origins (§27).

    Intentionally inside the Host/Origin guard: a foreign Host or Origin
    never reaches Starlette's preflight responder. For an allowed
    cross-origin request, CORS remains outside the session gate so 401/403
    responses are readable by the browser (§27).
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def install_host_guard(app: FastAPI, hosted: bool) -> None:
    """Host allow-list, exact Origin matching and the CSRF check (§27/§38).

    The decisions themselves live in ``edge.origin_guard``; this is the
    middleware that applies them. It runs in BOTH deployment modes: hosted
    mode has real authentication, but a correct Host check is still the
    first line of defence against DNS-rebinding style requests.
    """

    @app.middleware("http")
    async def enforce_allowed_host(request: Request, call_next):
        if not origin_guard._request_host_allowed(request):
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        # Browser requests from foreign pages are cut by exact Origin matching;
        # non-browser requests send no Origin and remain limited by the session
        # gate (hosted) or the loopback bind (desktop).
        origin = request.headers.get("origin")
        if origin is not None and not origin_guard._origin_allowed(origin, request):
            return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
        if hosted and request.method not in ("GET", "HEAD", "OPTIONS") and origin is None:
            # CSRF (§38), hosted only — the desktop build has no ambient
            # cookie to ride on. Layers, outermost first:
            #   1. SameSite=Lax session cookie (§37);
            #   2. exact Origin matching above (a cross-site browser request
            #      of an unsafe method always carries Origin);
            #   3. Fetch Metadata below, for requests without Origin —
            #      Sec-Fetch-Site is a forbidden header a page cannot forge.
            # Both headers absent = non-browser client (no ambient cookie
            # jar of its own), allowed on purpose so API tooling keeps
            # working. CORS is deliberately NOT counted as a defense (§38);
            # a signed CSRF token is unnecessary while the cookie is
            # host-only + SameSite=Lax and every unsafe request is
            # origin-checked (documented in ADR-0026).
            fetch_site = request.headers.get("sec-fetch-site")
            if fetch_site is not None and fetch_site not in ("same-origin", "none"):
                return JSONResponse(
                    {"detail": "Cross-site request rejected."}, status_code=403
                )
        return await call_next(request)


def install_security_headers(app: FastAPI) -> None:
    """Hosted-only response headers (stage 8, §36/§38/§48).

    Registered LAST, so it wraps every other middleware — including the
    guard's own 403 answers. The desktop build gets none of this: it is
    bound to loopback and keeps byte-for-byte its pre-stage-8 behaviour
    (§74).
    """

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Content-Security-Policy", security.CONTENT_SECURITY_POLICY)
        if request.url.path.startswith("/api"):
            # Per-user answers must not sit in any cache; the OAuth
            # callback and every API response are credential-adjacent (§36).
            headers.setdefault("Cache-Control", "no-store")
        # §36/§48: HSTS only when explicitly enabled (after HTTPS is
        # confirmed, stage 10) and only on an externally-https request —
        # the reverse proxy may set the header instead (then keep the
        # env at 0 to avoid duplicates).
        if config.HSTS_MAX_AGE > 0 and external_scheme(request) == "https":
            headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={config.HSTS_MAX_AGE}; includeSubDomains",
            )
        return response

