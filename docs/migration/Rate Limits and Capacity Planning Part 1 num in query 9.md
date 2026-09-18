# Rate Limits and Capacity Planning Part 1 num in query 9

**Stage 9 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Rate limiting, Google API quotas, token-failure handling, logging, privacy, retention, and capacity planning for ~1,000 users.
- **Depends on:** stages 1-8 must be done (or their decisions recorded)
- **Source prompt sections:** §39, §40, §41, §42, §43, §44, §45  (part 1/4)

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

