# Google Class Help — Low-Cost DDoS / Abuse Protection Implementation Plan

This document is the implementation companion for the hosted Google Class Help project.

Target:

- approximately 1,000 registered users;
- approximately 20–30 teachers;
- initial VPS: about 2 vCPU / 2 GB RAM;
- keep recurring security costs at $0 where practical;
- preserve the existing FastAPI + React + PostgreSQL + worker architecture;
- do not introduce Redis, Kubernetes, Celery, or expensive infrastructure unless measurement later proves it necessary.

Recommended architecture:

```text
Internet
   ↓
Cloudflare
   ├── DDoS protection
   ├── proxy / origin hiding
   ├── optional rate controls
   └── optional Turnstile
   ↓
Cloudflare Tunnel
   ↓
Caddy (internal Docker network)
   ↓
FastAPI
   ├── application rate limiting
   ├── authentication/session checks
   └── user-scoped API
   ↓
PostgreSQL

Worker
   ↓
bounded user-scoped Google Classroom synchronization
```

Cloudflare's standard DDoS protection is available on all plans. Cloudflare Tunnel is also available on all plans and uses an outbound-only connection, so the origin does not need public inbound HTTP/HTTPS ports. Turnstile has a Free plan. The aim is therefore to keep the initial security stack free beyond the VPS itself.

---

## 1. Cost target

Expected recurring cost:

```text
VPS 2 vCPU / 2 GB              paid — your chosen VPS tariff
Cloudflare Free                $0
Cloudflare Tunnel              included
Cloudflare DDoS protection     included
Cloudflare Turnstile           $0
Docker                         $0
Caddy                          $0
PostgreSQL                     $0 self-hosted in Docker
Ubuntu                         $0
```

Do not buy Cloudflare Pro/Business just for the initial deployment.

Do not add a dedicated Redis server just for the first rate limiter.

Do not add a second VPS until monitoring shows a real need.

---

# PART A — INFRASTRUCTURE

## 2. Put the domain under Cloudflare

Add:

```text
monkstonecor.pp.ua
```

to Cloudflare and change the domain's authoritative nameservers at the registrar to the Cloudflare nameservers provided by Cloudflare.

Keep unrelated records such as Zoho MX/TXT records.

For the production web hostname, use Cloudflare proxy/Tunnel.

Do not deliberately expose the VPS IP as the normal public web A record when using Tunnel.

---

## 3. Use Cloudflare Tunnel

Recommended production flow:

```text
Internet
   ↓
Cloudflare edge
   ↓
encrypted outbound Tunnel
   ↓
VPS
   ↓
Caddy
   ↓
FastAPI
```

Create a remotely managed tunnel in:

```text
Cloudflare Dashboard
→ Networking
→ Tunnels
→ Create Tunnel
```

Create a published application route:

```text
Hostname:
monkstonecor.pp.ua
```

Map it to:

```text
http://caddy:80
```

if `cloudflared` is inside the same Docker network.

Store the tunnel token only in the production environment:

```env
CLOUDFLARE_TUNNEL_TOKEN=...
```

Never commit the token to Git.

---

## 4. Docker Compose layout

Use:

```yaml
services:
  postgres:
    ...

  web:
    ...

  worker:
    ...

  caddy:
    ...

  cloudflared:
    ...
```

Use a private Docker network.

Production traffic:

```text
cloudflared
    ↓
caddy:80
    ↓
web:8000

web:8000 ──→ postgres:5432
worker   ──→ postgres:5432
```

Do not expose:

```text
5432
8000
```

to the public host.

With Tunnel, Caddy also does not need public host ports.

---

## 5. Firewall and SSH

Because Tunnel uses outbound connections, production can keep inbound web ports closed.

At minimum:

```text
Inbound:
    SSH → allowed for administration
    80  → closed
    443 → closed
    5432 → closed
    8000 → closed
```

Use SSH keys.

After key-based access is verified, disable password authentication.

Optionally allow SSH only from your own IP/VPN.

Do not consider fail2ban a DDoS solution. It helps against some login abuse, but it cannot protect a saturated network link.

---

# PART B — APPLICATION CODE

## 6. Add application-level rate limiting

Do not rely on Cloudflare alone for application abuse.

The first deployment can use a small in-process limiter. Keep one FastAPI web process initially so the limiter is consistent.

Create:

```text
backend/security/rate_limit.py
```

```python
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimit:
    max_requests: int
    window_seconds: float


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: RateLimit) -> bool:
        now = time.monotonic()

        async with self._lock:
            queue = self._events[key]

            cutoff = now - limit.window_seconds
            while queue and queue[0] <= cutoff:
                queue.popleft()

            if len(queue) >= limit.max_requests:
                return False

            queue.append(now)
            return True


rate_limiter = InMemoryRateLimiter()
```

Important limitation:

- this limiter is process-local;
- if you later run multiple web processes/replicas, move the shared limit to Redis/PostgreSQL or another shared mechanism.

For the first deployment this is intentionally simple.

---

## 7. Determine the client IP

Create:

```text
backend/security/client_ip.py
```

```python
from fastapi import Request


def get_client_ip(request: Request) -> str:
    cf_ip = request.headers.get("CF-Connecting-IP")

    if cf_ip:
        return cf_ip

    if request.client is not None:
        return request.client.host

    return "unknown"
```

Only trust `CF-Connecting-IP` because the production architecture uses Cloudflare Tunnel and blocks direct public origin access.

If the deployment is changed later so that the origin is directly reachable from the Internet, add an explicit trusted-proxy check before trusting forwarded headers.

---

## 8. Add endpoint guards

Create:

```text
backend/security/guards.py
```

```python
from fastapi import HTTPException, Request, status

from .client_ip import get_client_ip
from .rate_limit import RateLimit, rate_limiter


LOGIN_LIMIT = RateLimit(
    max_requests=10,
    window_seconds=600,
)

SYNC_IP_LIMIT = RateLimit(
    max_requests=10,
    window_seconds=600,
)


async def require_login_rate_limit(request: Request) -> None:
    ip = get_client_ip(request)

    allowed = await rate_limiter.allow(
        f"login:ip:{ip}",
        LOGIN_LIMIT,
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )


async def require_sync_ip_rate_limit(request: Request) -> None:
    ip = get_client_ip(request)

    allowed = await rate_limiter.allow(
        f"sync:ip:{ip}",
        SYNC_IP_LIMIT,
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sync requests. Try again later.",
        )
```

Use these guards on the relevant routes.

Treat the numbers as starting values and tune them from real traffic.

---

## 9. Protect synchronization per user

The most important Google-Classroom-specific protection is:

```text
one user → at most one active sync
```

and a cooldown between expensive manual syncs.

Recommended state:

```text
sync_jobs
---------
user_id
status
started_at
finished_at
last_success_at
last_error
```

The route should do approximately:

```python
if sync_already_running(user_id):
    raise HTTPException(
        status_code=409,
        detail="Synchronization is already running.",
    )

if sync_cooldown_active(user_id):
    raise HTTPException(
        status_code=429,
        detail="Synchronization was requested too recently.",
    )

enqueue_user_sync(user_id)
```

Do not perform the full Google synchronization inside the HTTP request.

Return quickly:

```json
{
  "status": "queued"
}
```

The worker performs the actual work.

---

## 10. Bound worker concurrency

For the initial 2 vCPU VPS:

```env
SYNC_MAX_WORKERS=2
```

Start conservatively.

Do not create a huge global thread pool.

The worker should:

```text
queue
 ↓
user-specific job
 ↓
load that user's Google credentials
 ↓
bounded Classroom API calls
 ↓
PostgreSQL
```

One user's large teacher course must not monopolize all workers.

---

## 11. Rate-limit destructive and expensive endpoints

These routes must be protected:

```text
POST   /api/auth/login/start
POST   /api/sync
DELETE /api/me/cache
```

For authenticated endpoints, use both:

```text
per-IP protection
+
per-user protection
```

Do not trust a client-supplied `user_id`.

Use:

```python
current_user.id
```

from the authenticated session.

---

## 12. Secure cache deletion

Do not retain a global endpoint such as:

```text
DELETE /api/cache?confirm=true
```

for the hosted application.

Prefer:

```text
DELETE /api/me/cache
```

Example:

```python
@router.delete("/me/cache")
async def clear_my_cache(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Delete only rows owned by current_user.id.
    ...
```

---

## 13. Request size limits

In the internal Caddy configuration:

```caddyfile
:80 {
    request_body {
        max_size 2MB
    }

    reverse_proxy web:8000
}
```

Increase the limit only when the application actually requires larger requests.

Do not add general file-upload capabilities unless there is a concrete feature requirement.

---

## 14. Timeouts

Ensure Google API calls have explicit connect/read timeouts.

For example, where the current Google HTTP client permits it:

```python
timeout = 30.0
```

Also enforce reasonable timeouts for:

- database operations;
- outbound HTTP calls;
- individual sync jobs.

A stalled external API must not occupy a worker indefinitely.

---

# PART C — AUTHENTICATION AND COOKIES

## 15. Secure session cookie

Production cookie:

```python
response.set_cookie(
    key="__Host-gch_session",
    value=session_token,
    httponly=True,
    secure=True,
    samesite="lax",
    path="/",
    max_age=60 * 60 * 24 * 30,
)
```

Development can use:

```text
secure=False
```

when using plain localhost HTTP.

Never put the session token in:

```text
localStorage
sessionStorage
URL parameters
```

---

## 16. CSRF

Review all state-changing endpoints:

```text
POST /api/auth/login/start
POST /api/sync
POST /api/auth/logout
DELETE /api/me/cache
```

Use same-origin requests plus:

```text
SameSite=Lax
```

and implement a CSRF token for the state-changing routes where appropriate.

Do not treat CORS as a CSRF defense.

---

# PART D — TURNSTILE

## 17. Protect login initiation

Turnstile is free on the current Free plan.

Use it only for suspicious/expensive actions, starting with login initiation.

Preferred flow:

```text
Click "Sign in with Google"
       ↓
Turnstile
       ↓
POST /api/auth/login/start
       ↓
backend verifies Turnstile token
       ↓
Google OAuth authorization URL
```

Environment variables:

```env
TURNSTILE_SITE_KEY=...
TURNSTILE_SECRET_KEY=...
```

The site key may be used by the frontend.

The secret key must remain backend-only.

Never put:

```text
TURNSTILE_SECRET_KEY
```

into the React build.

---

# PART E — CLOUDFLARE

## 18. Enable normal DDoS protection

Cloudflare's normal DDoS protection is already available on the Free plan.

Keep the normal managed DDoS rules enabled.

Do not immediately add complicated custom security rules.

---

## 19. Optional basic Cloudflare rate limiting

Cloudflare's Free rate-limiting feature is more limited than paid tiers.

Use it as an extra coarse edge defense for paths such as:

```text
/api/auth/login/start
/api/sync
```

The backend remains responsible for:

```text
per-user limits
sync cooldown
sync deduplication
```

Do not depend on the Free Cloudflare rule alone to implement authenticated-user quotas.

---

## 20. Verify that the origin IP is not used for the public site

With Tunnel:

```text
monkstonecor.pp.ua
    ↓
Cloudflare
    ↓
Tunnel
```

Do not publish a second public web hostname that exposes:

```text
VPS_IP
```

such as:

```text
server.monkstonecor.pp.ua
```

unless there is a specific reason.

Review DNS records for:

```text
www
ftp
dev
api
staging
```

and make sure they do not accidentally expose the VPS address.

---

# PART F — LOGGING

## 21. Never log secrets

Remove/review any logging of:

```text
access_token
refresh_token
client_secret
authorization_code
session_cookie
full credentials JSON
```

Safe:

```python
logger.info(
    "Google token refresh completed for user_id=%s",
    user_id,
)
```

Unsafe:

```python
logger.info("credentials=%s", credentials)
```

---

# PART G — DOCKER HARDENING

## 22. Non-root application container

In the backend Dockerfile:

```dockerfile
RUN addgroup --system app &&     adduser --system --ingroup app app

USER app
```

Do not run FastAPI as root.

---

## 23. Never bake secrets into images

Never use:

```dockerfile
COPY .env /app/.env
```

or:

```dockerfile
COPY credentials.json /app/
```

or:

```dockerfile
ENV GOOGLE_CLIENT_SECRET=real-secret
```

Use the production environment/Compose secret mechanism.

---

# PART H — HEALTH AND MONITORING

## 24. Health endpoints

Create:

```text
GET /api/health
GET /api/ready
```

Example:

```python
@router.get("/health")
async def health():
    return {"status": "ok"}
```

Readiness may verify PostgreSQL:

```python
@router.get("/ready")
async def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}
```

Do not return environment variables or database credentials.

---

## 25. Basic monitoring

Do not pay for a monitoring platform initially.

Use:

```bash
docker stats
docker compose ps
docker compose logs --tail=200 web
docker compose logs --tail=200 worker
```

Track:

```text
RAM
CPU
disk
HTTP 5xx
HTTP 429
sync queue depth
sync duration
Google API 429/5xx
PostgreSQL errors
```

Upgrade the VPS when measured load requires it.

---

# PART I — BACKUPS

## 26. PostgreSQL backups

Create PostgreSQL dumps:

```bash
docker compose exec -T postgres   pg_dump   -U googleclasshelp   -d googleclasshelp   > "/opt/backups/googleclasshelp-$(date +%F-%H%M).sql"
```

Do not store the only backup on the same VPS forever.

Initially keep a small number of rolling VPS backups and periodically copy an encrypted backup to your own PC.

Do not put database dumps into GitHub.

---

# PART J — TESTING

## 27. Rate-limit tests

Verify:

```text
rapid login attempts
rapid sync clicks
two simultaneous sync requests
```

Expected behavior:

```text
rate exceeded → 429
sync already running → 409
```

---

## 28. User isolation tests

Create:

```text
User A
User B
```

and verify:

```text
A cannot read B courses
A cannot read B coursework
A cannot read B grades
A cannot clear B cache
A cannot trigger B sync
B cannot read A data
```

---

## 29. Google token failure test

Invalidate User A's Google authorization.

Expected:

```text
User A → needs re-authentication
User B → unaffected
```

Never turn one user's OAuth failure into a global logout.

---

# PART K — DEPLOYMENT ORDER

Use this order:

```text
1. Finish hosting migration
        ↓
2. Add application rate limiting
        ↓
3. Add per-user sync lock/cooldown
        ↓
4. Add timeouts and request-size limits
        ↓
5. Harden sessions/cookies
        ↓
6. Add Turnstile
        ↓
7. Add Docker Compose
        ↓
8. Test locally
        ↓
9. Create Cloudflare account
        ↓
10. Move DNS to Cloudflare
        ↓
11. Create Tunnel
        ↓
12. Buy/deploy VPS
        ↓
13. Install Docker
        ↓
14. Clone Git
        ↓
15. Create production .env
        ↓
16. Start Compose
        ↓
17. Run Alembic migrations
        ↓
18. Test /api/health
        ↓
19. Test Google OAuth
        ↓
20. Test student + teacher
        ↓
21. Enable scheduled sync
        ↓
22. Configure backups
        ↓
23. Load test
        ↓
24. Public launch
```

---

# PART L — GIT CHECKLIST

These files are allowed in Git:

```text
Dockerfile
compose.yml
Caddyfile
Caddyfile.dev
.dockerignore
.gitignore
.env.example
backend/
frontend/
migrations/
tests/
docs/
README.md
```

These must NOT be committed:

```text
.env
credentials.json
client_secret.json
token.json
backend/embedded_secrets.py
data/token.json
data/classroom.db
*.db
*.sqlite
node_modules/
.venv/
frontend/dist/
logs/
database dumps
Cloudflare tunnel tokens
Turnstile secret key
Google OAuth web client secret
```

Run before pushing:

```powershell
git status
git ls-files | findstr /I "credentials token .env classroom.db embedded_secrets"
```

If a real secret was ever committed, rotate/revoke it rather than merely deleting the file in a later commit.

---

# PART M — FINAL LOW-COST PROFILE

Initial production:

```text
VPS:
    2 vCPU
    2 GB RAM
    35 GB SSD

Cloudflare:
    Free
    DDoS protection
    Tunnel
    Turnstile
    basic rate controls

Containers:
    postgres
    web
    worker
    caddy
    cloudflared

Application:
    one FastAPI web process initially
    bounded background worker
    per-user sync lock
    per-user cooldown
    per-IP login rate limit

No need initially:
    Redis
    Celery
    Kubernetes
    second VPS
    paid WAF
    paid monitoring
```

Scale only after measurement shows:

```text
RAM pressure
CPU saturation
growing sync queue
high database latency
high request latency
```

Prefer the first scaling step to be a larger VPS.

---

## Official documentation

Cloudflare DDoS:
https://developers.cloudflare.com/ddos-protection/

Cloudflare Tunnel:
https://developers.cloudflare.com/tunnel/

Cloudflare Turnstile:
https://developers.cloudflare.com/turnstile/

Cloudflare rate limiting:
https://developers.cloudflare.com/waf/rate-limiting-rules/

Cloudflare origin protection:
https://developers.cloudflare.com/fundamentals/security/protect-your-origin-server/

Caddy HTTPS:
https://caddyserver.com/docs/automatic-https

Docker Compose:
https://docs.docker.com/compose/
