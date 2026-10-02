# GoogleClassHelp — Super Admin, Administrators in PostgreSQL, Separate `/admin` Console

**This file is the authoritative implementation prompt.** Every decision below is
already made; do not re-open it, do not propose alternatives, do not redesign what
exists. Implement exactly this.

- **Status:** Ready to implement.
- **Extends:** the already-shipped feedback/ticket feature (ADR-0035).
  See `docs/adr/adr-0035-feedback-tickets-and-administrators.md`.
- **Production domain:** `https://classroomhelp.pp.ua`
- **Repo conventions:** ADR + README + `.env.example` + Alembic revision + pytest +
  vitest + ruff + pyright. Match the surrounding code style (module docstrings that
  explain *why*, `# ruff: noqa: B008` where FastAPI `Depends()` is used, typed
  Pydantic models, no magic numbers).

---

## 1. Fixed decisions (NON-NEGOTIABLE)

These were decided before implementation. Treat them as requirements, not options.

- **D1 — The admin console is a separate shell.** The admin area is NOT reachable
  from the user-facing site navigation. The user's `Sidebar` loses its
  "Administration" entry entirely; the only way in is the URL `/admin`. A dedicated
  `AdminShell` + `AdminSidebar` renders under `/admin/*`. The public site and its
  navigation stay exactly as they are.

- **D2 — One navigation abstraction, two item lists.** Extract a presentational
  `components/SidebarNav.tsx` (brand block, `<nav>`, `NavLink` with `isActive` +
  `cn`, compact-card-density prop, overdue-alert slot). `Sidebar` and `AdminSidebar`
  both render it with different `items` arrays. One nav component, no duplicated
  markup, no duplicated CSS.

- **D3 — The backend is the only authority.** Roles are derived exclusively from the
  Google e-mail of the validated session (`ownership.get_current_user`). No
  client-supplied e-mail, header, query parameter, form field, cookie or
  localStorage flag is ever trusted for authorization.

- **D4 — `SUPER_ADMIN_EMAIL` is server-side only.** Read from the process
  environment, unprefixed (like `COOKIE_SECURE` / `APP_BASE_URL` /
  `TURNSTILE_SITE_KEY`). Never a `VITE_*` variable, never a `/api/config` field, never
  in the OpenAPI document. The frontend learns two **booleans** and nothing else:
  `UserOut.is_admin` and `UserOut.is_super_admin`.

- **D5 — `ADMIN_EMAILS` is deleted outright.** No compatibility shim, no fallback,
  no dual mechanism, no "deprecated but still read" branch. Exactly one
  authoritative source for normal administrators: the `admins` table. Update
  `.env.example`, `.env.local.example`, `README.md`, and every test helper that
  monkeypatched it.

- **D6 — Fail closed.** Unset / blank / whitespace-only / `@`-less
  `SUPER_ADMIN_EMAIL` means **nobody** is a Super Admin. A missing `admins` row means
  normal user. Failures never widen access.

- **D7 — E-mail validation without a new dependency.** Write a hand-rolled
  `field_validator` in `backend/schemas_admins.py` (trim, lowercase, pragmatic
  regex, length cap), in the spirit of the existing validators in
  `backend/schemas_feedback.py`. Do **NOT** add `pydantic[email]` /
  `email-validator`: `backend/requirements.txt`, `backend/requirements-prod.txt`
  and the Docker image must stay untouched.

- **D8 — Display name is derived server-side and is deterministic.** `AdminOut.name`
  is computed by the backend from the stored e-mail
  (`john.doe@gmail.com` to `John Doe`, `john_doe@gmail.com` to `John Doe`,
  `john-doe@gmail.com` to `John Doe`, `john@gmail.com` to `John`). The database
  stores only the e-mail. There is no editable name field, and no Google lookup is
  made.

- **D9 — The `admins` table has NO foreign key to `users`.** An administrator may be
  appointed before they ever sign in, and deleting an account
  (`maintenance.delete_user_data`) must not silently revoke a role. Orphan rows are
  the intended behaviour, not a leak to clean up.

- **D10 — Unauthorized `/admin` access redirects; it never renders a dead end.**
  `RequireAdmin` currently renders a "not available" `EmptyState`; replace that with
  `<Navigate to="/" replace />`. Add `RequireSuperAdmin`, which redirects a plain
  administrator from `/admin/admins` to `/admin`. While the session answer is still
  unknown (`auth === null`), redirect too — privileged-looking UI must never flash
  at whoever is loading the page.

- **D11 — Status codes are part of the contract.** Unauthenticated gives 401 (already
  answered by the hosted session gate). Authenticated but not an administrator gives
  403. Plain administrator on the admins API gives **403**. Duplicate e-mail gives
  **409**. Invalid / blank e-mail gives **422**. An attempt to add or delete the Super
  Admin gives **409**. A missing row on `DELETE` gives **404**. Never rely on
  frontend hiding.

- **D12 — Ticket functionality is not redesigned.** Only these ticket-side pieces
  change: the `require_admin` dependency signature, the `is_admin` call in
  `feedback_api.download_attachment`, and the `UserOut` identity builder. No second
  ticket system, no second statistics implementation, no second auth system, no
  second user table, no duplicate sidebar.


---

## 2. Existing implementation you are extending (verified)

Do not recreate any of this. Read these files first.

| Concern | File | Notes |
| --- | --- | --- |
| Current admin allow-list | `backend/config.py` (administrators block, lines ~69-91) | `ADMIN_EMAILS: frozenset[str]` + `is_admin_email(email)` — **to be deleted** |
| Authorization dependency | `backend/admin_auth.py` (46 lines) | `require_admin(user = Depends(ownership.get_current_user))` — extend here |
| Ticket router (admin side) | `backend/feedback_admin_api.py` | `APIRouter(prefix="/api/admin/feedback", tags=["admin"])`, every handler takes `Depends(require_admin)` |
| Ticket router (user side) | `backend/feedback_api.py` | line ~349 uses `is_admin_email(user.email)` for the attachment read-through |
| Domain model module (precedent) | `backend/models_feedback.py` | one module per domain; register in `database._import_models()` |
| Pydantic module (precedent) | `backend/schemas_feedback.py` | `*Out` vs `Admin*` split; `field_validator` for trimming |
| Identity shape | `backend/schemas.py::UserOut` | today `id, name, email, is_admin` |
| Identity builder | `backend/api.py::_user_out` / `_build_auth_status` | consumed by `GET /api/auth/status`, `GET /api/me`, `POST /api/auth/login`, `POST /api/auth/logout` |
| Router registration | `backend/main.py::create_app` | next to `app.include_router(feedback_admin_router)` |
| Migration precedent | `migrations/versions/0004_feedback_tickets.py` | docstring explains every index; `downgrade()` in reverse dependency order |
| Migration env | `migrations/env.py` | imports the model modules; add the new one or autogenerate misses the table |
| Frontend routes | `frontend/src/App.tsx` | one `AppShell`, `.app-layout` + `<Sidebar/>` |
| Frontend sidebar | `frontend/src/components/Sidebar.tsx` | `ITEMS` array, `admin?: boolean` filter via `isAdminUser(auth)` |
| Route guard | `frontend/src/components/RequireAdmin.tsx` | renders `EmptyState` today, becomes a redirect |
| Destructive dialog | `frontend/src/components/ConfirmDialog.tsx` | real React dialog, `.button-danger`, no `window.confirm` |
| Modal / form pattern | `frontend/src/components/AssignmentModal.tsx` | `modal-backdrop` + `modal` + `modal-actions` |
| Table styling | `frontend/src/styles/pages.css` | `.table-wrap` + `.data-table` (used by `TeacherCourse`, `AssignmentDetail`, `TeacherGrades`) |
| HTTP client | `frontend/src/api.ts` | `request<T>()` / `requestForm<T>()`, `ApiError { status, message }`, one shared 401 handler |
| Types | `frontend/src/types.ts` | wire types generated from `api-schema.d.ts`; `isAdminUser(auth)` lives here |
| i18n | `frontend/src/i18n/{en,uk,ru}.ts` | `en.ts` defines `I18nKey`; the other two use `satisfies Record<I18nKey, string>`, so a missing translation fails `tsc` |
| OpenAPI regeneration | `tools/dump_openapi.py` then `frontend/openapi.json` then `npm run gen:api:file` | required after changing any Pydantic model |
| Test helpers | `tests/feedback_helpers.py` | `as_admin(monkeypatch, ...)` patches the already-parsed set |
| Test env hygiene | `tests/conftest.py` | pops `ADMIN_EMAILS` and the feature knobs before importing `config` |
| Lint config | `ruff.toml` | `known-first-party` lists every backend module — add the new ones |
| Type-check config | `pyrightconfig.json` | `include: ["backend", "tests", "tools", "migrations"]`, mode `standard` |

---

## 3. Role model

```
authenticated Google e-mail (users.email via ownership.get_current_user)
        |
        +-- equals SUPER_ADMIN_EMAIL?  -> SUPER ADMIN
        |     (normalize: strip then lowercase; unset/blank/@-less means never)
        |
        +-- row exists in `admins`?    -> ADMIN
        |
        +-- otherwise                   -> NORMAL USER
```

| Capability | Normal user | Admin | Super Admin |
| --- | --- | --- | --- |
| Public site, dashboard, own tickets | yes | yes | yes |
| `GET /api/admin/feedback/*`, `PATCH`, `POST .../messages`, `DELETE` | 403 | yes | yes |
| `GET /api/admin/feedback/stats` | 403 | yes | yes |
| `/admin`, `/admin/feedback*` in the UI | redirect `/` | yes | yes |
| `GET /api/admin/admins` | 403 | 403 | yes |
| `POST /api/admin/admins` | 403 | 403 | yes |
| `DELETE /api/admin/admins/{id}` | 403 | 403 | yes |
| `/admin/admins` in the UI | redirect `/` | redirect `/admin` | yes |

The Super Admin is **not** stored in the `admins` table and **cannot be deleted
through this UI or API**: their configuration lives exclusively in
`SUPER_ADMIN_EMAIL`, and changing it takes effect after a `web` restart with no code
change (SCENARIO 12).

The only functional difference between Admin and Super Admin at this stage is
administrator management. Ticket functionality, ticket statistics and every other
admin capability are shared.


---

## 4. Phase A — Database model and migration

### 4.1 `backend/models_admin.py` (NEW)

Follow the `models_feedback.py` precedent: a separate module per domain, with a
module docstring explaining the invariants.

```python
class Admin(Base):
    """One normal administrator, identified by e-mail."""

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The authoritative identifier, stored normalized (strip + lowercase).
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # Naive UTC, like every other timestamp in this schema.
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

The docstring must state, in prose: the e-mail is the identity and is stored
normalized; there is no name column because the display name is derived (D8); there
is no FK to `users` and why (D9); the Super Admin is deliberately absent from this
table.

### 4.2 `migrations/versions/0005_admins_table.py` (NEW)

`revision = "0005"`, `down_revision = "0004"`. Hand-written, never silently
autogenerated. The docstring must justify the unique index on `email` (a normalized
e-mail is the identity, so exactly one row per person) and the absence of any FK.

- `upgrade()` — `op.create_table("admins", ...)`.
- `downgrade()` — `op.drop_table("admins")`.

It must work on a **clean** database and on the **existing production** database. Do
not touch any existing ticket table.

### 4.3 Registration (easy to forget, all three are required)

- `backend/database.py::_import_models()` — import `Admin` from `models_admin`, so
  SQLite `create_all` and `Base.metadata` see it.
- `migrations/env.py` — import the module next to `import models` /
  `import models_auth`, otherwise autogenerate will not see the table.
- `ruff.toml`, `[lint.isort] known-first-party` — add `models_admin`,
  `schemas_admins`, `admins_api`.

---

## 5. Phase B — Backend authorization

### 5.1 `backend/config.py`

- **Delete** the `ADMIN_EMAILS` block and `is_admin_email()`.
- **Add**, unprefixed, in the same place:

```python
SUPER_ADMIN_EMAIL: str | None = ...   # os.environ["SUPER_ADMIN_EMAIL"], stripped+lowered

def normalize_email(value: str | None) -> str:
    """Trim and lowercase; '' for None/blank. The one normalization of the feature."""
```

Rules: unset, empty, whitespace-only, or a value without `@` means
`SUPER_ADMIN_EMAIL is None`, which means **nobody** is a Super Admin (D6). Never log
the value, never expose it.

Keep the fail-closed framing of the existing docstrings, and state explicitly that
this value never reaches React, `/api/config`, the OpenAPI document or a log line.

### 5.2 `backend/admin_auth.py` (extend — this stays the ONLY authorization seam)

Keep the file deliberately thin and keep its explanatory docstring style.

```python
ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLE_SUPER_ADMIN = "super_admin"

def is_super_admin_email(email: str | None) -> bool          # vs config.SUPER_ADMIN_EMAIL
def display_name_from_email(email: str) -> str               # D8, deterministic
def resolve_role(db: Session, email: str | None) -> str      # the single resolver
def is_admin_email(db: Session, email: str | None) -> bool   # DB-backed replacement

def require_admin(user = Depends(ownership.get_current_user),
                  db = Depends(get_db)) -> User             # 403 unless role != user
def require_super_admin(user = Depends(ownership.get_current_user),
                        db = Depends(get_db)) -> User       # 403 unless super admin
```

Rules:

- `resolve_role` checks **Super Admin first**, then a single indexed SELECT on
  `admins.email`, then falls through to `ROLE_USER`.
- An empty address (the desktop local owner has `email is None`) is never an
  administrator and never a Super Admin; do not even query for it.
- `require_super_admin` composes on top of `require_admin` so the 401 path stays in
  exactly one place (`ownership.get_current_user` and the hosted session gate).
- 401 stays absent from these dependencies: an unauthenticated request never reaches
  them.
- FastAPI caches dependencies per request, so the `db` resolved here is the same
  `get_db` session the handler receives. State this in the docstring and prove it
  with a test.


### 5.3 `backend/schemas.py::UserOut`

Add `is_super_admin: bool = False`. Nothing else changes: no role string, no Super
Admin e-mail, no administrator list.

### 5.4 `backend/api.py`

- `_user_out(user, db)` and `_build_auth_status(user, db)` compute `is_admin` and
  `is_super_admin` through `resolve_role`, so the flags can never disagree with the
  dependency.
- Thread `db: Session = Depends(get_db)` through `GET /api/auth/status`,
  `GET /api/me`, `POST /api/auth/login`, `POST /api/auth/logout`.
- Desktop branch: the local owner has no address, so both flags are `False` by
  construction.

### 5.5 `backend/feedback_api.py`

Replace the `is_admin_email(user.email)` call inside `download_attachment` with the
DB-backed role check, so an Admin **and** a Super Admin may read any attachment.

### 5.6 `backend/schemas_admins.py` (NEW)

- `AdminOut`: `id: int`, `email: str`, `name: str`, `created_at: datetime`.
- `AdminCreateIn`: `email: str` with a `field_validator` implementing D7: trim,
  lowercase, non-empty, length cap (255), exactly one `@`, a dot in the domain, no
  whitespace. Raise `ValueError` so FastAPI answers 422.

Pydantic's default `extra="ignore"` stays: an unknown or forged field (`name`,
`is_super_admin`, `id`) is ignored, never honoured.

### 5.7 `backend/admins_api.py` (NEW)

```python
router = APIRouter(prefix="/api/admin/admins", tags=["admin"])
```

| Method | Path | Guard | Answers |
| --- | --- | --- | --- |
| `GET` | `/` | `require_super_admin` | 200 `list[AdminOut]`, newest first |
| `POST` | `/` | `require_super_admin` | 201 `AdminOut` |
| `DELETE` | `/{admin_id}` | `require_super_admin` | 204 |

Handler bodies:

- **POST** — normalize, then 409 if it equals `SUPER_ADMIN_EMAIL`, then 409 on a
  duplicate (query first, and stay correct under a race by also catching the unique
  violation), then insert with a naive-UTC `created_at`, then log at INFO with the row
  id (never the value of `SUPER_ADMIN_EMAIL`).
- **DELETE** — 404 when the row does not exist; 409 when the row's e-mail equals the
  Super Admin e-mail (possible only if `SUPER_ADMIN_EMAIL` changed after the row was
  inserted); otherwise delete, commit, log at INFO.
- Errors use the project's short `detail` strings; never echo a stack trace or a
  Pydantic error object.
- No endpoint accepts an e-mail from the request as an identity claim.

### 5.8 `backend/main.py`

`app.include_router(admins_router)` next to `feedback_admin_router`, inside the
hosted middleware stack so the session gate, the Host/Origin guard, the CSRF
fetch-metadata check and `Cache-Control: no-store` already apply.


---

## 6. Phase C — Frontend

### 6.1 `frontend/src/components/SidebarNav.tsx` (NEW — the D2 abstraction)

A **presentational** component. It renders the brand block, the `<nav>` of `NavLink`s
and the overdue-alert slot; it fetches nothing and knows nothing about roles.

```ts
export type NavItem = {
    to: string;
    labelKey: I18nKey;
    icon: LucideIcon;
    counter?: "todo";
    end?: boolean;
};
export function SidebarNav({ items, alert }: { ... })
```

`Sidebar.tsx` becomes a thin wrapper that assembles the **user** item list (no
"Administration" entry, per D1) and renders `<SidebarNav>`. `AdminSidebar.tsx` (NEW)
assembles the **admin** item list:

- `Tickets` to `/admin/feedback` (both roles);
- `Admins` to `/admin/admins`, **only** when `isSuperAdminUser(auth)`.

Move the `NavLink ... isActive ... cn("sidebar-link", isActive && "active")` markup
verbatim out of `Sidebar.tsx` so styling and the active state cannot drift. Keep the
`cardDensity === "compact"` class on the aside.

### 6.2 `frontend/src/App.tsx`

- Keep `App`, `SettingsProvider`, `DataProvider`, the toasters, and the
  `bootUnknown` / `showLanding` / `signedOut` gates exactly as they are.
- Branch on the current location: paths starting with `/admin` render
  `<AdminShell>`; everything else renders the existing `.app-layout` with
  `<Sidebar/>`.
- `AdminShell` (NEW) mirrors the existing layout markup (`div.app-layout`, then
  `<AdminSidebar/>`, then `div.app-main` with `<TopBar/>` and `main.app-content`) so
  the visual design is identical and only the navigation differs.
- Admin routes, each wrapped in its guard:
  - `/admin` to `AdminDashboard`
  - `/admin/feedback` to `AdminFeedback`
  - `/admin/feedback/:id` to `AdminFeedbackTicket`
  - `/admin/admins` to `AdminAdmins`
  - `/admin/*` to `<Navigate to="/admin" replace />`

Keep `DashboardBoundary` around the route tree as today.

### 6.3 Guards

- `RequireAdmin.tsx` becomes `<Navigate to="/" replace />` when the session is not an
  administrator (D10). It still reads only the server-derived boolean, never a
  localStorage flag.
- `RequireSuperAdmin.tsx` (NEW) renders children when `isSuperAdminUser(auth)`,
  otherwise `<Navigate to="/admin" replace />`; it also redirects while
  `auth === null`.

### 6.4 `frontend/src/pages/AdminAdmins.tsx` (NEW)

Layout, top to bottom:

1. `page-header` with the `<h1>` and the **Add administrator** button
   (`button button-primary`) inside `page-header-actions`;
2. the table.

Table (`.table-wrap` > `.data-table`): **Email | Name | Date added | Delete**.

- The **Delete** button (`button button-danger`) sits in the same `<tr>` as the
  administrator it removes; there is no global delete control anywhere.
- The date column uses the existing `toLocalDate` and `formatDateTimeShort` helpers
  from `frontend/src/dates.ts`.
- Empty list gives `EmptyState`; loading gives `SectionSkeleton`; failure gives
  `alert alert-error`; success gives a toast through the existing `Toaster`.

**Add form** — a modal on the `AssignmentModal` pattern (`modal-backdrop`, `modal`,
`modal-header`, `modal-actions`):

- exactly one field, `Email`, required, `type="email"`;
- **no** name field, no display-name field;
- server-side 422 and 409 messages are shown inside the modal, never swallowed;
- the button is disabled while the request is in flight.

**Delete confirmation** — reuse `ConfirmDialog.tsx` verbatim: title
`Remove administrator?`; a body that names the address being removed and states that
the user will lose administrator access to GoogleClassHelp; `[Cancel]` then
`[Remove administrator]` as a `.button-danger` that is the last focusable element.
`ConfirmDialog` already supports `busy` and `error`; use them.

### 6.5 Client plumbing

- `frontend/src/types.ts` — add `isSuperAdminUser(auth)` next to `isAdminUser`; both
  keep reading the server flags.
- `frontend/src/api.ts` — `getAdmins()`, `createAdmin(email)` and `deleteAdmin(id)` in
  the existing admin-surface block, reusing `request<T>()`, the shared `ApiError` and
  the shared 401 handling.
- `frontend/src/i18n/en.ts` — new `admin.admins*` keys plus `nav.admins` (`en.ts` is
  the source of truth for `I18nKey`); add the same keys to `i18n/uk.ts` and
  `i18n/ru.ts` or `tsc` fails.
- `frontend/src/styles/pages.css` — at most a small `.admin-admins-*` block built
  from the existing tokens; reuse `.table-wrap`, `.data-table`, `.modal*` and
  `.button-danger`.
- Regenerate the wire types once the backend models are final:
  `python tools/dump_openapi.py > frontend/openapi.json`, then
  `npx prettier --write openapi.json`, then `npm run gen:api:file`.


---

## 7. Phase D — Tests

### 7.1 Test infrastructure changes (do these before adding new tests)

- `tests/conftest.py` — replace `"ADMIN_EMAILS"` with `"SUPER_ADMIN_EMAIL"` in the
  popped feature knobs, so a stray value from the developer's shell cannot change who
  is a Super Admin.
- `tests/feedback_helpers.py` — **replace** `as_admin(monkeypatch, ...)` with:
  - `grant_admin(db, *emails)` — inserts normalized rows into `admins` and
    **`db.commit()`** (the same lesson as the `owner_id` fixture: the API opens its
    own connection, so an uncommitted write would deadlock or block it);
  - `as_super_admin(monkeypatch, email)` — patches the already-parsed
    `config.SUPER_ADMIN_EMAIL` (config is read at import time, so patching the parsed
    value is correct; do not `importlib.reload` it).
- Update every call site: `tests/test_feedback_admin_auth.py` (~28),
  `tests/test_feedback_tickets.py` (2), `tests/test_feedback_attachments.py` (4).
- Delete the `ADMIN_EMAILS` parsing tests (lines ~44-115 of
  `test_feedback_admin_auth.py`) and replace them with the `SUPER_ADMIN_EMAIL`
  equivalents from §7.2.
- `tests/test_teacher_mode.py` (~305-332) compares the **whole** `UserOut` dict: add
  `"is_super_admin": False`.
- `tests/test_user_isolation.py:439` calls `api._build_auth_status(alice)` directly:
  pass the session.
- Any other exact-dict or fixture comparison of `UserOut` / `AuthStatus`
  (`Settings.test.tsx`, `DataContext.test.tsx`, `SyncToaster.test.tsx`,
  `RequireAdmin.test.tsx`, `App.test.tsx`) needs the new field, or `tsc` fails.

### 7.2 New backend tests

`tests/test_admin_roles.py` — role resolution and configuration:

1. Super Admin is recognized from `SUPER_ADMIN_EMAIL`.
2. A row in `admins` is recognized as an Admin.
3. A normal user is neither Admin nor Super Admin.
4. Comparison is case-insensitive (`Boss@Example.com` equals `boss@example.com`).
5. Leading and trailing whitespace is stripped on both sides.
6. Empty, blank, whitespace-only or `@`-less `SUPER_ADMIN_EMAIL` means nobody is a
   Super Admin.
7. The desktop local owner (`email is None`) is never an administrator.
8. `ADMIN_EMAILS` no longer grants administrator access (D5).
9. `display_name_from_email` maps the four documented examples.
10. `require_admin` and `require_super_admin` receive the same `Session` instance the
    handler gets (the FastAPI dependency-cache claim).
11. `SUPER_ADMIN_EMAIL` never appears in the `/api/auth/status`, `/api/me` or
    `/api/admin/admins` responses.

`tests/test_admins_management_api.py` — the management surface:

12. Normal user: 401 anonymous and 403 authenticated on all three routes, with no
    administrator data leaking into the body.
13. Plain Admin: 403 on `GET`, `POST` and `DELETE` (this is the requirement that must
    not regress), while `GET /api/admin/feedback/tickets` and
    `GET /api/admin/feedback/stats` answer 200.
14. Super Admin can list, add and delete administrators.
15. Duplicate add gives 409 and creates no second row.
16. Adding the Super Admin e-mail gives 409 and creates no row.
17. Invalid, blank or whitespace-only e-mail gives 422.
18. Adding the same address with different case and surrounding spaces gives 409
    (normalization happens before the duplicate check).
19. A deleted administrator loses access after the next authorization check: their
    next request to a ticket admin endpoint is 403.
20. The Super Admin cannot be removed through `DELETE /api/admin/admins/{id}`
    (404 when absent, 409 when the row holds the Super Admin e-mail).
21. Inserting or deleting a row directly in the database changes authorization.
22. No request field (`email`, `is_admin`, `is_super_admin`, headers, query params)
    can grant or escalate a role.

### 7.3 New frontend tests (vitest)

- `RequireAdmin` redirects a non-administrator instead of rendering an "unavailable"
  screen, and redirects while `auth === null`.
- `RequireSuperAdmin` renders children for a Super Admin and redirects a plain Admin
  to `/admin`.
- `Sidebar` (user site) shows **no** admin entries, including for a Super Admin (D1);
  `AdminSidebar` shows `Tickets` for an Admin and `Tickets` + `Admins` for a Super
  Admin, with the active item marked.
- `AdminAdmins` renders the generated name and the date, opens the add modal with
  only an e-mail field, shows the server message for a duplicate, shows the
  `ConfirmDialog` before deleting, and refreshes the table afterwards.


---

## 8. Phase E — Environment, documentation, deployment

- `.env.example` — replace the `ADMIN_EMAILS` block with `SUPER_ADMIN_EMAIL`, with a
  comment stating: Super Admin only, unset means nobody, read from the process
  environment, never a `VITE_` variable, restart `web` after changing it.
- `.env.local.example` — replace the `ADMIN_EMAILS` hint; local admins are now rows in
  the database, the Super Admin is still the variable.
- `compose.yml` and `compose.local.yml` — **no change required**: both already pass
  `.env` / `.env.local` wholesale via `env_file`. Verify that only.
- `README.md` — replace the `ADMIN_EMAILS` row in the environment table; extend the
  administration section: the console is at `/admin` and reachable **only** by URL,
  who may manage whom, and that `/api/admin/admins` is Super-Admin-only.
- `docs/adr/adr-0036-super-admin-and-admin-registry.md` (NEW) — context, decision,
  consequences, in the project's ADR format; then add the row to `docs/adr/README.md`.
  The superseded part of ADR-0035 (`ADMIN_EMAILS` as the source of normal-admin
  authorization) stays in ADR-0035 and is marked superseded there.
- `docs/DEPLOYMENT_CHECKLIST.md` — add the rollout step: after `alembic upgrade head`,
  set `SUPER_ADMIN_EMAIL` in `.env`, restart `web`, sign in as the Super Admin and
  re-create the former `ADMIN_EMAILS` administrators through `/admin/admins` (D5 makes
  this a deliberate one-time step).
- `docs/TESTING_NOTES.md` — the new test files, the new "last green" record, and the
  new gotcha: `grant_admin` must commit, because uncommitted rows produce
  `database is locked`.
- ADR-0035 references in docstrings (`RequireAdmin.tsx`, `admin_auth.py`,
  `config.py`) that name `ADMIN_EMAILS` must be corrected.

---

## 9. Order of work

Do the phases in this order and run `pytest` after each one.

1. `config.py` (`SUPER_ADMIN_EMAIL`, `normalize_email`, delete `ADMIN_EMAILS`), then
   `models_admin.py`, then `0005_admins_table.py`, then `database.py`,
   `migrations/env.py` and `ruff.toml`.
2. `admin_auth.py`: `resolve_role`, `is_admin_email(db, ...)`, `require_admin(db)`,
   `require_super_admin`, `display_name_from_email`.
3. `schemas.py` (`UserOut`), `api.py`, `feedback_api.py` — move every `is_admin`
   computation onto `resolve_role`.
4. `schemas_admins.py`, `admins_api.py`, `main.py`.
5. Test infrastructure: `conftest.py`, `feedback_helpers.py`, and **all** call sites of
   `as_admin`; the existing suite must be green again before anything new is added.
6. `test_admin_roles.py` and `test_admins_management_api.py`.
7. Frontend: `SidebarNav`, then `Sidebar`, then `AdminSidebar`, then
   `App.tsx` / `AdminShell`, then the guards, then `AdminAdmins`, then
   `api.ts` / `types.ts` / i18n / CSS, then regenerate `openapi.json` and
   `api-schema.d.ts`.
8. Frontend tests.
9. Documentation (§8) and the final report.

Do not leave a phase half-done: each phase ends with the suite green.

---

## 10. Verification

```powershell
# backend
python -m pytest
ruff check backend
npx pyright

# frontend
cd frontend
npm run lint
npx vitest run
npm run build

# repo hygiene
python tools/check_text_encoding.py
```

Plus, against the running app, the curl checks that matter most (D11):

```powershell
# as a PLAIN ADMIN - must be 403, proving the API cannot be bypassed
curl -i -X POST https://classroomhelp.pp.ua/api/admin/admins `
  -H "Content-Type: application/json" -b "gch_session=<admin session>" `
  -H "Sec-Fetch-Site: same-origin" -d '{"email":"attacker@example.com"}'

# the same request as the SUPER ADMIN - must be 201
```

Also run `alembic upgrade head` on a scratch PostgreSQL twice (once on a clean
database, once on an existing schema) and confirm the downgrade/upgrade round-trips.


---

## 11. Manual verification scenarios

Run all twelve against `https://classroomhelp.pp.ua` (or the local stack from
`compose.local.yml`) and record the result of each.

| # | Action | Expected |
| --- | --- | --- |
| 1 | A normal Google user opens `/admin` | redirected to `/` |
| 2 | An existing Admin opens `/admin` | console loads; sidebar shows **Tickets** only |
| 3 | The Super Admin opens `/admin` | console loads; sidebar shows **Tickets** and **Admins** |
| 4 | A normal Admin manually opens `/admin/admins` | redirected to `/admin`; `GET /api/admin/admins` is 403; no administrator data in the response |
| 5 | The Super Admin opens `/admin/admins` | table with e-mail, generated name, date added, per-row delete |
| 6 | The Super Admin clicks *Add administrator* | modal with an **e-mail** field only, no name field |
| 7 | The Super Admin adds `test.admin@example.com` | new row appears, name auto-generated, row present in PostgreSQL |
| 8 | The Super Admin adds the same e-mail again | rejected with a clear message; still one row |
| 9 | The Super Admin adds the Super Admin e-mail | rejected; no row created |
| 10 | The Super Admin removes a normal administrator | confirmation dialog first; then the row is deleted, and that user's next admin API call is 403 while `/admin` redirects them to `/` |
| 11 | Any attempt to delete the Super Admin | impossible through the UI (no such row) and refused by the API (404 or 409) |
| 12 | Change `SUPER_ADMIN_EMAIL` and restart `web` | the new address is the Super Admin and the old one is demoted, with no code change |

---

## 12. Final report

Finish with a concise report containing:

- files and components added, changed, removed;
- the database model added and the migration added;
- the authentication and role-resolution changes;
- the new environment variable and the removed one;
- the new backend endpoints with their guards and status codes;
- frontend routes, the sidebar change, the new abstraction;
- the administrator-management implementation: name generation, duplicate handling,
  Super Admin protection, confirmation dialog;
- tests added and tests executed, with counts;
- the manual verification table from §11, filled in;
- compatibility considerations, especially that former `ADMIN_EMAILS` administrators
  must be re-created through the UI — a deliberate, one-time consequence of D5.

### Explicit confirmations to state in the report

- Super Admin is configured **only** through `SUPER_ADMIN_EMAIL`, server-side only.
- Normal Admins are stored **only** in PostgreSQL, never in `.env`.
- `ADMIN_EMAILS` no longer grants anything, anywhere.
- Admins cannot manage other Admins; only the Super Admin can add or remove them.
- The Super Admin cannot be deleted through the UI or the API.
- `/admin` checks the current authenticated Google e-mail on every entry; no
  client-supplied identity is trusted and no admin flag is stored in the browser.
- Unauthorized users are redirected to `/`, and a plain Admin on `/admin/admins` is
  redirected to `/admin`.
- Admin and Super Admin have different sidebar permissions (D1, D2).
- Backend authorization prevents API bypasses: `POST /api/admin/admins` and
  `DELETE /api/admin/admins/{id}` are Super-Admin-only, while the ticket admin
  endpoints work for both roles.

---

## 13. Non-goals (do not do)

- No second Google authentication system, no second user table, no password login.
- No second ticket system, no duplicate statistics, no redesign of the ticket screens.
- No duplicated sidebar code (D2) and no second `is_admin` computation path.
- No `email-validator` or `pydantic[email]` dependency (D7).
- No role column on `users`, no "first user is admin", no wildcard.
- No `SUPER_ADMIN_EMAIL` in React, in `/api/config`, in the OpenAPI document or in a
  log line.
