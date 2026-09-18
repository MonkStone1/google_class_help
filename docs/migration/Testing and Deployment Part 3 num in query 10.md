# Testing and Deployment Part 3 num in query 10

**Stage 10 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Tests (auth / isolation / sync / teacher mode), Docker + Compose + Caddy, backups, documentation, ADRs, acceptance criteria, and the final audit.
- **Depends on:** stages 1-9 must be done (or their decisions recorded)
- **Source prompt sections:** §82 "Non-negotiable acceptance criteria", §83 "What NOT to do", §84 "Expected final repository shape", §85 "Deliverables"  (part 3/4)

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

