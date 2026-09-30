# Frontend and Configuration Part 1 num in query 7

**Stage 7 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Adapt the frontend to cookie sessions and 401 handling; configure CORS, host validation, trusted proxy, and environment settings.
- **Depends on:** stages 1-6 must be done (or their decisions recorded)
- **Source prompt sections:** §26, §27, §28, §29, §30, §31  (part 1/2)

---
## 26. Frontend authentication behavior

Update React only as much as necessary.

Keep:

```ts
const BASE = "/api";
```

Use the same-origin browser session cookie.

Do not manually attach Google access tokens from React.

Do not store sensitive Google tokens in:

- localStorage;
- sessionStorage;
- IndexedDB;
- URL query parameters;
- React state persisted to disk.

On `401`, route the user back to the login state.

Make sure refresh/reload keeps the application session without exposing credential material.

If the current `SettingsContext` stores only harmless UI settings in localStorage, that can remain. Do not put authentication secrets into it.

---

## 27. CORS and same-origin policy

Because frontend and backend should be served from the same public origin, minimize CORS requirements.

Preferred production behavior:

```text
Browser → https://classroomhelp.pp.ua
Browser → https://classroomhelp.pp.ua/api/...
```

Same-origin requests do not need permissive CORS.

Remove the current local-only CORS/origin assumptions from the hosted configuration while keeping secure host validation.

Do not use:

```python
allow_origins=["*"]
allow_credentials=True
```

in production.

If any cross-origin frontend is intentionally kept, list exact trusted origins.

---

## 28. Replace localhost-only host protection with production host protection

The current backend explicitly rejects hosts other than `127.0.0.1` and `localhost`.

The hosted service must instead recognize the production domain, for example:

```text
classroomhelp.pp.ua
```

and localhost only in development.

Separate configuration by environment.

Example conceptual behavior:

```text
development:
    localhost / 127.0.0.1

production:
    classroomhelp.pp.ua
```

Do not hard-code the production hostname in many files.

Use configuration/environment variables.

---

## 29. Trusted proxy configuration

When deploying behind Caddy/Nginx, carefully configure proxy headers.

FastAPI/Uvicorn must correctly understand the external HTTPS scheme and host without blindly trusting arbitrary client-supplied headers.

Configure trusted proxy IPs/networks deliberately.

Make sure OAuth callback URLs are generated using the correct public HTTPS origin.

Do not create redirects to an internal URL such as:

```text
http://127.0.0.1:8000/...
```

in production.

---

## 30. Environment configuration

Create an explicit production configuration layer.

Recommended variables include:

```text
APP_ENV=production
APP_BASE_URL=https://classroomhelp.pp.ua

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://classroomhelp.pp.ua/api/auth/callback

DATABASE_URL=postgresql+psycopg://...

SESSION_SECRET=...
OAUTH_TOKEN_ENCRYPTION_KEY=...

COOKIE_SECURE=true
COOKIE_SAMESITE=lax

SYNC_INTERVAL_MINUTES=...
SYNC_MAX_WORKERS=...
```

Use names matching the project's style where practical, but do not create both `GC_DASHBOARD_*` and unrelated duplicate settings unless there is a reason.

Provide `.env.example` only.

Never commit the actual `.env`.

---

## 31. Path configuration changes

The current `path_config.py` is heavily oriented toward desktop/Nuitka builds.

For the hosted Linux service, stop treating `%LOCALAPPDATA%` as the data directory.

The hosted application should not depend on arbitrary process working directories.

Use explicit Linux/container filesystem paths.

For Docker, a common approach is:

```text
/app
/data
```

or similar, with PostgreSQL used for the database and `/data` used only for non-database runtime files when needed.

Do not store user OAuth tokens in the container filesystem as the main persistence mechanism.

Do not store production state inside the container image.

---

