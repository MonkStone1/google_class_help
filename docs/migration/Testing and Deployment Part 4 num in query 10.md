# Testing and Deployment Part 4 num in query 10

**Stage 10 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Tests (auth / isolation / sync / teacher mode), Docker + Compose + Caddy, backups, documentation, ADRs, acceptance criteria, and the final audit.
- **Depends on:** stages 1-9 must be done (or their decisions recorded)
- **Source prompt sections:** §86 "Final review pass", §87 "Final engineering principle"  (part 4/4)

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

