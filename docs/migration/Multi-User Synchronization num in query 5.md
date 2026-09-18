# Multi-User Synchronization num in query 5

**Stage 5 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Rework background synchronization from one global loop into per-user jobs with a scheduler/worker and bounded concurrency.
- **Depends on:** stages 1-4 must be done (or their decisions recorded)
- **Source prompt sections:** §18, §19, §20, §63, §64

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

