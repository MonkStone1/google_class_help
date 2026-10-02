# Google Class Help — ticket-based feedback system (implementation prompt)

Implement a complete, ticket-based support/feedback system in the existing
Google Class Help repository: user-facing tickets with a Markdown editor and
attachments, plus an administrator panel with a dashboard, filtering, replies
with a custom public display name, status changes and permanent deletion.

This prompt describes **this** repository. Every path, module, helper and
command below was read from the current tree; do not invent alternatives and do
not assume a structure that is not listed here.

---

## 0. How to use this prompt

Work in this order:

1. Read the files listed in §1 (all of them) before writing any code.
2. Implement §4–§10 (data, API, security, frontend).
3. Add the tests of §13 and run them.
4. Run the manual verification of §14 and record the real answers.
5. Update the documentation of §15.
6. Run the full verification sequence of §16.
7. Deliver the report of §17.

If something in this prompt contradicts the code you read, **the code wins** —
but say so explicitly in the final report and explain why the prompt was wrong.

---

## 1. Read this repository first (mandatory)

### 1.1 Backend runtime and edge

- `backend/main.py`
  - `create_app(hosted: bool)` builds one app per deployment mode; the
    module-level `app = create_app(hosted=HOSTED_MODE)`.
  - Middleware order is documented in the `create_app` docstring (last added =
    outermost): session gate → Host/Origin guard → CORS, plus the abuse
    throttle and the security-headers middleware of the hosted branch.
  - `require_session` closes **every** `/api/*` path except `/api/auth/*`,
    `/api/health`, `/api/ready` and `OPTIONS`, and answers **401** — so an
    anonymous ticket request is rejected before route dispatch.
  - `enforce_allowed_host` implements the Host/Origin guard and the CSRF
    check (§38): an unsafe method without an `Origin` is judged by
    `Sec-Fetch-Site`. New state-changing endpoints inherit this for free —
    do not add a second, weaker CSRF mechanism.
  - `CONTENT_SECURITY_POLICY`: `script-src 'self'`, `style-src 'self'
    'unsafe-inline'`, `img-src 'self' data:`, `connect-src 'self'`,
    `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`,
    `frame-ancestors 'none'`. **No CDN, no remote origin, no inline script.**
  - `SPAStaticFiles` serves `frontend/dist` with SPA fallback; anything under
    `assets/` 404s instead of returning `index.html`.
- `backend/api.py` — the single data router: `router = APIRouter(prefix="/api")`.
  Its module docstring is the project's contract for user isolation and for the
  status-code policy (§12/§13/§23): **401** without a session, **403** for an
  authenticated user lacking a role, **404** for a resource outside the caller's
  scope. Follow it.
- `backend/proxy.py` — trusted-proxy / client-IP resolution (only if you extend
  the throttle).
- `backend/metrics.py` — the counters used by the auth and retention paths; add
  new counters here rather than ad-hoc logging.

### 1.2 Authentication and identity

- `backend/hosted_auth.py` — web OAuth + server-side sessions (ADR-0020).
  `resolve_session_user(request, db)` returns the active `User` or raises 401;
  the session cookie is `gch_session` (plus the optional `__Host-` prefix) and
  only its SHA-256 hash is stored.
- `backend/ownership.py` — `get_current_user` is **the** dependency that
  resolves the current user in both deployment modes (hosted: the session user;
  desktop: the synthetic local owner). Every data endpoint depends on it and
  trusts no user id from the request. New endpoints must do the same.
- `backend/models_auth.py` — `User` (`id`, `provider`, `provider_subject`,
  `email`, `display_name`, `is_active`, …). `email` is **nullable** and is never
  the identity key; the local desktop owner has `email = None`.
- `backend/api.py::_user_out` / `_build_auth_status` and
  `backend/schemas.py::UserOut` — the only identity shape the frontend sees
  (`id`, `name`, `email`). No OAuth internals, no tokens, ever.

### 1.3 Database, models, migrations

- `backend/models.py` — the user-scoped Classroom cache. Two invariants:
  - every primary key starts with `user_id`, and children reference their parent
    with a composite FK `(user_id, parent_id) → parent(user_id, id)` and
    `ondelete="CASCADE"`;
  - timestamps are **naive UTC**
    (`datetime.now(timezone.utc).replace(tzinfo=None)`).
- `backend/models_auth.py` — the app's own tables. Precedent: a new domain gets
  **its own models module**, not new classes appended to `models.py`.
- `backend/database.py` — `_import_models()` must import every mapped model so
  `Base.metadata` is complete; `init_db()` runs `create_all` on SQLite (desktop)
  and `alembic upgrade head` on PostgreSQL (hosted).
- `migrations/versions/` — revisions `0001`, `0002`, `0003`. Yours is
  **`0004`** with `down_revision = "0003"` and a docstring explaining every table
  and index (see `0003_stage9_session_index.py` for the tone: why an index
  exists, not a blind list).

### 1.4 Configuration, abuse control, retention

- `backend/config.py` — the env conventions: `_int_env`, `_bool_env` and
  `_csv_env(name)` (comma-separated, trimmed, empty items dropped). Most knobs
  are prefixed `GC_DASHBOARD_`; a few are deliberately plain (`COOKIE_SECURE`,
  `APP_BASE_URL`, `TURNSTILE_SITE_KEY`). Choose per §12 and document the choice.
- `backend/rate_limit.py` — the in-memory token bucket (`RateLimiter.allow`),
  hosted-only, registry owned by `app.state.rate_limiter`, injectable clock.
- `backend/main.py::throttle_abuse_surfaces` — the existing per-IP buckets
  (`login`, `sync`, `cache`) and the 429 + `Retry-After` mapping.
- `backend/maintenance.py` — retention and account deletion.
  `delete_user_data(db, user)` deletes one user's rows explicitly and cascades
  the cache from `courses`. **The feedback tables must be deleted there too**
  (§5.5).
- `.env.example`, `.env.local.example` — the documented server-side variables;
  `.env.example` is committed with placeholders only.

### 1.5 Deployment

- `compose.yml` / `compose.local.yml` — `web` (uvicorn, serves `/api` **and** the
  built SPA), `worker`, `postgres`, `caddy`, `cloudflared`. `web` runs a
  **single replica** precisely because the rate limiter is in-process. Both
  `web` and `worker` mount the `appdata` volume at `/data`.
- `Dockerfile` — two-stage build; the runtime installs **only**
  `backend/requirements-prod.txt`, copies `backend/`, `migrations/`,
  `alembic.ini` and `frontend/dist`, and runs as the non-root `app` user with
  `/data` writable.
- `Caddyfile` — `request_body { max_size 2MB }` with the comment "the
  application has no upload feature". **This limit must change** (§7.4).

### 1.6 Frontend

- `frontend/src/App.tsx` — providers (`SettingsProvider` → `DataProvider`), the
  splash/landing/sign-in gate, and one `<Routes>` block. Add routes here.
- `frontend/src/api.ts` — the single `request()` helper: `BASE = "/api"`,
  `credentials: "same-origin"`, `Content-Type: application/json`, a module-level
  401 handler (`setUnauthorizedHandler`), and `ApiError = Error & {status}`.
  Add the feedback calls to the exported `api` object — do not create a second
  fetch wrapper and do not bypass the 401 handler.
- `frontend/src/types.ts` — wire types are **generated** from OpenAPI
  (`api-schema.d.ts`, via `npm run gen:api:file` / `tools/dump_openapi.py`) and
  re-exported through the `Wire<>` / `DeepRequired<>` helpers. Only the app's own
  concepts are hand-written.
- `frontend/src/components/Sidebar.tsx` — the `ITEMS` array drives navigation
  (`to`, `labelKey`, `icon`, optional `counter`); icons come from `lucide-react`.
- `frontend/src/i18n.ts` + `frontend/src/i18n/{en,uk,ru}.ts` — dependency-free
  typed dictionaries; **`en.ts` is the source of truth for `I18nKey`** and the
  other two are checked with `satisfies Record<I18nKey, string>`, so a new key
  without `uk`/`ru` translations breaks `tsc`. Never hardcode user-facing
  strings in a component.
- `frontend/src/styles/{base,layout,components,pages}.css` — plain CSS with
  design tokens (`--bg`, `--bg-elevated`, `--bg-muted`, `--border`, `--text`,
  `--text-muted`, `--accent`, `--accent-soft`, `--danger`, `--success`,
  `--warning`, `--radius`, `--shadow`, …) plus a dark-theme block. **No
  Tailwind.** Existing classes worth reusing: `.card`, `.button`,
  `.button-primary`, `.button-danger`, `.badge`, `.stat-grid`, `.stat-card`,
  `.modal-backdrop`, `.modal`, `.empty-state`, `.back-link`.
- `frontend/src/components/AssignmentModal.tsx` — the modal pattern
  (`modal-backdrop` + `role="dialog"` + `aria-modal`, close on backdrop click).
  There is **no `window.confirm` anywhere** in this codebase, so the delete
  confirmation must be a real React dialog.
- `frontend/src/components/Skeletons.tsx` (`SectionSkeleton`, `EmptyState`) and
  `frontend/src/components/Toaster.tsx` — the existing loading/empty/toast
  primitives; reuse them instead of inventing new ones.
- `frontend/src/context/DataContext.tsx` — three contexts (`useAuth`, `useSync`,
  `useCourses`); subscribe to the narrowest one.
- `frontend/src/test/setup.ts` and the `*.test.ts(x)` files next to each module —
  vitest + @testing-library/react + jsdom. There is no test infrastructure
  beyond this; add tests in the same style.

### 1.7 Tests, lint, types

- `tests/conftest.py` — puts `backend/` on `sys.path`, points
  `GC_DASHBOARD_DATA_DIR` at a temp dir, **pops** the stage-9 env knobs so a
  developer's shell cannot change them, and provides `client` (desktop app),
  `hosted_client` (`create_app(hosted=True)` on `https://gch.test`), `db` and
  `owner_id`.
- `tests/test_user_isolation.py` — the reference for user-isolation tests:
  `_make_user`, `_add_session`, switching the session with
  `hosted_client.cookies.set("gch_session", raw_token)`.
- `tests/test_user_scoped_schema.py` — asserts `user_id` is in the primary key
  of every user-scoped table. **Your new tables must satisfy it.**
- `pytest.ini` (`testpaths = tests`, `pythonpath = backend`), `ruff.toml`
  (`[lint.isort] known-first-party` — add the new backend modules),
  `pyrightconfig.json`, `frontend/package.json` (`npm run lint`, `npm run test`,
  `npm run build`, `npm run gen:api:file`).

---

## 2. Non-negotiable constraints

1. **Do not touch the authentication system.** No new login, no second session
   table, no client-supplied identity. `get_current_user` stays the only way to
   learn who the caller is.
2. **All authorization is enforced on the backend.** Hiding a route or a nav
   item in React is UX, never security.
3. **Do not break** Google OAuth, the Classroom sync, courses, assignments,
   grades, the teacher surfaces, the desktop build, or any existing endpoint.
   The change is additive.
4. **Do not put a user id in a request parameter** to decide whose data to read
   or write. The user's own endpoints derive it from `get_current_user`.
5. **Do not hardcode administrator emails** anywhere — not in Python, not in
   TypeScript, not in a committed fixture.
6. **Never expose `ADMIN_EMAILS` to the frontend.** No `VITE_`-prefixed
   variable, no injected config, no `/api/config` field.
7. **Markdown is untrusted input.** Store the Markdown source, render it
   sanitized, never inject untrusted HTML.
8. **Do not log** message bodies, attachment contents, tokens, session cookies
   or env values. `backend/access_log.py` already redacts queries and secrets —
   keep it that way.
9. **Naive UTC** timestamps, like every other table in this schema.
10. **Do not disable or weaken** the Host/Origin guard, the CSRF check, the CSP
    or the existing rate limits to make a ticket endpoint work.

---

## 3. What "done" looks like

A signed-in user opens a Feedback entry page, chooses *Create ticket* or
*My tickets*, writes a ticket with a category, a subject, a Markdown message and
attachments, reads the whole conversation later, and replies — under their own
identity, shown automatically.

An administrator sees a dashboard with counts, a filterable list of all tickets,
any ticket's full conversation, can answer with a chosen public display name,
change the status, and permanently delete a ticket behind an explicit
confirmation.

A regular authenticated user cannot see another user's ticket, cannot reach any
admin endpoint, and cannot delete anything. An anonymous browser cannot reach the
feature at all.

---

## 4. Fixed decisions (do not re-litigate these)

Chosen during planning. Implement them as stated; if one is truly impossible,
implement the closest safe variant and document the deviation.

### 4.1 Deployment mode

The feature is **hosted-first** but works in both modes, because
`get_current_user` abstracts over them. The desktop build's single local owner is
an ordinary user with `email = None` and therefore **never** an administrator
(§6). Admin entry points stay hidden whenever the server does not report the
user as an administrator.

### 4.2 Identity comes from the session, never from the form

The ticket form must **not** contain name or email inputs (the reference
screenshots show them; do not copy that). `User.display_name` / `User.email` are
already refreshed from Google at every login.

### 4.3 Category is a closed set, subject is free text

`category ∈ {suggestion, bug, problem, other}`, validated server-side against the
literal set (a Pydantic enum is the natural fit) and rejected with **422** for
anything else. Do not merge the two fields into one.

### 4.4 Statuses

`new`, `in_progress`, `resolved`. Stored lowercase; the frontend maps them to
localized labels and badge classes.

### 4.5 A reply to a resolved ticket reopens it

Decision: **reopen**. Posting a new message sets the status back to
`in_progress`. It is simple, predictable, and it cannot silently swallow a
customer's follow-up. State this in the ADR and make it visible in the UI (the
user sees the status change immediately; the administrator sees who reopened it
in the timeline).

### 4.6 Attachments are optional

The whole feature must work with zero files. Attachments are additive.

### 4.7 Deletion is real and irreversible

A hard delete of the row plus its dependents — no `deleted_at`, no soft delete,
no restore. The database cascades (§5.3) and the files are unlinked (§7.3).

### 4.8 One Markdown editor component

`@uiw/react-md-editor` is used for ticket creation, user replies and admin
replies through **one** shared wrapper. Three copies of the toolbar logic is a
defect, not a variation.

---

## 5. Data model

### 5.1 Files

- `backend/models_feedback.py` — a new module, following the `models_auth.py`
  precedent. Register every class in `backend/database.py::_import_models()`.
- `backend/schemas_feedback.py` — the Pydantic models for this feature
  (`schemas.py` holds the shared response models; a domain-specific module keeps
  the feedback surface readable). Extending `schemas.py` is acceptable — but be
  consistent.
- `backend/admin_auth.py` — the admin dependency (§6).
- `backend/feedback_api.py` — the user-facing router (§8).
- `backend/feedback_admin_api.py` — the admin router (§8).
- `backend/feedback_attachments.py` — validation, safe storage and authorized
  serving of uploaded files (§7).

Add the new backend modules to `ruff.toml`'s `known-first-party`.

### 5.2 Tables

`feedback_tickets`

| column | type | notes |
| --- | --- | --- |
| `id` | Integer PK | autoincrement |
| `user_id` | Integer FK → `users.id`, `ondelete="CASCADE"` | the owner |
| `category` | String(32) | `suggestion` / `bug` / `problem` / `other` |
| `subject` | String(200) | required, trimmed, non-empty |
| `status` | String(32) | `new` / `in_progress` / `resolved`, default `new` |
| `created_at` | DateTime, not null | naive UTC |
| `updated_at` | DateTime, not null | naive UTC, bumped on every message |

`ticket_messages`

| column | type | notes |
| --- | --- | --- |
| `id` | Integer PK | autoincrement |
| `ticket_id` | Integer FK → `feedback_tickets.id`, `ondelete="CASCADE"` | |
| `author_user_id` | Integer FK → `users.id`, `ondelete="CASCADE"` | the **real** author, always the authenticated user |
| `author_type` | String(16) | `USER` or `ADMIN` — the machine-readable distinction |
| `display_name` | String(255) | for `USER`: from the profile; for `ADMIN`: the chosen public name |
| `author_email` | String(255), nullable | real address, administrators only; **never** sent to a regular user |
| `body_markdown` | Text | the Markdown **source**, not HTML |
| `created_at` | DateTime, not null | naive UTC |

`ticket_attachments`

| column | type | notes |
| --- | --- | --- |
| `id` | Integer PK | autoincrement |
| `message_id` | Integer FK → `ticket_messages.id`, `ondelete="CASCADE"` | |
| `ticket_id` | Integer FK → `feedback_tickets.id`, `ondelete="CASCADE"` | denormalized for authorization queries; keep both consistent |
| `stored_name` | String(255) | server-generated, never the client's filename |
| `original_name` | String(255) | display only, sanitized |
| `content_type` | String(128) | sniffed server-side |
| `size_bytes` | Integer | server-measured |
| `created_at` | DateTime, not null | naive UTC |

`ticket_id` on an attachment is derived from `message_id` on the server; a
client never sets it.

### 5.3 Indexes (justify each in the migration docstring)

- `ix_feedback_tickets_user_updated` on `(user_id, updated_at DESC)` — the
  "My tickets" list, sorted by last activity, scoped to one user.
- `ix_feedback_tickets_status_updated` on `(status, updated_at DESC)` — the admin
  list and the dashboard, filtered by status.
- `ix_feedback_tickets_category` on `(category)` — the admin category filter.
- `ix_ticket_messages_ticket_created` on `(ticket_id, created_at)` — the
  conversation, always chronological.
- `ix_ticket_messages_author` on `(author_user_id)` — administrator audit.
- `ix_ticket_attachments_message` on `(message_id)` — loading a message's files.
- No uniqueness on `(user_id, subject)`: the product does not promise it.

### 5.4 Migration

`migrations/versions/0004_feedback_tickets.py`, `revision = "0004"`,
`down_revision = "0003"`. Real `upgrade()` / `downgrade()` with `op.create_table`
/ `op.create_index` / `op.drop_table` in dependency order (users → tickets →
messages → attachments), and a docstring stating what each index serves. Verify
it against a real PostgreSQL (§16), not only SQLite: `init_db()` upgrades by
Alembic only on PostgreSQL, so a broken revision would not surface in the
desktop tests.

### 5.5 Retention and account deletion

`backend/maintenance.py::delete_user_data` must also remove the user's feedback
rows (and their attachment files, §7.3) and report the counts in its returned
dict next to `sessions`, `tokens`, `courses` and `sync_status`. The documented
rule in that module: no global "clear everything" helper, and never another
user's rows as a side effect. Keep it.

Any retention window for closed tickets belongs in `purge_expired`, with a
documented TTL — and the default must be "keep forever" unless §15 says
otherwise.

---

## 6. Administrators

### 6.1 Configuration

Add to `backend/config.py`, next to the other `_csv_env` readers:

```python
# Comma-separated allow-list of administrator accounts (lower-cased e-mails).
# Empty or missing means NOBODY is an administrator — fail closed, never open.
ADMIN_EMAILS: frozenset[str] = frozenset(
    email.strip().lower() for email in _csv_env("ADMIN_EMAILS") if "@" in email
)
```

Rules:

- read from the process environment only, **server-side only**;
- split on commas, trim whitespace, lower-case, drop empty items;
- malformed entries (no `@`) are dropped;
- unset or empty ⇒ the set is empty ⇒ nobody is an administrator;
- no fallback default, no "first user is admin", no wildcard;
- documented in `.env.example` (with a placeholder) and in the ADR. Add a
  commented placeholder to `.env.local.example` rather than a live value.

`ADMIN_EMAILS` (unprefixed) follows the precedent of `COOKIE_SECURE`,
`APP_BASE_URL` and `TURNSTILE_SITE_KEY`: an identity/authorization value that
must not look like a tuning knob. All the new **limits** (§12) do take the
`GC_DASHBOARD_` prefix.

### 6.2 `require_admin()`

New module `backend/admin_auth.py`:

```python
def require_admin(
    user: User = Depends(ownership.get_current_user),
) -> User:
    """The caller, if a configured administrator; 403 otherwise."""
```

Behaviour:

1. `get_current_user` has already rejected the anonymous case with 401 — do not
   re-implement session parsing;
2. normalize the caller's email: `(user.email or "").strip().lower()`;
3. an empty email (the desktop local owner) or one outside `ADMIN_EMAILS` ⇒
   `HTTPException(403)`;
4. otherwise return the `User`.

Every admin endpoint depends on this. No route checks the list by hand; no route
forgets the check.

### 6.3 How the frontend learns about it

The admin flag is a **boolean derived by the backend** on an existing
authenticated response — never the list of addresses. Either extend `UserOut`
with `is_admin: bool` computed from the same membership test, or add a single
`GET /api/me/admin` returning `{is_admin: true|false}` behind `get_current_user`.
The sidebar renders the admin entry from that flag only. Pick one; do not
implement both.

---

## 7. Attachments

There is **no upload mechanism in this repository today** — `Caddyfile` even
says so. You are adding the first one, so the simplest secure design wins.

### 7.1 Allowed types and limits

- Types (server-side allow-list, matched on sniffed content; the extension is
  only a hint): `image/jpeg`, `image/png`, `image/gif`, `application/pdf`,
  `text/plain`. Nothing else.
- Per file: **≤ 5 MB**. Per message: **≤ 3 files** and **≤ 10 MB** in total.
- Subject ≤ 200 chars, message body ≤ 20 000 chars, display name ≤ 100 chars.
- The 64 MB limit visible in the reference screenshot is **not** adopted: the
  target is a 1–2 vCPU VPS behind a Cloudflare Tunnel with a single web replica,
  and multipart bodies are parsed in-process.

Make the three size numbers configurable (§12) with exactly these defaults.

### 7.2 Validation

- **Never trust the filename or the client `Content-Type`.** Sniff the bytes
  (magic numbers for JPEG/PNG/GIF/PDF, a UTF-8 decodability check for text) and
  reject anything that does not match the allow-list.
- Reject executables and active content regardless of the sniff result (`.exe`,
  `.sh`, `.js`, `.html`, `.svg`, `.php`, double extensions such as `x.html`).
  Store the file under the **sniffed** type's extension, not the uploaded one.
- Enforce the limits while **streaming** the upload, not after it is fully in
  memory: read in chunks and abort as soon as the byte budget is exceeded.

### 7.3 Storage and serving

- Store under `DATA_DIR` (from `backend/path_config.py`; `/data` in the
  container, already a mounted volume) in a per-ticket subdirectory, e.g.
  `DATA_DIR / "feedback" / f"{ticket_id}"`, with a server-generated file name
  (`uuid4().hex` + the canonical extension). The client's filename is display
  metadata only.
- Resolve the final path and verify it stays inside the feedback root
  (path-traversal defence) before writing and before deleting.
- **Serving is an authorized API endpoint**, e.g.
  `GET /api/feedback/attachments/{id}`: load the row, check that the caller is
  either the ticket's owner or an administrator, then return a `FileResponse`.
  Never add an unauthenticated static mount for uploads — `frontend/dist` is the
  only static mount, and the SPA fallback would otherwise expose whatever it
  finds.
- Headers: the sniffed `Content-Type` or `application/octet-stream`, plus
  `Content-Disposition: attachment`. Never `inline` for anything a browser might
  treat as active content. `X-Content-Type-Options: nosniff` is already global.
- Deletion: the admin delete endpoint and `maintenance.delete_user_data` must
  unlink the files as well as the rows, and must not fail the whole request
  because a file is already gone.

### 7.4 Edge limit

`Caddyfile`'s `request_body { max_size 2MB }` would reject every multipart
upload. Raise it to fit the worst case (10 MB of files plus form fields ⇒ use
**16MB**) and replace the now-false comment. Check `compose.loadtest.yml` and
any other edge config for a duplicate limit.

### 7.5 Dependency

`python-multipart` is required by FastAPI for multipart form parsing and is
**not** installed today. Add it to `backend/requirements.txt` (range) and
`backend/requirements-prod.txt` (exact pin, matching that file's style).

---

## 8. API

Two routers, included from `backend/main.py` next to `api.py`
(`app.include_router(...)`), inside the hosted middleware stack. They live under
`/api`, so the session gate, the Host/Origin guard, the CSRF check and
`Cache-Control: no-store` already apply.

### 8.1 User-facing — `backend/feedback_api.py`

`router = APIRouter(prefix="/api/feedback", tags=["feedback"])`

| method | path | notes |
| --- | --- | --- |
| `POST` | `/tickets` | create a ticket (multipart with the message and files, or JSON — pick one and document it) |
| `GET` | `/tickets` | **the caller's own** tickets, newest activity first |
| `GET` | `/tickets/{ticket_id}` | one own ticket with its messages and attachments |
| `POST` | `/tickets/{ticket_id}/messages` | reply to an own ticket |
| `GET` | `/attachments/{attachment_id}` | authorized download (§7.3) |

Every handler takes `user: User = Depends(ownership.get_current_user)`, and
every query filters on `ticket.user_id == user.id` **inside the same statement** —
never fetch-then-check. A ticket id that exists but belongs to someone else must
answer **404**, identical to a ticket that does not exist (§23: do not disclose
another user's rows). A 403 here would confirm the id is real.

### 8.2 Admin — `backend/feedback_admin_api.py`

`router = APIRouter(prefix="/api/admin/feedback", tags=["admin"])`

Every handler takes `admin: User = Depends(require_admin)`.

| method | path | notes |
| --- | --- | --- |
| `GET` | `/tickets` | all tickets; filters `status`, `category`, `q` (subject/message substring), pagination (`limit`/`offset`) |
| `GET` | `/tickets/{ticket_id}` | any ticket: full conversation, author e-mails, attachments |
| `POST` | `/tickets/{ticket_id}/messages` | admin reply with a chosen public display name |
| `PATCH` | `/tickets/{ticket_id}` | change `status` (and only status) |
| `DELETE` | `/tickets/{ticket_id}` | permanent delete (§8.4) |
| `GET` | `/stats` | dashboard counters |

### 8.3 Message creation contract

Both reply endpoints share one service function that takes the **authenticated**
author plus only the inputs it may accept:

- user path: `author_type = "USER"`, `author_user_id = current user`,
  `display_name = user.display_name or user.email or "User"`,
  `author_email = user.email`. **The request body has no author fields at all.**
  A body containing `author_user_id`, `author_type` or a custom `display_name`
  must be rejected or ignored — it must never take effect.
- admin path: `author_type = "ADMIN"`, `author_user_id = the authenticated
  administrator` (never a value from the body), `display_name` = the
  administrator's chosen public label (default `"GoogleClassHelp Support"`),
  `author_email` = the administrator's own address.

Two administrators may therefore post under different public names while the
internal author stays correct. Both paths bump the ticket's `updated_at` and
apply §4.5.

### 8.4 Delete contract

- A real `DELETE`: remove the row, let `ON DELETE CASCADE` remove the messages
  and attachment rows, and unlink the files (§7.3). No soft delete, no
  `deleted_at`.
- Answer **204 No Content** on success. (`DELETE /api/cache` in this codebase
  returns a small model instead; either is acceptable — be consistent within the
  feature.)
- The confirmation warning lives in the **frontend** (§10.6); a backend cannot
  ask a question, so it simply performs the delete. Do not invent a server-side
  confirmation token.
- After deletion the ticket must be unreachable: 404 for the owner, 404 for an
  administrator, and absent from a fresh `GET /api/feedback/tickets`.

### 8.5 Error mapping

- 401 — no session (middleware).
- 403 — authenticated but not an administrator (admin routers).
- 404 — the resource is not the caller's, or does not exist.
- 409 — only for a genuine state conflict; never for validation.
- 413 — the upload exceeded the byte budget (the edge may reject it first).
- 422 — validation failure: bad category, empty subject, empty message, body too
  long, disallowed file type.
- 429 + `Retry-After` — rate limited (§9).

Use `HTTPException` with a short, non-sensitive `detail`. Never return a stack
trace, a filesystem path or an SQL fragment.

---

## 9. Limits and rate limiting

The project already has an in-memory token-bucket limiter
(`backend/rate_limit.py`, hosted-only, `app.state.rate_limiter`, injectable
clock). **Reuse it** — no second limiter, no Redis, no `SlowAPI` wrapper.

### 9.1 Buckets

The existing `throttle_abuse_surfaces` middleware is keyed by IP, which is right
for anonymous abuse but wrong for authenticated ticket spam (a school NAT shares
one address). So:

- keep `throttle_abuse_surfaces` for a coarse per-IP cap in front of the
  upload-heavy endpoints, and
- add a **per-user** bucket inside the ticket endpoints, keyed
  `f"feedback:create:{user.id}"` / `f"feedback:reply:{user.id}"`, using
  `request.app.state.rate_limiter.allow(...)` and answering 429 with
  `Retry-After` exactly like the existing code.

Sane first-production defaults (env-configurable, §12):

| what | limit |
| --- | --- |
| ticket creation | 5 per hour per user |
| replies | 30 per hour per user |
| subject | 200 chars |
| message body | 20 000 chars |
| display name | 100 chars |
| attachments | 3 files, 5 MB each, 10 MB total |

### 9.2 Validation is server-side only

An empty subject, an empty/whitespace message, an over-long body, an unknown
category and a bad file type are all rejected by the backend. Frontend
validation is a convenience, never the control.

---

## 10. Frontend

### 10.1 The editor component

New `frontend/src/components/MarkdownField.tsx` — the single wrapper around
`@uiw/react-md-editor`, used by ticket creation, user replies and admin replies.
Props: `value`, `onChange`, optional `placeholder`, optional `minHeight`,
`disabled`.

- Package `@uiw/react-md-editor@^4.1.2` (peer `react >=16.8`; this project is on
  React 18.3.1, so it is compatible). Add it to `frontend/package.json`
  **dependencies** and commit the updated `package-lock.json`.
- Sanitize the preview and every rendering of stored Markdown:
  `previewOptions={{ rehypePlugins: [[rehypeSanitize]] }}` for the editor and the
  same `rehypePlugins` prop on `MDEditor.Markdown` for the read-only view. Add
  `rehype-sanitize` to dependencies. Never use `dangerouslySetInnerHTML` for
  ticket content.
- **CSP**: `script-src 'self'` and `style-src 'self' 'unsafe-inline'` mean no
  CDN. Import the editor's stylesheet locally inside your component; no `<link>`
  to unpkg/jsdelivr, no remote fonts, no remote highlight.js themes.
- Keep the toolbar to what a support ticket needs: bold, italic, heading, link,
  bulleted list, numbered list, quote, code, preview, fullscreen. Hide anything
  that inserts a remote image if it cannot be made safe.
- Theme it with the existing tokens so it looks native in light and dark mode.
- Do not reimplement the toolbar by hand (§4.8).

A read-only `frontend/src/components/Markdown.tsx` (built on
`MDEditor.Markdown` with `rehype-sanitize`) renders the conversation.

### 10.2 Routes

```
/feedback                      entry: choose Create ticket | My tickets
/feedback/new                  create form
/feedback/tickets              my tickets
/feedback/tickets/:id          conversation + reply
/admin                         admin shell (dashboard + navigation)
/admin/feedback                all tickets, filters, search
/admin/feedback/:id            any ticket: conversation, reply, status, delete
```

Register them in `frontend/src/App.tsx`. Guard the `/admin` routes with a small
component that reads the admin flag and renders a "not available" state (or
redirects to the dashboard) when it is false — while remembering that this is UX
only, and the API answers 403 regardless.

### 10.3 Navigation

Add a *Feedback* entry to the `ITEMS` array in `Sidebar.tsx` (a `lucide-react`
icon such as `MessageSquare`/`LifeBuoy`) and an *Admin* entry **only** when the
admin flag is true. Keep the `ITEMS`-driven structure; do not bolt on a second
navigation mechanism.

### 10.4 Pages and components

One concern per component; the names are suggestions:

- `pages/FeedbackHome.tsx` — the two choices (§10.5);
- `pages/FeedbackNew.tsx` — category select, subject input, `MarkdownField`,
  attachment picker, submit;
- `pages/FeedbackTickets.tsx` — id, category, subject, status, updated, created;
  empty state via the existing `EmptyState`;
- `pages/FeedbackTicket.tsx` — conversation + reply;
- `pages/AdminDashboard.tsx` — the `StatCard`/`stat-grid` pattern: total, new, in
  progress, resolved, plus recent tickets;
- `pages/AdminFeedback.tsx` — list + filters + search;
- `pages/AdminFeedbackTicket.tsx` — conversation, reply form with the display
  name input, status control, delete button;
- `components/TicketConversation.tsx`, `components/TicketMessage.tsx` (styling
  per `author_type`), `components/AttachmentList.tsx`,
  `components/ConfirmDialog.tsx`.

### 10.5 Entry page

When an authenticated user opens Feedback, show a clear choice — **not** the
creation form directly: "Create ticket" and "My tickets", each its own card or
button linking to `/feedback/new` and `/feedback/tickets`. The copy must make the
difference obvious in all three languages.

### 10.6 Delete confirmation (mandatory)

Before any delete request is sent, show a prominent warning dialog:

> **Delete this ticket permanently?**
> This action cannot be undone. The ticket conversation and its attachments
> will be permanently deleted.

with `[ Cancel ]` and `[ Delete permanently ]`, the destructive action styled
with `.button .button-danger` and clearly separated from cancel. Reuse the
`modal-backdrop` / `modal` pattern of `AssignmentModal.tsx` (`role="dialog"`,
`aria-modal="true"`, labelled, closable with Escape and backdrop click). Do
**not** use `window.confirm` — it does not exist in this codebase and is not
accessible enough for a destructive action.

Requiring a typed confirmation phrase is optional; the two-button modal is the
minimum and the default.

### 10.7 Visual distinction of messages

`TicketMessage` branches on `author_type` — never on the name or the e-mail:

- `USER` — neutral surface (`--bg-elevated`, `--border`);
- `ADMIN` — a distinct accent treatment (`--accent-soft` background, an accent
  left border, a support badge) that reads differently at a glance in both
  themes.

Add the classes to `frontend/src/styles/pages.css` (or `components.css`) using
the existing tokens. No new CSS framework, no inline `style={{}}` blobs.

### 10.8 Data access

Add the feedback methods to the `api` object in `frontend/src/api.ts` and the
types to `types.ts` through the generated `Wire<>` helpers. After changing the
backend schemas, regenerate the wire types:

```
python tools/dump_openapi.py            # writes openapi.json
cd frontend && npm run gen:api:file     # rewrites src/api-schema.d.ts
```

Commit the regenerated `api-schema.d.ts`. `tsc` must be able to fail on a
wire-shape change — that is the point of the generated file.

### 10.9 States

Every page must handle: loading (reuse `SectionSkeleton`), empty list
(`EmptyState`), submit in progress (disabled button), success (navigate, refresh,
toast through the existing `Toaster`), failure (a visible message, never a
silent console error), 401 (the shared `api.ts` handler signs the browser out),
403 on an admin route, 404 for a missing or deleted ticket, 413/422 on an upload
problem, and 429 with its `Retry-After`.

### 10.10 Text

All user-visible strings go into `frontend/src/i18n/{en,uk,ru}.ts` under the
project's key naming (`feedback.*`, `admin.*`). Add every key to **all three**
files — `en.ts` defines `I18nKey` and the others are type-checked against it, so
a missing `uk`/`ru` entry is a build failure.

### 10.11 The reference screenshots

`screenshot 1.png` and `screenshot 2.png` (in this folder) are **structural**
references from another product: labelled support forms, a bordered Markdown
editor with a toolbar, a large message area, an attachments block with an "add
another" control, and primary/secondary buttons. Take the structure; do not copy
that product's styling, branding or fields. Specifically drop:

- the manual `Ім'я` / `Електронна пошта` inputs — identity comes from the session
  (§4.2);
- `Для акаунту` and `Пріоритет` — not part of this data model;
- the stated 64 MB limit — replaced by §7.1.

Keep: clear labels, a large message field, an attachments section, one obvious
primary action per form.

---

## 11. Security model (server-enforced)

| actor | may |
| --- | --- |
| anonymous | nothing — 401 from the session gate on every feedback endpoint |
| authenticated user | create a ticket; list/read/reply to **own** tickets only; download own attachments; never delete |
| authenticated administrator | additionally: list/read/reply to any ticket, change status, delete permanently, read author e-mails, download any attachment, read `/stats` |

Explicitly forbidden, and each covered by a test:

- any user-supplied `user_id` deciding the data scope;
- reading or writing another user's ticket (404, not 403 — see §8.1);
- a user reply that sets `author_type`, `author_user_id`, `author_email` or a
  custom `display_name` (the body must not contain them; extra fields must never
  change the stored identity);
- any admin endpoint without `require_admin`;
- uploading an executable, a script or active content;
- fetching an attachment without ownership;
- rendering untrusted Markdown without sanitization;
- deleting a ticket without the UI confirmation (§10.6);
- `ADMIN_EMAILS` reaching the browser bundle.

---

## 12. Environment variables

| variable | default | purpose |
| --- | --- | --- |
| `ADMIN_EMAILS` | *(empty)* | comma-separated administrator e-mails; server-side only (§6) |
| `GC_DASHBOARD_FEEDBACK_TICKETS_PER_HOUR` | `5` | per-user ticket creation |
| `GC_DASHBOARD_FEEDBACK_REPLIES_PER_HOUR` | `30` | per-user replies |
| `GC_DASHBOARD_FEEDBACK_MAX_SUBJECT_CHARS` | `200` | subject length |
| `GC_DASHBOARD_FEEDBACK_MAX_MESSAGE_CHARS` | `20000` | message length |
| `GC_DASHBOARD_FEEDBACK_MAX_ATTACHMENTS` | `3` | files per message |
| `GC_DASHBOARD_FEEDBACK_MAX_ATTACHMENT_BYTES` | `5242880` | 5 MB per file |
| `GC_DASHBOARD_FEEDBACK_MAX_TOTAL_BYTES` | `10485760` | 10 MB per message |

Read them through the existing `config.py` helpers (`_int_env` with a
non-negative minimum, `_csv_env` for `ADMIN_EMAILS`) and document each one in
`.env.example` in the commented style of its neighbours. Follow the
`tests/conftest.py` precedent and pop the new knobs there, so a developer's shell
cannot change them under the suite.

---

## 13. Tests

Backend tests live in `tests/` (pytest; `testpaths = tests`,
`pythonpath = backend`). Reuse the `client` / `hosted_client` / `db` fixtures and
the session helper pattern of `tests/test_user_isolation.py` (`_make_user`,
`_add_session`, `hosted_client.cookies.set("gch_session", token)`).

Remember the CSRF check: an unsafe hosted request without `Origin` is judged by
`Sec-Fetch-Site`, so send `Sec-Fetch-Site: same-origin` (or an `Origin`) on
POST/PATCH/DELETE exactly as `tests/test_stage8_coexistence.py` does.

Suggested files: `tests/test_feedback_tickets.py` (user surface),
`tests/test_feedback_admin_auth.py` (admin surface and `ADMIN_EMAILS` parsing),
`tests/test_feedback_attachments.py` (upload validation and serving).

Required cases:

1. anonymous → 401 on ticket create, list, read, reply and attachment download;
2. anonymous → 401 on every admin endpoint;
3. a user can create a ticket; `author_type == "USER"` and `display_name` come
   from the profile;
4. a user can list tickets and sees **only** their own;
5. a user can open their own ticket with its messages;
6. a user cannot open another user's ticket — 404, not 403, and no content;
7. a user can reply to their own ticket; replying to a `resolved` ticket sets it
   back to `in_progress`;
8. a user cannot reply to another user's ticket;
9. a user reply body containing `author_type` / `author_user_id` /
   `display_name` does not change the stored identity;
10. a regular user → 403 from every admin endpoint (list, read, reply, patch,
    delete, stats);
11. a regular user attempting to delete → 403/404, never a deletion;
12. an admin can list all tickets, filter by status and category, and search by
    `q`;
13. an admin can open any ticket and sees the author's e-mail;
14. an admin can reply: `author_type == "ADMIN"`, `author_user_id` is the
    authenticated administrator, and the public `display_name` is what was
    chosen — two administrators, two different names, both correct internally;
15. an admin can change the status; an invalid status is rejected;
16. an admin can delete a ticket permanently: the row, its messages and its
    attachment rows are gone and the files on disk are unlinked;
17. after deletion the ticket is unreachable (404 for the owner too);
18. `ADMIN_EMAILS` parsing: comma-separated, trimmed, lower-cased, empty items
    ignored, entries without `@` dropped;
19. the comparison is case-insensitive (`Admin@Example.com` in the environment
    matches `admin@example.com`);
20. empty/unset `ADMIN_EMAILS` ⇒ 403 for everybody, including a plausible
    looking address;
21. the desktop local owner (`email is None`) is never an administrator;
22. invalid category → 422; empty/whitespace subject → 422; empty/whitespace
    message → 422;
23. an over-long subject or body → 422;
24. rate limits: the N+1th creation or reply inside the window → 429 with
    `Retry-After` (reset the limiter between tests via `RateLimiter.reset()`);
25. attachments rejected: a `.png` that is actually a ZIP or an ELF, an `.exe`,
    an `.html`, a traversal filename (`../../etc/passwd`), an over-sized file, and
    an empty file named `.png`;
26. user A cannot download user B's attachment (404);
27. the file is stored under a server-generated name and served with
    `attachment` + `nosniff`, never from a public static path;
28. `delete_user_data` also removes that user's tickets, messages, attachment rows
    and files, and no other user's rows;
29. the new tables satisfy the invariant of `tests/test_user_scoped_schema.py`
    (`user_id` in the primary key of every user-scoped table) — extend that test
    if it enumerates tables explicitly;
30. Markdown safety: a body containing `<script>`, `<img onerror=…>`,
    `[x](javascript:alert(1))` and `<iframe>` is stored verbatim as Markdown, and
    the rendered output is sanitized.

Frontend tests (vitest + @testing-library/react, `frontend/src/test/setup.ts`),
in the existing `*.test.tsx` style:

- the Feedback entry renders both choices and navigates;
- the create form refuses an empty subject before calling the API;
- `TicketMessage` renders USER and ADMIN messages with different classes;
- `ConfirmDialog` fires the delete callback only after the destructive action is
  clicked;
- the admin routes render the "not available" state for a non-admin;
- the sanitizer strips a `<script>` tag from stored Markdown.

---

## 14. Manual security verification

Perform each line explicitly and record the **actual** observed result in the
report — not the expected one.

| # | action | expected |
| --- | --- | --- |
| 1 | `GET /api/feedback/tickets` with no session cookie | 401 |
| 2 | `GET /api/admin/feedback/tickets` as a regular authenticated user | 403 |
| 3 | a regular user opens `/admin` in the browser | no privileged data rendered; the nav entry is absent |
| 4 | an administrator opens `/admin` | dashboard and feedback list work |
| 5 | user A opens user B's ticket id | 404 / access denied, no content |
| 6 | user A posts a message to user B's ticket id | 404 / access denied |
| 7 | a regular authenticated user sends `DELETE` for a ticket | 403 |
| 8 | an administrator clicks delete | the confirmation dialog appears **first**; after confirming, the ticket, its messages and its files are gone and the id returns 404 |
| 9 | remove `ADMIN_EMAILS`, restart the backend | nobody is an administrator |
| 10 | change `ADMIN_EMAILS` to a different address, restart | access follows the new value with no code change |
| 11 | upload a `.png` that actually contains a ZIP header | rejected |
| 12 | upload a file named `../../evil.txt` | rejected; nothing written outside the feedback directory |
| 13 | submit a Markdown body with `<script>alert(1)</script>` and a `javascript:` link | stored verbatim, rendered inert |
| 14 | grep the built frontend bundle for the administrator addresses | nothing found |

---

## 15. Documentation to update

- `docs/adr/adr-0035-*.md` — a new ADR: the feedback domain, the administrator
  allow-list from the environment, the reply-reopens-resolved rule, permanent
  deletion, and the attachment limits with the edge change. Add the row to the
  table in `docs/adr/README.md`.
- `README.md` — a short section for the feature, and the new variables if the
  env surface grew.
- `docs/TESTING_NOTES.md` — the new test files and the current "last green"
  date.
- `.env.example` — the new variables, commented like their neighbours.

---

## 16. Final verification sequence

Run these and report the real outcome of each:

```
python -m pytest                                  # backend suite, including the new tests
cd frontend && npm run lint                        # eslint + tsc
cd frontend && npm run test                       # vitest
cd frontend && npm run build                      # tsc -b && vite build
python tools/dump_openapi.py
cd frontend && npm run gen:api:file               # regenerated wire types
docker compose -f compose.local.yml build web     # the image must install python-multipart
# migrations against a clean PostgreSQL:
docker compose --env-file .env.local -f compose.local.yml run --rm --workdir /app web alembic -c /app/alembic.ini upgrade head
docker compose --env-file .env.local -f compose.local.yml up -d postgres web worker
# then exercise the feature end to end in the browser
```

Also verify by reading, not only by running:

- existing behaviour is intact: `/api/status`, `/api/courses`, `/api/grades`,
  `/api/sync`, sign-in, sign-out;
- the desktop build still starts and its tests (the `client` fixture) pass;
- `ruff.toml` lists the new backend modules in `known-first-party`;
- `backend/database.py::_import_models` imports the new models;
- nothing logs message bodies, file contents or filesystem paths;
- `git status` shows only intended files, and `frontend/package-lock.json` plus
  `frontend/src/api-schema.d.ts` are committed.

---

## 17. Final report

Deliver a concise report containing:

- files added and changed (backend, frontend, migrations, configuration);
- the database tables and the migration revision;
- the API endpoints added, with the status codes each returns;
- the frontend routes and components added;
- the Markdown editor and sanitizer packages with their versions;
- how authentication and the administrator authorization are implemented, and
  where;
- the new environment variables and their defaults;
- the tests added, and the tests actually executed with their real results;
- the manual verification of §14 with the real observed outcome per line;
- known limitations — the localhost SQLite suite vs a real PostgreSQL, the
  in-memory rate limiter being per-process, attachment files living on the
  `appdata` volume (so losing that volume loses the files while the rows remain),
  and anything in this prompt that reality contradicted.

Close with an explicit confirmation, in your own words, that:

- anonymous users cannot create, read or reply to tickets;
- an authenticated user can only reach their own tickets;
- no user can read another user's conversation;
- a regular user cannot reach any admin API;
- admin authorization is enforced by the backend, not by the frontend;
- administrator e-mails are not hardcoded and come only from `ADMIN_EMAILS`;
- `ADMIN_EMAILS` stays server-side and never reaches the browser;
- an admin reply carries an explicit `ADMIN` author type and a chosen public
  display name, while the authenticated administrator is recorded internally;
- a user reply cannot impersonate another display name;
- Markdown is rendered sanitized;
- deletion is permanent and always confirmed first.
















