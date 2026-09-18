# Desktop and Hosted Coexistence Part 1 num in query 8

**Stage 8 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Split desktop and hosted startup/auth paths, choose the static-asset strategy, and enable HTTPS, cookies, CSRF, and security headers.
- **Depends on:** stages 1-7 must be done (or their decisions recorded)
- **Source prompt sections:** §32, §33, §34, §35, §36, §37, §38  (part 1/2)

---
## 32. Remove desktop-only code from the hosted startup path

The hosted service does not need:

- `pystray`;
- desktop tray icon;
- single-instance Windows launcher;
- browser auto-opening from the server;
- Windows AppData logic;
- Windows console suppression;
- Nuitka runtime logic.

Do not necessarily delete the desktop code. Keep it if the repository will continue to ship a Windows build.

Instead, separate desktop-specific startup from shared application logic.

Recommended concept:

```text
backend/
    app.py / main.py              shared FastAPI app
    auth_web.py                    hosted OAuth
    auth_desktop.py                native desktop OAuth
    launcher.py                    Windows desktop only
```

Exact filenames may differ.

The hosted deployment should import only what it needs.

---

## 33. Decide how to keep desktop and hosted versions in one repository

Preferred design:

```text
shared business logic
        │
   ┌────┴─────┐
   │          │
Desktop      Hosted Web
```

Shared:

- Classroom API client;
- sync logic;
- SQLAlchemy/domain models where sensible;
- schemas/domain transformations;
- teacher/student business rules;
- grading logic;
- frontend components where shared UI is useful.

Desktop-specific:

- local OAuth loopback;
- local SQLite cache;
- Nuitka build;
- system tray;
- local token path.

Hosted-specific:

- web OAuth;
- web sessions;
- PostgreSQL;
- per-user background jobs;
- reverse proxy;
- production settings.

Do not force both deployment modes through the exact same authentication implementation.

---

## 34. Consider whether to maintain one frontend or separate desktop/web entry behavior

Prefer one React frontend when possible.

The desktop build can continue serving the same compiled SPA locally.

The hosted version serves the same or nearly the same SPA publicly.

Conditional behavior should be limited to actual environment differences, such as:

- hosted web login redirects to Google web OAuth;
- desktop login calls the local desktop OAuth route.

Do not fork the whole frontend into two independent applications unless necessary.

---

## 35. Production static asset strategy

The current FastAPI app already serves `frontend/dist` with SPA fallback.

For the hosted deployment choose one of these and document it:

### Option A — FastAPI serves the built SPA

Simple and keeps deployment close to the current project.

```text
Caddy → FastAPI
         ├── /api → API routes
         └── /    → React static files
```

### Option B — Caddy serves React static files

Potentially more efficient and conventional:

```text
Caddy
  ├── /api/* → FastAPI
  └── /      → static React files
```

Either is acceptable. Do not introduce unnecessary complexity.

Given the current project, Option A may be the easiest first production migration.

---

## 36. HTTPS is mandatory in production

The hosted site must run behind HTTPS.

Do not operate production OAuth callback flow over plain HTTP.

Use Caddy or another reverse proxy to terminate TLS.

Ensure:

- HTTP redirects to HTTPS;
- Secure cookies are enabled;
- HSTS can be considered after confirming correct HTTPS behavior;
- OAuth redirect URI is HTTPS;
- no credential-bearing URLs are logged or cached.

---

## 37. Cookie policy

The main session cookie should be approximately:

```text
HttpOnly
Secure
SameSite=Lax
Path=/
```

Consider a `__Host-` cookie prefix if the deployment supports the required constraints and there is no need for a Domain attribute.

Do not set a broad cookie Domain unless necessary.

Implement explicit session expiration and revocation.

Do not create permanent sessions by default without reviewing the security tradeoff.

---

## 38. CSRF protection

Because authentication uses cookies, review CSRF.

State-changing routes include at least:

- login initiation if it changes server state;
- logout;
- sync;
- cache clear/delete;
- any future write actions.

For the first implementation, use same-origin policy + `SameSite=Lax` plus an appropriate CSRF strategy for state-changing requests. A signed CSRF token or equivalent should be considered for endpoints where SameSite alone is not sufficient.

Do not assume CORS is a CSRF defense.

---

