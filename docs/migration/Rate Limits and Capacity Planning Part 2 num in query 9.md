# Rate Limits and Capacity Planning Part 2 num in query 9

**Stage 9 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Rate limiting, Google API quotas, token-failure handling, logging, privacy, retention, and capacity planning for ~1,000 users.
- **Depends on:** stages 1-8 must be done (or their decisions recorded)
- **Source prompt sections:** §46, §59, §60, §61, §62, §66, §68  (part 2/4)

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

