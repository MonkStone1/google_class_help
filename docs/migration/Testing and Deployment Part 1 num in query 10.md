# Testing and Deployment Part 1 num in query 10

**Stage 10 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Tests (auth / isolation / sync / teacher mode), Docker + Compose + Caddy, backups, documentation, ADRs, acceptance criteria, and the final audit.
- **Depends on:** stages 1-9 must be done (or their decisions recorded)
- **Source prompt sections:** §52, §53, §54, §55, §56, §57, §58  (part 1/4)

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

