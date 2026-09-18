# Frontend and Configuration Part 2 num in query 7

**Stage 7 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Adapt the frontend to cookie sessions and 401 handling; configure CORS, host validation, trusted proxy, and environment settings.
- **Depends on:** stages 1-6 must be done (or their decisions recorded)
- **Source prompt sections:** §51 "Development vs production configuration"  (part 2/2)

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

