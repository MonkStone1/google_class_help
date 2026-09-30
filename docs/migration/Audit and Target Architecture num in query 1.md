# Audit and Target Architecture num in query 1

**Stage 1 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Understand the current architecture, fix the target hosted architecture, find every single-user assumption, and classify all process-global state.
- **Depends on:** none — starting stage
- **Source prompt sections:** §1, §2, §3, §47

---
## 1. Current application architecture

The current application is primarily a local desktop application:

```text
Browser
   ↓
Vite dev server (development) OR FastAPI serving frontend/dist (production)
   ↓
FastAPI
   ├── auth.py
   ├── classroom_api.py
   ├── sync.py / sync_service.py / sync_store.py
   ├── database.py
   ├── models.py
   ├── schemas.py
   └── background_sync.py
   ↓
SQLite cache
   ↓
Google Classroom API
```

The production Windows build is a single Nuitka executable and stores user-specific data under `%LOCALAPPDATA%\GoogleClassHelp`.

The frontend already uses:

```ts
const BASE = "/api";
```

This is desirable and should be preserved. The hosted application should serve the frontend and backend from the same public origin, for example:

```text
https://classroomhelp.pp.ua/
https://classroomhelp.pp.ua/api/...
```

The frontend must never call Google APIs directly.

The backend remains the only component that communicates with Google Classroom.

---

## 2. Target architecture

The target is a real multi-user hosted web application.

Use this architecture unless a repository constraint requires a documented alternative:

```text
                           Internet
                              │
                              ▼
                    ┌──────────────────┐
                    │ Caddy / reverse  │
                    │ proxy + HTTPS    │
                    └────────┬─────────┘
                             │
                    same public origin
                             │
             ┌───────────────┴────────────────┐
             │                                │
             ▼                                ▼
     React static assets                    /api/*
             │                                │
             │                                ▼
             │                           FastAPI
             │                                │
             │                ┌───────────────┼───────────────┐
             │                │               │               │
             │                ▼               ▼               ▼
             │          PostgreSQL       Google OAuth    Classroom API
             │
             └────────── Browser session / UI
```

Recommended deployment platform:

- Linux VPS or equivalent host.
- Docker + Docker Compose for reproducible deployment.
- Caddy for HTTPS/reverse proxy because automatic TLS is desirable.
- PostgreSQL as the production database.
- FastAPI + Uvicorn for the application server.
- React/Vite built assets served either by FastAPI or, preferably, by the reverse proxy/static layer if that improves the deployment without complicating routing. Keep `/api` owned by FastAPI.

Do not use SQLite as the primary production database for the multi-user service.

Do not use a desktop/Nuitka architecture for the hosted deployment.

Do not require users to install Python, Node.js, or the Google Class Help executable to use the hosted web version.

---

## 3. First task: perform a repository audit before editing code

Before making changes:

1. Read the repository structure.
2. Read all relevant ADRs in `docs/adr/`.
3. Read the current `README.md`.
4. Inspect the actual authentication flow in `backend/auth.py`.
5. Inspect the current database and all SQLAlchemy models.
6. Inspect `backend/api.py`, `backend/main.py`, `backend/sync.py`, `backend/sync_service.py`, `backend/background_sync.py`, `backend/classroom_api.py`, and `backend/sync_store.py`.
7. Inspect frontend auth/status behavior and all API calls.
8. Identify every place that assumes:
   - one user;
   - one token file;
   - local loopback OAuth;
   - local filesystem storage;
   - SQLite;
   - localhost trusted hosts;
   - local-only CORS;
   - a process-global login state;
   - process-global profile cache;
   - process-global sync state.
9. Identify all places that must become user-scoped.
10. Do not assume a global variable is harmless just because the current desktop build has only one user.

Produce a brief migration audit in the repository, for example `docs/HOSTING_MIGRATION_AUDIT.md`, documenting what you found and what will change.

Do not expose or copy any real secrets into that document.

---

## 47. Remove unsafe process-global business state

Audit every module for global state.

Examples already identified:

- `_login_state`;
- `_profile_cache`;
- global sync state;
- global refresh coordination;
- anything derived from a single `TOKEN_FILE`.

For each global variable, determine whether it is:

1. truly immutable configuration;
2. safe process-wide infrastructure;
3. a cache that needs user keys;
4. user-specific state that must move to the database/session layer.

Do not blindly remove all globals. Make the classification explicit.

---

