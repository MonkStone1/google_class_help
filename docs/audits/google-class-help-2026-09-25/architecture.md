# Architecture

Product: Local Google Classroom dashboard (FastAPI + SQLite/PostgreSQL cache, React/Vite frontend). Two deployment modes: desktop (loopback OAuth, local owner) and hosted (web OAuth + server sessions, PostgreSQL).

Principals and authority:

- Anonymous browser: may request login initiation, OAuth callback, public Turnstile config, health/ready; no data access.
- Authenticated hosted user: session cookie maps to one local user; all cache reads/writes scoped by that user id; per-course teacher gates add role checks.
- Authenticated Google grant: per-user encrypted OAuth tokens authorize Classroom API calls for that user only.
- Desktop local owner: synthetic local user owns the single-machine cache; process-local token.json.
- Background worker/scheduler: acts per user with that user's credential, claimed via DB conditional update.
- Operator/deployer: controls env, Cloudflare Tunnel, Caddy, backups.

Protected resources: Google OAuth access/refresh tokens, session tokens, user Classroom cache across tenants, sync state, hosted configuration secrets, availability of shared web/worker/DB.

Stack and deployment: Python 3.12/3.13 FastAPI + SQLAlchemy + Alembic; React + Vite; PostgreSQL 16; Caddy internal reverse proxy; Cloudflare Tunnel edge; Docker Compose; Nuitka desktop build. Source-visible deployment paths: desktop uvicorn/launcher, hosted Docker web/worker/postgres/caddy/cloudflared.

Offline/test limits: source-only audit; no target execution, no sandbox available in this environment; hermetic tests exist but were not run here.

Entry surfaces and paths:

- HTTP browser/API: /api/auth/login, /api/auth/login/start, /api/auth/callback, /api/auth/logout, /api/auth/status, /api/auth/turnstile, data endpoints, sync, cache/account deletion.
- OAuth identity: Google consent, code exchange, userinfo, token refresh.
- Reverse-proxy headers: Host, Origin, X-Forwarded-Proto/Host/For, CF-Connecting-IP.
- Config/env: APP_ENV, HOSTED flag, base URL, hosts/CORS, trusted proxies, cookie flags, OAuth client, token encryption key, Turnstile keys, rate limits, DB pool, HSTS.
- Persistence lifecycle: users, sessions, login states, encrypted tokens, cache, sync status, retention sweeps, backups/restores, migrations.
- Release/build: npm/Node frontend build, pip backend image, Docker context, CI, Turnstile widget script.

Trust boundaries and strongest source-visible controls:

- Anonymous to authenticated: server-side random OAuth state + browser nonce, single-use callback, PKCE, fixed redirect URI, Google-issued identity only.
- User A to user B: session-derived owner id, composite PKs starting with user_id, per-query user scoping, per-user credential locks and sync claims.
- Browser to Google credential: Fernet encryption at rest, hashed session storage, HttpOnly cookie, secret redaction, query redaction.
- Internet to origin: Cloudflare Tunnel, Caddy body cap, trusted-proxy-gated forwarded headers, Host/Origin/fetch-metadata checks, rate buckets, short transactions, bounded pools.
- Build to runtime: pinned prod requirements, Docker non-root user, .dockerignore secrets exclusion, env-only secrets.

Starting paths:

- backend/main.py, backend/hosted_auth.py, backend/api.py, backend/ownership.py, backend/google_credentials.py, backend/proxy.py, backend/config.py, backend/oauth_transport.py, backend/token_crypto.py, backend/access_log.py, backend/rate_limit.py, backend/sync_service.py, backend/sync_store.py, backend/sync_scheduler.py, backend/sync_worker.py, backend/maintenance.py, backend/database.py, backend/models.py, backend/models_auth.py, backend/classroom_api.py
- frontend/src/api.ts, frontend/src/components/SignIn.tsx, frontend/src/context/DataContext.tsx
- Dockerfile, compose.yml, Caddyfile, migrations/, tools/backup_postgres.sh, .env.example, .dockerignore, .gitleaks.toml, .github/workflows/ci.yml

Prior coverage: no compatible prior ledger or findings were available; all units are newly seeded.

Companion selection: WEB-PROTOCOL-AND-AUTH for OAuth/session/proxy identity; DATA-ISOLATION-AND-LIFECYCLE for per-user cache/credential/deletion lineage; RESOURCE-EXHAUSTION-AND-AVAILABILITY for unauthenticated outbound calls, queues, pools and retries; CLOUD-AND-DEPLOYMENT for Tunnel/Caddy/Compose/container and env precedence; CLIENT-SIDE for React login/redirect/session handling; SUPPLY-CHAIN-AND-RELEASE for npm/pip/Docker/CI/update provenance.
