# Google Class Help — Server/Hosting Migration Implementation Prompt

You are an expert full-stack engineer taking over an existing production-oriented project called **Google Class Help**. Your task is to migrate the current **single-user local Windows application** into a **secure multi-user hosted web application** while preserving as much existing functionality and code structure as practical.

Do **not** rewrite the project from scratch. First audit the repository, understand the existing architecture and ADRs, then implement the migration incrementally. Preserve working student mode and teacher mode behavior unless a change is explicitly required by the hosted architecture.

The repository currently contains a React/Vite frontend, a FastAPI backend, SQLAlchemy models, Google Classroom API integration, Google OAuth, a local SQLite cache, background synchronization, teacher-mode pages/endpoints, and a Windows/Nuitka packaging path.

The existing project is intentionally well-layered. Keep that layering rather than moving Google API calls into React or duplicating business logic in multiple places.

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

## 4. Hard architectural decision: web OAuth instead of desktop OAuth

The hosted version must **not** use the current desktop loopback OAuth flow as its primary authentication flow.

The existing desktop OAuth flow was intentionally designed for a native application and includes a local callback server on `127.0.0.1`. That remains valid for the desktop build, but the hosted web application needs a proper web OAuth flow.

Use a **separate Google OAuth client of type Web application** for the hosted service.

Recommended Google Cloud arrangement:

```text
One Google Cloud project
├── Desktop OAuth client
│     └── existing local/Nuitka application
│
└── Web OAuth client
      └── hosted Google Class Help
```

Do not mix the redirect URI assumptions between the two clients.

The hosted application should use a redirect URI such as:

```text
https://classroomhelp.pp.ua/api/auth/callback
```

The exact path may differ if the implementation has a better route, but it must be HTTPS in production and must exactly match the Google Cloud Console configuration.

The web client secret is a real server-side secret and must never be shipped to the browser, embedded into React assets, or committed to Git.

---

## 5. Hosted OAuth flow

Implement a secure server-owned web OAuth flow.

Desired flow:

```text
Browser
  ↓
GET/POST /api/auth/login
  ↓
FastAPI generates OAuth authorization URL
  ↓
Browser redirects to Google
  ↓
Google consent/login
  ↓
Google redirects to
https://classroomhelp.pp.ua/api/auth/callback
  ↓
FastAPI validates OAuth state
  ↓
FastAPI exchanges authorization code
  ↓
FastAPI obtains Google credentials
  ↓
FastAPI identifies the Google user
  ↓
Create/find local user record
  ↓
Persist encrypted/protected token data server-side
  ↓
Create authenticated application session
  ↓
Redirect browser back to the dashboard
```

Important security requirements:

- Generate a cryptographically random OAuth `state` for every login attempt.
- Store state server-side or bind it securely to the initiating browser session.
- Reject state mismatches.
- Do not trust a user ID supplied by the frontend.
- Do not accept `user_id` as an authorization mechanism.
- Do not let the frontend select another local user by changing an ID in a URL.
- Use an application session after Google login.
- Prefer an opaque random session identifier stored in an `HttpOnly`, `Secure`, `SameSite` cookie.
- Do not store the application session token in localStorage if it can be avoided.
- Do not place Google access tokens or refresh tokens into frontend JSON responses.
- Do not place refresh tokens in browser cookies.
- Never log access tokens, refresh tokens, client secrets, authorization codes, or raw credential JSON.

---

## 6. Decide and document the session architecture

Use a server-side session model.

Recommended schema:

```text
users
sessions
oauth_tokens
```

Conceptually:

```text
users
-----
id
provider                 # google
provider_subject         # stable Google subject/user id
email                    # optional/local profile field
display_name
created_at
updated_at
last_login_at
is_active

sessions
--------
id / session_token_hash
user_id
created_at
expires_at
last_seen_at
revoked_at
user_agent              # optional, only if useful
ip_hash                  # optional; do not store raw IP without a reason

oauth_tokens
------------
user_id
access_token
refresh_token
token_uri
scopes
expires_at
created_at
updated_at
```

The exact schema can vary, but the following relationship must exist:

```text
Google account
      ↓
local User
      ↓
OAuth credentials
      ↓
session(s)
```

A user session is an application authentication concept. A Google OAuth token is a credential used by the backend when talking to Google APIs. Do not conflate the two.

Sessions should be revocable independently of Google tokens.

Logging out should revoke the application session. Decide whether the UI logout should also revoke/delete stored Google credentials. For the first hosted implementation, prefer:

- revoke the current application session;
- do not necessarily revoke the Google grant at Google;
- retain the refresh token server-side so the next login/session can be efficient if the application's security model permits it.

Document the decision and make sure the implementation matches it. A stronger privacy-oriented design may delete local OAuth credentials on explicit account removal.

---

## 7. User identity: use Google's stable subject identifier

Do not identify users solely by email.

Use Google's stable OpenID/OAuth subject identifier as the primary external identity key, or the equivalent stable Google user ID returned by the chosen Google identity endpoint.

Email can change. The stable subject is the identity link.

The implementation must correctly handle:

- first login;
- returning login;
- same Google account on a second browser;
- logout/login as a different Google account;
- two users with the same display name;
- changed email address;
- revoked Google authorization;
- expired access token with valid refresh token;
- invalid refresh token;
- deleted/deactivated local user.

---

## 8. Replace the single global token file

The current project has a single `TOKEN_FILE` and functions that load/save one credential set.

That design must be replaced for the hosted service.

Never do this in the hosted multi-user process:

```python
TOKEN_FILE = DATA_DIR / "token.json"
```

for all users.

Do not solve multi-user support by creating:

```text
users/user1/token.json
users/user2/token.json
```

unless there is a very strong reason. Database-backed credentials are easier to transactionally associate with a user, revoke, rotate, and secure.

Recommended approach:

- store OAuth credentials in PostgreSQL;
- encrypt the credential fields at rest using a server-side application encryption key if practical;
- keep the encryption key outside the database and outside source control;
- load/decrypt credentials only inside backend memory when needed;
- never return raw credentials through an API endpoint.

If implementing application-level encryption, use a standard authenticated encryption construction/library. Do not invent custom XOR/base64 encryption.

The existing desktop `embedded_secrets.py` / XOR obfuscation mechanism is not an acceptable security mechanism for server secrets.

---

## 9. Secret management

Separate secrets into categories.

### Public client identifier

The Google OAuth `client_id` is not a security boundary and may be present in frontend configuration when appropriate, but keep the web OAuth implementation server-owned anyway.

### Server-only secrets

These must remain on the server:

- Google web OAuth client secret;
- session signing/encryption key, if using signed sessions;
- OAuth-token encryption key, if used;
- PostgreSQL password/connection credentials;
- any future server API keys;
- any SMTP credentials if email is later added.

Inject them through environment variables or the hosting platform's secret mechanism.

Never:

- commit them;
- put them in React source;
- put them into `frontend/dist`;
- put them into logs;
- put them into GitHub Pages;
- put them into Docker image layers when avoidable;
- put them into a public `.env` file.

Provide a safe `.env.example` with placeholders only.

---

## 10. Database migration: SQLite → PostgreSQL

The hosted version should use PostgreSQL.

Do not continue to use the local SQLite cache as the production primary datastore.

The existing SQLAlchemy models can be reused conceptually, but they are currently designed around a single authenticated user. That must change.

Current examples include:

- `Course`
- `CourseWork`
- `StudentSubmission`
- `CourseRole`
- `CourseStudent`
- `CourseWorkSubmission`
- `SyncState`

The key architectural change is user ownership.

At minimum, cache records that can differ by Google account must become user-scoped.

A safe conceptual model is:

```text
users
  │
  ├── courses
  │      ├── coursework
  │      ├── course_roles
  │      ├── course_students
  │      ├── student_submissions
  │      └── coursework_submissions
  │
  ├── oauth_tokens
  └── sessions
```

Possible columns:

```text
courses
-------
id                     # local PK may be composite or internal integer
user_id                # FK to users
provider_course_id     # Google Classroom course id
...
```

For Coursework:

```text
coursework
----------
id
user_id
course_id
provider_coursework_id
...
```

For student submissions:

```text
submissions
-----------
user_id
course_id
coursework_id
...
```

For teacher submissions:

```text
coursework_submissions
----------------------
user_id
course_id
coursework_id
student_id
...
```

For teacher course roles:

```text
course_roles
------------
user_id
course_id
role
```

For course students:

```text
course_students
---------------
user_id
course_id
student_id
...
```

Do not blindly add `user_id` everywhere without reviewing primary keys and uniqueness constraints.

A Google Classroom course ID may be identical across different authenticated users. The cache must never assume global uniqueness for user-specific records.

Use uniqueness constraints appropriate to the scope, for example:

```text
(user_id, provider_course_id)
(user_id, provider_coursework_id)
(user_id, course_id, coursework_id)
(user_id, course_id, coursework_id, student_id)
```

The exact schema must be based on the existing foreign-key relationships and actual query patterns.

---

## 11. Add proper database migrations

Do not rely on `Base.metadata.create_all()` as the production schema migration system.

Introduce a real migration mechanism, preferably Alembic, for PostgreSQL.

Required migration path:

1. Fresh installation creates the full schema.
2. Existing development databases can be recreated or migrated in a controlled way.
3. Production migrations are versioned.
4. Destructive schema changes require explicit review.
5. No production deployment should depend on silently creating missing columns.

A local legacy SQLite database does not need to be migrated automatically unless there is a concrete requirement. If migration from existing user data is implemented, provide a deliberate import/migration script rather than guessing.

---

## 12. User data isolation is a hard security requirement

This is one of the most important parts of the migration.

Every data access path must be filtered by the authenticated user.

A request such as:

```text
GET /api/courses/123
```

must mean:

```text
current session user
        ↓
lookup course 123 belonging to current user
        ↓
return it or 404/403
```

It must never mean:

```text
lookup global Course(id=123)
```

without a user constraint.

Audit every endpoint for IDOR-style vulnerabilities.

Specifically review:

- `/api/courses`
- `/api/courses/{course_id}`
- `/api/courses/{course_id}/coursework`
- `/api/courses/{course_id}/students`
- `/api/courses/{course_id}/grades`
- `/api/courses/{course_id}/coursework/{coursework_id}`
- `/api/courses/{course_id}/coursework/{coursework_id}/submissions`
- `/api/courses/{course_id}/students/{student_id}/grades`
- `/api/assignments`
- `/api/grades`
- `/api/calendar`
- `/api/status`
- `/api/sync`
- `/api/cache`
- all auth/session routes.

Also check indirect lookup paths. A user must not be able to reach another user's coursework by guessing its Google ID.

Prefer repository/service functions that receive an authenticated `user_id` and enforce ownership centrally instead of repeating fragile checks in every route.

---

## 13. Introduce an authenticated-user dependency

Create a reusable FastAPI dependency such as:

```python
current_user = Depends(get_current_user)
```

or an equivalent design.

The dependency should:

1. read the secure application session cookie;
2. validate the session;
3. load the local User record;
4. reject missing/expired/revoked sessions;
5. expose the authenticated user to route handlers.

Do not make route handlers trust a frontend-supplied `user_id`.

For example, prefer:

```python
@router.get("/courses")
def courses(current_user: User = Depends(get_current_user)):
    ...
```

rather than:

```python
@router.get("/courses")
def courses(user_id: int):
    ...
```

---

## 14. Application auth and Google auth must be separate layers

Keep these concerns separate:

```text
Authentication layer
    ↓
Who is the current local application user?

Google credential layer
    ↓
What Google OAuth credentials belong to that user?

Classroom service layer
    ↓
Use those credentials to call Google Classroom
```

Do not let `classroom_api.py` decide who the local browser user is.

Do not let React hold a Google token.

Do not make Classroom routes accept a token supplied by the browser.

---

## 15. Refactor the existing Google credential functions

The current functions such as:

- `load_credentials()`
- `get_valid_credentials()`
- `_save_credentials()`
- `logout()`

are process/global-user oriented.

Refactor them into user-scoped operations.

Conceptual interface:

```python
get_google_credentials(user_id)
save_google_credentials(user_id, credentials)
refresh_google_credentials(user_id)
delete_google_credentials(user_id)
```

The refresh lock must also become user-aware.

Current global refresh serialization is suitable for one user. On a multi-user server, do not allow one user's refresh traffic to block all users unnecessarily.

A per-user refresh lock or database-level coordination mechanism is preferable.

The implementation should still prevent duplicate concurrent refresh requests for the same user's token.

---

## 16. Refactor the current global login state

The existing `_login_state` is a global dictionary and is only safe because the current desktop app has one user.

For a hosted web app, do not use one global:

```python
{
    "in_progress": ...,
    "error": ...,
    "auth_url": ...,
}
```

for everyone.

Login attempts need to be correlated to the initiating browser/session.

Do not allow:

```text
User A starts OAuth
User B polls /api/auth/status
User B sees User A's OAuth URL/state/error
```

Use a short-lived login transaction keyed to a secure browser cookie or server-side transaction ID.

---

## 17. Profile caching must become user-scoped

The current profile cache is global:

```python
_profile_cache
```

This is unsafe when multiple users are logged in.

Replace it with a user-scoped cache, database value, or a short-lived cache keyed by local user ID.

At minimum:

```text
user_id -> profile cache
```

Never allow User B to receive User A's cached name/email.

---

## 18. Refactor background synchronization for multiple users

The current background synchronization is a single process-global loop designed for one local user.

Do not simply run the existing loop unchanged on a public server.

The hosted system needs a scheduler/worker model that processes users independently.

Recommended first implementation:

```text
Scheduler
   ↓
find active users that are due for sync
   ↓
queue/execute user-specific sync jobs
   ↓
for each user:
    load that user's Google credentials
    sync only that user's Classroom data
    update that user's sync state
```

Do not hold one global lock around all users.

Use per-user concurrency control.

Prevent the same user's sync from running twice concurrently.

Do not let one broken OAuth token or one API 403 stop synchronization for other users.

Record sync state per user.

The current `SyncState(key, value)` table is global. Change it to something like:

```text
sync_state
----------
user_id
key
value
```

or a dedicated structured table.

Recommended fields:

```text
last_started_at
last_finished_at
last_success_at
last_error
status
```

Do not expose raw exception traces or credential data to the frontend.

---

## 19. Decide how the production scheduler will run

A simple first production deployment may use a dedicated application worker process or a lightweight scheduler container.

Do not depend on FastAPI startup hooks alone if the server may run multiple replicas/workers.

If using multiple containers or multiple Uvicorn workers, a process-local scheduler can cause duplicate sync jobs.

Preferred choices:

### Option A: dedicated worker container

```text
web container
worker container
postgres container
caddy container
```

The worker owns background synchronization.

### Option B: external scheduler + job queue

Use this only if the project scale actually requires it.

Do not add Celery/Redis/etc. merely for complexity. Start with the simplest architecture that is correct for the expected user count.

Document the chosen approach.

---

## 20. Preserve the existing staged/parallel sync logic

The current project already has staged parallel synchronization and retry/backoff decisions documented in its ADRs.

Do not throw that work away.

Reuse the existing Google Classroom API client and synchronization logic where possible.

But add a `user_id` context to sync operations.

Conceptually:

```python
sync_user(user_id)
```

instead of:

```python
sync_now()
```

with hidden process-global user state.

The Google service object and credentials must be associated with the current user.

---

## 21. Teacher mode must remain per-course and per-user

The existing teacher mode correctly recognizes that one Google account may be a teacher in some courses and a student in others.

Preserve this behavior.

The hosted migration must not collapse the role to a single account-level boolean.

The correct conceptual model remains:

```text
User
 ├── Course A → STUDENT
 ├── Course B → TEACHER
 └── Course C → STUDENT
```

Teacher-mode data is also user-owned.

Do not let another user access:

- teacher rosters;
- submissions of students in that teacher's courses;
- grades;
- course statistics;
- teacher-only coursework.

All teacher endpoints must enforce both:

```text
current authenticated user
AND
course role == TEACHER
```

The existing read-only Classroom scopes should be preserved unless the Google API implementation requires a documented adjustment.

Current intended read-only scope set:

```text
https://www.googleapis.com/auth/classroom.courses.readonly
https://www.googleapis.com/auth/classroom.student-submissions.me.readonly
https://www.googleapis.com/auth/classroom.student-submissions.students.readonly
https://www.googleapis.com/auth/classroom.rosters.readonly
```

Do not add write scopes merely for convenience.

Do not request student email access unless the feature genuinely requires it and the privacy/verification implications have been reviewed.

---

## 22. Preserve the important semantic rules

The existing project contains important business semantics. Preserve them during migration.

Examples:

- Missing grade is not zero.
- Student and teacher assignment views are different.
- Teacher aggregates must not be interpreted as the teacher's personal submission.
- Archived courses are filtered appropriately.
- Submission states remain explicit.
- `not_submitted`, `turned_in`, `returned`, and `graded` semantics should not regress.
- Derived percentages remain consistent.
- Client-side calendar/search/filter behavior should keep working unless moved server-side for a concrete reason.

Do not silently change business meaning while performing infrastructure migration.

---

## 23. Rework the API surface carefully

The frontend currently uses `/api/...` and should continue to do so.

The API may gain routes such as:

```text
GET  /api/auth/status
POST /api/auth/login
GET  /api/auth/callback
POST /api/auth/logout

GET  /api/me

GET  /api/courses
GET  /api/courses/{course_id}
GET  /api/courses/{course_id}/coursework
GET  /api/courses/{course_id}/students
GET  /api/courses/{course_id}/grades
GET  /api/courses/{course_id}/coursework/{coursework_id}
GET  /api/courses/{course_id}/coursework/{coursework_id}/submissions
GET  /api/courses/{course_id}/students/{student_id}/grades

GET  /api/assignments
GET  /api/grades
GET  /api/calendar
GET  /api/status
POST /api/sync
```

Adapt the exact set to the current implementation rather than duplicating routes.

The backend should return `401 Unauthorized` when there is no valid application session.

Use `403 Forbidden` when the user is authenticated but lacks permission for the requested resource (for example, a student opening teacher-only course data).

Use `404 Not Found` when appropriate for resources that do not belong to the current user, depending on the desired information-disclosure policy. Avoid leaking whether another user's resource exists.

---

## 24. Rework `/api/auth/status`

The hosted auth status should describe the current browser's application session, not a global server login.

A reasonable response shape:

```json
{
  "authenticated": true,
  "user": {
    "id": "local-id",
    "name": "...",
    "email": "..."
  }
}
```

Do not include:

- access tokens;
- refresh tokens;
- client secret;
- OAuth authorization code;
- full Google credential object.

The frontend should not need to know any Google OAuth internals beyond whether login is required and perhaps a display name/email.

---

## 25. Login UX changes

The current local application can automatically open a browser window and expose an OAuth URL in its settings.

For the hosted web application, the desired UX is simpler:

```text
User opens site
    ↓
Not authenticated
    ↓
"Sign in with Google"
    ↓
Google consent
    ↓
redirect back
    ↓
dashboard
```

Do not expose loopback callback URLs in the hosted UI.

Do not require copying authorization URLs from logs.

The desktop OAuth UX should remain separate from the web OAuth UX.

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

## 39. Rate limiting and abuse controls

A public service changes the threat model dramatically compared with localhost.

At minimum, consider rate limits for:

- `/api/auth/login`;
- OAuth callback errors/retries;
- `/api/sync`;
- `/api/cache` destructive operations;
- any expensive teacher-grade endpoints if they ever read live Google data.

Do not expose an unrestricted endpoint that can cause continuous Google API calls.

`/api/sync` should trigger a user-scoped sync with cooldown/de-duplication.

Do not allow one user to consume the entire Google API quota by pressing Sync repeatedly.

---

## 40. Google API quota and multi-user scaling

The current local project configures around one authenticated user and has 16 synchronization workers.

On a hosted service, `16 workers` cannot automatically be treated as a global safe setting.

Reason about:

```text
number of active users
×
requests per sync
×
concurrent users
```

Google quotas apply per user and also at project/client levels.

Implement per-user throttling and global concurrency limits as appropriate.

Do not create a huge global thread pool simply because it worked for one user.

The first production version can use conservative defaults and observability rather than trying to maximize throughput prematurely.

---

## 41. Handle Google token failures correctly

When a user's refresh token becomes invalid or authorization is revoked:

1. mark that user's Google authentication as needing reauthorization;
2. stop trying to refresh forever;
3. keep the application session behavior explicit;
4. return a frontend-safe status indicating that Google access needs to be reconnected;
5. do not sign out every user on the server;
6. do not delete other users' credentials.

A Google 401/invalid_grant for User A must never globally invalidate User B.

---

## 42. Logging

The current desktop project logs to `%LOCALAPPDATA%\GoogleClassHelp\logs\app.log`.

Hosted deployment should use standard structured application logs to stdout/stderr, allowing Docker/systemd/hosting to capture them.

Logs must be safe by default.

Never log:

- access tokens;
- refresh tokens;
- Google client secrets;
- session cookies;
- authorization codes;
- full credential JSON;
- raw sensitive student data unless explicitly justified.

OAuth errors should log technical details server-side, but the frontend should receive a short safe message.

Use full tracebacks in server logs where useful.

Do not return a raw traceback to a browser.

---

## 43. Student privacy and data minimization

The hosted application may process classroom information belonging to students and teachers.

Review all stored data and ask for each field:

- Is it required for the UI?
- Is it required for synchronization?
- Can it be derived instead of stored?
- Should it have a retention limit?

Do not introduce unnecessary sensitive fields merely because Google provides them.

The existing project intentionally avoids requesting student profile emails unless needed. Preserve that principle.

Be especially careful with:

- student names;
- student identifiers;
- grades;
- submissions;
- attachments;
- profile photos;
- teacher data.

Do not create public APIs that expose these records without authentication and ownership checks.

---

## 44. Data retention and deletion policy

Decide what happens when a user:

- logs out;
- disconnects Google;
- deletes their local account;
- stops using the service;
- requests data deletion.

At minimum, design an account deletion path that can remove:

```text
sessions
OAuth credentials
cached courses
coursework
submissions
teacher rosters
sync state
```

for that user only.

Do not implement a global destructive cache clear for all hosted users.

The current `/api/cache?confirm=true` endpoint is dangerous in its existing global form and must be changed to operate only on the authenticated user's cache.

Consider whether the action should require additional confirmation or CSRF protection.

---

## 45. Database transaction boundaries

Review existing SQLAlchemy session patterns.

On the hosted service:

- use short transactions;
- avoid holding transactions open across network calls to Google;
- do not use one SQLAlchemy `Session` across worker threads;
- create sessions per job/request as appropriate;
- use proper connection pooling for PostgreSQL;
- close sessions reliably.

The existing ADRs intentionally avoided sharing SQLAlchemy sessions across worker threads. Preserve the underlying principle.

---

## 46. Concurrency rules

Multi-user production introduces several race conditions that the local application did not have.

Explicitly address:

### Same user, two browser tabs

Both tabs should share the same application session.

### Same user, two simultaneous OAuth callbacks

Only one should create/update the expected login transaction.

### Same user, concurrent token refresh

Avoid duplicate refresh requests.

### Same user, two manual sync clicks

Do not launch duplicate full syncs.

### Same user, manual sync + scheduled sync

Only one should run at a time.

### Different users, simultaneous sync

User A must not block User B unnecessarily.

### Different users, same Google course ID

Their cached data must remain isolated.

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

## 48. Security headers

Configure appropriate production headers, either in Caddy or FastAPI, including as appropriate:

- `Strict-Transport-Security` after HTTPS is stable;
- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy` with a privacy-conscious value;
- `X-Frame-Options` or an appropriate CSP `frame-ancestors` policy;
- a Content Security Policy appropriate for the actual React bundle and Google OAuth redirects.

Do not add a CSP that breaks the app without testing it.

Document any external origins required by the frontend.

---

## 49. Frontend security review

Search the built frontend and source tree for accidental secrets.

Check that no production build contains:

- client secret;
- PostgreSQL credentials;
- session secret;
- OAuth token;
- refresh token;
- internal hostnames that should not be public;
- development `.env` values.

Remember that anything in `frontend/dist` is public.

---

## 50. Google OAuth verification / branding compatibility

The hosted app is intended to be a public web service and already has a public domain planned for its privacy/terms/branding pages.

Ensure the implementation supports these production OAuth requirements:

```text
https://classroomhelp.pp.ua/
https://classroomhelp.pp.ua/privacy
https://classroomhelp.pp.ua/terms
```

The exact page paths may be different, but there must be publicly accessible pages for the information Google requires.

The OAuth branding and privacy URLs must match the actual hosted service.

Do not put the hosted OAuth client secret in GitHub Pages or any public static hosting.

---

## 51. Development vs production configuration

Preserve a convenient development workflow.

Development should still support something like:

```text
FastAPI
Vite
PostgreSQL or a clearly documented local database setup
Google OAuth development client / redirect URI
```

Do not require production secrets to run frontend unit tests.

Use separate configuration for:

```text
local development
CI/test
production
```

Prefer a dedicated development Google OAuth client if practical.

Do not make local development depend on the production database.

---

## 52. Testing strategy

Add automated tests for the hosted architecture.

At minimum test:

### Authentication

- unauthenticated request → 401;
- valid session → current user;
- expired session → 401;
- revoked session → 401;
- logout invalidates session;
- OAuth state mismatch rejected;
- OAuth callback cannot be replayed;
- two login transactions do not interfere.

### User isolation

Create User A and User B with overlapping Google-like IDs and verify:

- A cannot read B's courses;
- A cannot read B's coursework;
- A cannot read B's grades;
- A cannot read B's teacher roster;
- A cannot clear B's cache;
- A cannot trigger B's user-scoped sync.

### OAuth credentials

- User A's token is never returned to frontend;
- User B does not receive A's credentials;
- token refresh is scoped to one user;
- invalid refresh token affects only one user.

### Sync

- two users can synchronize concurrently;
- one user can only have one active sync;
- scheduled and manual sync do not duplicate one another;
- a failure for one user does not stop others.

### Teacher mode

- teacher course remains teacher for that user;
- same Google user can be student in another course;
- teacher-only endpoints reject student courses;
- student cannot access another user's teacher data.

### Database

- migration from clean database;
- startup against current schema;
- foreign keys and cascading behavior;
- concurrent request safety;
- connection pool behavior.

---

## 53. Add integration-test fixtures

Create a fake Classroom/Google provider layer or mock the existing client so tests do not require real Google credentials.

Use fixture users like:

```text
user_a
user_b
```

and courses like:

```text
course_shared_id
course_teacher_a
course_student_b
```

The key test is that the same provider-level ID can exist independently in each user's cache when semantically appropriate.

---

## 54. Production deployment files

Create deployment configuration such as:

```text
Dockerfile
compose.yml / docker-compose.yml
Caddyfile
.env.example
```

The exact filenames are flexible.

Recommended container layout:

```text
caddy
web
worker
postgres
```

A separate worker container is strongly preferred if scheduled sync is retained.

Do not publish PostgreSQL directly to the public internet.

Expose only the reverse proxy publicly.

The FastAPI container should be on an internal Docker network.

---

## 55. Database networking

Do not bind PostgreSQL to `0.0.0.0` on the public host unless there is a specific administrative requirement.

Prefer:

```text
Caddy → web
web → postgres
worker → postgres
```

inside Docker's private network.

Only Caddy should need a public HTTP/HTTPS port.

---

## 56. Persistent storage

Make PostgreSQL persistent using a Docker volume or a managed database.

Do not store production database contents inside ephemeral container layers.

If any non-database persistent files remain necessary, mount them explicitly.

Backups must be considered before calling the deployment production-ready.

---

## 57. Backup and recovery

Document:

- how PostgreSQL backups are made;
- where backups are stored;
- how often;
- how to restore;
- how secrets are restored;
- what data must be backed up together.

At minimum, create a simple documented PostgreSQL dump procedure suitable for the expected small deployment.

---

## 58. Health and readiness endpoints

Retain a lightweight health endpoint, for example:

```text
GET /api/health
```

But do not report secrets or detailed infrastructure information.

Consider:

```text
/api/health
/api/ready
```

where readiness can verify database connectivity if appropriate.

A health endpoint should not require Google authentication if it is intended for the reverse proxy/container health check.

---

## 59. Error handling

Audit exception handling.

Public production responses should be safe and concise.

Do not return raw exceptions such as:

```text
OSError(...)
Traceback...
client_secret...
SQL statement...
```

to users.

Server logs may contain detailed traces.

Map common cases to stable frontend-understandable error statuses/messages:

```text
401 — authentication required
403 — not permitted
404 — not found
409 — operation already running
429 — try again later
502/503 — upstream/service unavailable
```

---

## 60. Observability

Add enough logging/metrics to understand:

- active users;
- login successes/failures;
- sync duration per user;
- sync success/failure per user;
- Classroom API 429/5xx counts;
- database errors;
- worker crashes;
- session/auth failures.

Do not log personally sensitive classroom data unnecessarily.

Prefer IDs that are safe to use operationally, or one-way hashes if needed for correlation.

---

## 61. Review cache semantics

The current application treats the database as a cache of Google Classroom state.

In the hosted app, this remains useful, but the cache becomes persistent server-side data.

Explicitly decide:

- what is authoritative (Google Classroom);
- what is cached locally (PostgreSQL);
- what happens after a missed sync;
- how stale data is displayed;
- whether stale data has a TTL;
- how deletions are reflected;
- how archived courses are handled.

Do not silently represent stale data as current.

Expose last-sync metadata per user.

---

## 62. Avoid accidental cross-user cache sharing

Any cache key currently based only on Google resource ID must be reviewed.

Unsafe example:

```text
cache[course_id]
```

Safe conceptual key:

```text
cache[(user_id, course_id)]
```

This includes in-memory caches as well as database tables.

The same review applies to:

- profile cache;
- role map;
- loaded assignment dictionaries;
- submission lookups;
- any future Redis cache.

---

## 63. Background sync and user lifecycle

Only active users with valid/usable Google authorization should be candidates for scheduled sync.

Do not sync deleted or disabled users.

When refresh fails permanently:

```text
mark user as needs_reauth
```

and pause scheduled sync until reauthorization.

Avoid retry storms.

---

## 64. Avoid synchronized startup storms

If there are many users, do not run a full Classroom sync for every account at exactly the same instant after deployment.

Use jitter/staggering or a queue.

The current local behavior of “sync immediately at startup” was designed for one user. For hosted deployment, preserve freshness without creating a startup thundering herd.

---

## 65. Explicitly review teacher-mode API volume

Teacher mode can generate significantly more Google Classroom requests than the student view because it may load:

- all coursework;
- roster;
- all student submissions;
- related teacher/course data.

Keep the existing parallel staged approach but add:

- user-level concurrency limits;
- global limits;
- backoff;
- observability;
- pagination correctness.

Do not assume one teacher sync is representative of server-wide load.

---

## 66. Security review of destructive endpoints

The current local cache-clear endpoint is acceptable only because the app is local to one user.

In hosted mode:

```text
DELETE /api/cache?confirm=true
```

must only delete the authenticated user's cached data.

Do not allow an unauthenticated request to wipe anything.

Consider renaming it to something more explicit such as:

```text
DELETE /api/me/cache
```

if that improves clarity.

---

## 67. API response ownership

Every API response containing user data must have an obvious ownership path.

Examples:

```text
Assignment
  → Course
    → User
```

or

```text
CourseWorkSubmission
  → CourseWork
  → Course
  → User
```

Avoid query patterns that can accidentally join across users.

Use explicit SQLAlchemy filters.

---

## 68. Database indexes

Once `user_id` is introduced, add indexes based on actual query patterns.

Likely candidates include:

```text
courses(user_id)
coursework(user_id, course_id)
submissions(user_id, course_id, coursework_id)
course_roles(user_id, course_id)
course_students(user_id, course_id)
coursework_submissions(user_id, course_id, coursework_id)
sessions(user_id, expires_at)
```

Do not add dozens of indexes blindly. Use the actual query plan and expected workload.

---

## 69. PostgreSQL compatibility details

Review SQLite-specific assumptions such as:

- SQLite-specific SQL;
- implicit transaction behavior;
- JSON behavior;
- Boolean behavior;
- datetime semantics;
- `ON CONFLICT` syntax;
- case sensitivity;
- null handling;
- connection/thread assumptions.

Keep SQLAlchemy abstractions wherever possible.

Use PostgreSQL-native types only when they provide a concrete benefit.

---

## 70. Time and timezone handling

The existing project has explicit datetime semantics and stores certain values as naive datetimes.

Do not change timezone behavior accidentally during the migration.

Review:

- Google Classroom timestamps;
- due dates;
- PostgreSQL `timestamp with time zone` vs `timestamp without time zone`;
- user locale/display timezone;
- calendar calculations;
- server timezone;
- DST.

A hosted server should normally operate in UTC internally.

Convert to user-facing timezone at the UI boundary where appropriate.

Document any required migration.

---

## 71. Production database credentials and least privilege

Create a PostgreSQL role dedicated to the application.

Do not run the application as the PostgreSQL superuser.

Do not expose PostgreSQL admin credentials to the web container.

Use separate roles for migration/administration if practical.

---

## 72. Container security

Prefer:

- non-root application container;
- minimal base image;
- pinned dependency versions for production builds;
- regular dependency updates;
- no shell/debug tools in production image unless needed;
- read-only filesystem where practical;
- writable directories only where needed.

Do not bake secrets into Docker images.

---

## 73. Dependency management

The current project has a Python `requirements.txt` with broad minimum versions.

For production reproducibility, decide on a pinning strategy.

At minimum, generate a reproducible lock/constraints file or pin production dependencies in an appropriate format.

Do the same for frontend dependencies using the existing `package-lock.json`.

Do not upgrade every dependency just because the project is being migrated.

Upgrade only when necessary and test each meaningful change.

---

## 74. Keep current desktop production support intact unless intentionally removed

The repository already contains:

- Nuitka build decisions;
- Windows launcher;
- `path_config.py` compiled-build logic;
- embedded OAuth client obfuscation;
- local loopback OAuth implementation;
- tray/single-instance functionality.

Do not destroy these features merely to create the hosted version.

Refactor shared code so the desktop and hosted targets coexist safely.

The hosted web deployment should not import Windows-only desktop modules.

---

## 75. Desktop OAuth and hosted OAuth must use separate redirect configuration

Desktop:

```text
loopback 127.0.0.1 + random/free local port
```

Hosted:

```text
https://classroomhelp.pp.ua/api/auth/callback
```

Do not dynamically reuse one redirect URI implementation for both modes unless the code clearly handles both paths without weakening security.

---

## 76. Do not expose the hosted OAuth client secret through Nuitka or React

The desktop embedded secret mechanism and hosted server secret mechanism are different security domains.

For desktop:

- the client secret is not a true security boundary;
- obfuscation is only a casual-observation measure.

For hosted:

- the web client secret is server-only;
- it must never be in the browser;
- it must never be in public repository artifacts.

Document this distinction.

---

## 77. Migration of existing local development data

Do not automatically upload `data/token.json` or `data/classroom.db` to production.

Those files are user-local development data and may contain private Google information.

Add them to the migration documentation as explicitly excluded from source control and deployment artifacts.

Do not put:

```text
data/token.json
data/classroom.db
backend/credentials.json
backend/embedded_secrets.py
.env
```

into Docker images or GitHub repositories.

---

## 78. Repository hygiene

Review `.gitignore` and ensure the following are ignored:

```text
.env
.env.*
! .env.example

backend/credentials.json
backend/embedded_secrets.py

data/token.json
data/classroom.db
data/logs/

__pycache__/
*.pyc

frontend/node_modules/
frontend/dist/
```

Adjust to the project's actual build strategy.

Check `git status` and repository history for accidentally committed credentials.

If a secret was ever committed publicly, assume it is compromised and rotate it rather than merely deleting the file in a later commit.

---

## 79. Update README and deployment documentation

Rewrite the README so that it clearly explains there are now two deployment modes:

```text
Desktop/local
Hosted web
```

Document:

- development setup;
- local desktop setup;
- hosted environment variables;
- Google Cloud OAuth configuration;
- database setup;
- migration commands;
- Docker Compose startup;
- Caddy/domain setup;
- backup/restore basics;
- OAuth callback URI;
- security warnings;
- how to run tests.

Do not include actual secrets.

---

## 80. Add ADRs for major architecture decisions

Create/update ADRs for at least:

1. Hosted multi-user architecture.
2. Web OAuth client separate from desktop OAuth client.
3. PostgreSQL replacing SQLite for hosted deployment.
4. Server-side sessions.
5. User-scoped OAuth credential storage.
6. Multi-user background synchronization.
7. Docker/Caddy deployment strategy.

Do not rewrite historical ADRs to pretend the project was always hosted. Preserve history and add new decisions.

---

## 81. Migration implementation order

Use this order unless the audit proves a better sequence:

```text
1. Audit current code and identify globals
        ↓
2. Add user/session domain model
        ↓
3. Add PostgreSQL + Alembic
        ↓
4. Refactor ownership into models/queries
        ↓
5. Implement hosted Google OAuth
        ↓
6. Store Google credentials per user
        ↓
7. Add get_current_user dependency
        ↓
8. Make all API queries user-scoped
        ↓
9. Refactor sync to user-scoped jobs
        ↓
10. Refactor teacher mode to user-scoped data
        ↓
11. Adapt frontend auth UX
        ↓
12. Add production CORS/host/cookie/CSRF config
        ↓
13. Add Docker + Caddy + PostgreSQL deployment
        ↓
14. Add tests and security tests
        ↓
15. Run full regression test
        ↓
16. Update documentation
```

Do not start with Docker before the application model is correct.

---

## 82. Non-negotiable acceptance criteria

The migration is not complete until all of these are true:

### Authentication

- A user can sign in with Google through the hosted web flow.
- OAuth state is validated.
- The server creates a secure application session.
- The browser receives only a secure session cookie, not a Google token.
- Logout invalidates the application session.

### User isolation

- At least two users can use the service simultaneously.
- Their courses, coursework, submissions, grades, teacher rosters, and sync states remain isolated.
- Changing IDs in request URLs cannot access another user's resources.

### OAuth credentials

- Each user has their own Google credentials.
- Credentials are stored server-side.
- Server secrets are not present in frontend assets.
- Tokens are never logged.

### Google Classroom

- Existing student mode remains functional.
- Existing teacher mode remains functional.
- Per-course teacher/student roles remain correct.
- Read-only scope model remains intact unless explicitly changed for a documented reason.

### Sync

- User A can sync while User B is also using the service.
- Sync state is per user.
- Duplicate syncs for the same user are prevented.
- A failure for one user does not globally break synchronization.

### Database

- Production uses PostgreSQL.
- Schema is managed with migrations.
- User-specific records have correct ownership keys and constraints.

### Deployment

- Frontend and backend are served from one HTTPS origin.
- Caddy/reverse proxy terminates HTTPS.
- PostgreSQL is not publicly exposed.
- Containers or services restart safely.
- Persistent database storage exists.

### Security

- No real secrets are committed.
- No OAuth tokens are exposed to frontend code.
- No server secret is embedded into React assets.
- No public endpoint can access another user's classroom data.
- Destructive actions are authenticated and user-scoped.

---

## 83. What NOT to do

Do not:

- rewrite the entire project from scratch;
- keep one global `token.json` on the server;
- keep one global authenticated user;
- use a global process login state for all browsers;
- put Google refresh tokens into localStorage;
- return OAuth tokens from `/api/auth/status`;
- trust `user_id` sent by the client;
- use Google email alone as the permanent identity key;
- use SQLite as the production multi-user database;
- expose PostgreSQL publicly;
- embed the web client secret in React;
- store secrets in the Docker image;
- use XOR/base64 as encryption for server credentials;
- use `allow_origins=["*"]` with credentials;
- leave the localhost-only host guard enabled in production;
- make every user sync at exactly the same instant after deployment;
- let one user's Google API failure log out or break every user;
- make every sync request hit Google live if the existing cached architecture can serve the UI;
- remove the current teacher-mode semantics;
- silently change grading/business rules during the infrastructure migration.

---

## 84. Expected final repository shape

A reasonable target could look like:

```text
GoogleClassHelp/
├── backend/
│   ├── main.py
│   ├── api.py
│   ├── auth/
│   │   ├── web.py
│   │   ├── desktop.py
│   │   └── session.py
│   ├── classroom_api.py
│   ├── sync.py
│   ├── sync_service.py
│   ├── sync_store.py
│   ├── background_sync.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   └── ...
│
├── frontend/
│   ├── src/
│   ├── package.json
│   └── ...
│
├── migrations/
├── docs/
│   ├── adr/
│   └── HOSTING_MIGRATION_AUDIT.md
│
├── Dockerfile
├── compose.yml
├── Caddyfile
├── .env.example
└── README.md
```

The exact structure is flexible. Avoid needless folder churn if it makes the migration harder to review.

---

## 85. Deliverables

When the implementation is complete, provide:

1. Updated source code.
2. Database migrations.
3. Production Docker/Compose configuration.
4. Caddy/reverse-proxy configuration.
5. `.env.example`.
6. Security-focused tests.
7. User-isolation tests.
8. OAuth flow tests.
9. Updated README.
10. ADRs documenting major new decisions.
11. A migration audit and a concise list of files changed.
12. A deployment checklist.

The deployment checklist should contain concrete commands where possible.

---

## 86. Final review pass

Before declaring success, perform a final security and architecture audit.

Search the entire repository for:

```text
TOKEN_FILE
client_secret
refresh_token
access_token
user_id
localStorage
sessionStorage
127.0.0.1
localhost
allow_origins
create_all
SyncState
_profile_cache
_login_state
```

For each occurrence, determine whether it is:

- intentionally desktop-only;
- intentionally development-only;
- correctly user-scoped;
- incorrectly global;
- a production security risk.

Then test both deployment modes:

```text
Desktop/local build
Hosted web deployment
```

The hosted build must be able to run independently of the Windows desktop packaging path.

---

## 87. Final engineering principle

The core migration is not “put the existing FastAPI app on a VPS.”

The actual transformation is:

```text
single-user local application
          ↓
proper multi-user web service
```

The most important invariants are:

```text
Browser session identifies one local user.
        ↓
That user owns one Google credential set.
        ↓
That user owns one Classroom cache.
        ↓
That user's sync jobs use that user's credentials.
        ↓
Every API query is constrained to that user.
```

Teacher mode remains a **per-course role of that user**, not a global role.

Google Classroom remains the authoritative source; PostgreSQL is the server-side cache/state store; the browser receives only application-safe data; server secrets stay on the server.

Preserve the existing business logic and teacher/student functionality, but rebuild the authentication, persistence, synchronization boundaries, and deployment model so they are correct for multiple simultaneous users.

When there is a design ambiguity, inspect the existing code and ADRs first, choose the simplest secure design that satisfies the requirements, document the decision, and avoid speculative infrastructure that is not yet necessary.

---

## 88. Capacity planning and expected load for ~1,000 users

The hosted version is initially expected to support approximately **1,000 registered users**, of whom roughly **20–30 may be teachers**. Treat these figures as the initial capacity target, not as a guarantee that all 1,000 users will be simultaneously active.

The design must distinguish between:

- registered users;
- concurrently active browser sessions;
- HTTP request rate;
- Google Classroom API request rate;
- background synchronization concurrency;
- database load.

The most important scalability concern is **not the static React frontend** and usually not ordinary FastAPI request handling. The potentially expensive part is synchronization with Google Classroom, especially for teacher accounts where one synchronization may involve courses, coursework, rosters, submissions, grades, pagination, and related resources.

### Initial deployment target

A reasonable first production target is a VPS around:

```text
2 vCPU
2 GB RAM
30–40 GB SSD
multiple TB monthly transfer
```

A 2 vCPU / 2 GB VPS is considered an acceptable **initial deployment size** for ~1,000 registered users provided that synchronization, caching, database access, and concurrency are implemented correctly.

Do not assume that 1,000 registered users equals 1,000 concurrent users. The system must be designed so that a temporary increase in concurrent activity does not cause uncontrolled Google API fan-out or exhaust server memory.

The implementation must remain easy to scale vertically to approximately 4 GB RAM and/or additional CPU without requiring a major architectural rewrite.

### Critical architecture decision: cache Classroom data

Do **not** design the normal web request path so that every page load triggers a full Google Classroom synchronization.

Prefer this flow:

```text
Google Classroom
      ↓
background synchronization
      ↓
PostgreSQL cache/state
      ↓
FastAPI
      ↓
React browser
```

Instead of:

```text
Browser request
      ↓
FastAPI
      ↓
multiple Google Classroom API calls
      ↓
response
```

Whenever possible, normal UI reads must be served from PostgreSQL. Google Classroom should be contacted by the backend when data must be refreshed, synchronized, or explicitly revalidated.

### Background synchronization must be controlled

Do not run one unrestricted global synchronization loop that attempts to process every user simultaneously.

Implement a controlled synchronization mechanism with at least:

- per-user synchronization state;
- a bounded number of concurrent sync jobs;
- a queue or equivalent scheduling mechanism;
- retry handling with exponential backoff where appropriate;
- protection against duplicate simultaneous synchronization for the same user;
- pagination for every relevant Google Classroom API collection;
- sensible refresh intervals;
- cancellation/timeouts for stalled external calls;
- logging and metrics for sync duration, failures, and Google API request counts.

Teacher synchronization must be treated as potentially more expensive than ordinary student synchronization.

The worker model should conceptually support:

```text
                    Sync Scheduler
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
        User A         User B        User C
       sync job       sync job      sync job
            │             │             │
            └─────────────┼─────────────┘
                          ▼
                   Google Classroom
```

But concurrency must be bounded rather than allowing hundreds of simultaneous Google API workflows.

### Avoid synchronized traffic spikes

Do not schedule all users to synchronize at exactly the same interval boundary.

For example, avoid a design equivalent to:

```text
00:00 → sync all users
00:10 → sync all users
00:20 → sync all users
```

Prefer staggered scheduling/jitter so the workload is distributed over time:

```text
00:00 → User A
00:00 → User G
00:01 → User C
00:02 → User X
...
00:09 → User M
00:10 → only the users whose refresh is due
```

This reduces CPU, database, network, and Google API bursts.

### Estimate Google API load before release

The engineering process must quantify the approximate number of Google Classroom API requests generated by one synchronization for:

1. an ordinary student account;
2. a student account with several courses and coursework items;
3. a teacher account;
4. a teacher account with multiple courses, many students, many assignments, and paginated submissions.

Use this to estimate total traffic for roughly 1,000 users and 20–30 teachers.

For example, if an average synchronization requires `N` Google API requests and a user is synchronized every `T` minutes, the rough average request rate is:

```text
average requests/minute ≈ (users × N) / T
```

This is only an approximation because pagination and course sizes vary significantly. The implementation must instrument the actual request count rather than relying only on theoretical estimates.

### Teacher-mode load

Teacher accounts can create disproportionately more load because a teacher course may require retrieval of:

```text
courses
coursework
students / roster
submissions
grades / returned state
attachments or related metadata where permitted
```

A teacher with many students and assignments may require many paginated requests.

Do not assume that “only 20–30 teachers” means teacher load is negligible. The system must explicitly measure teacher synchronization cost and limit simultaneous expensive teacher jobs.

### Database requirements for 1,000 users

PostgreSQL should be used instead of SQLite for the hosted multi-user deployment.

The database design must support:

- indexes on user ownership and Google resource IDs;
- efficient lookup of a user's courses/coursework/submissions;
- unique constraints preventing duplicate cached resources;
- transaction-safe synchronization updates;
- safe concurrent reads and writes;
- cleanup/retention rules for obsolete cached data where necessary.

Queries used by the main UI must be analyzed for N+1 behavior and missing indexes.

### Session and API request expectations

The frontend must not poll the backend excessively merely to determine whether data changed.

Prefer:

- cached responses;
- explicit refresh actions where useful;
- sensible polling intervals only when required;
- server-side timestamps / sync state so the frontend can determine freshness;
- conditional or incremental synchronization rather than full re-imports whenever the Google Classroom API permits it.

Do not introduce WebSockets, Redis, Celery, Kubernetes, or other infrastructure solely because the application has 1,000 registered users. Introduce additional components only when measured load or required reliability justifies them.

### Initial capacity acceptance criteria

Before public release, load-test the hosted application with a realistic approximation of:

```text
~1,000 user records
~20–30 teacher accounts
multiple courses per user
multiple assignments per course
multiple students per teacher course
realistic concurrent browser activity
background synchronization enabled
```

Measure at minimum:

- RAM usage;
- CPU usage;
- PostgreSQL memory/CPU usage;
- HTTP latency;
- HTTP error rate;
- Google API request rate;
- sync queue depth;
- average and worst-case synchronization duration;
- failed and retried sync jobs;
- database query latency.

The application should remain responsive during a realistic synchronization wave and must not allow a single user or teacher account to monopolize the worker pool.

### Monitoring and scale-up trigger

Add enough observability to determine when the initial VPS is becoming insufficient.

Potential scale-up signals include sustained high memory usage, sustained CPU saturation, growing synchronization queues, increasing request latency, excessive PostgreSQL contention, or repeated timeouts/retries.

The first scaling step should preferably be vertical scaling, for example:

```text
2 vCPU / 2 GB
      ↓
4 vCPU / 4 GB
```

before introducing a more complex multi-server architecture.

### Important conclusion for the implementation

The project should be engineered around the assumption that **1,000 registered users is manageable on a modest VPS, but uncontrolled Google Classroom synchronization is not**.

Therefore the primary scalability objective is:

```text
bounded background concurrency
+ PostgreSQL caching
+ efficient user-scoped queries
+ staggered synchronization
+ Google API request measurement
+ graceful scaling path
```

Do not optimize prematurely for thousands of simultaneous HTTP requests if the actual bottleneck is Google Classroom synchronization. Measure the real workload and optimize the external API access pattern first.
