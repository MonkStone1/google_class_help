# Testing and Deployment Part 2 num in query 10

**Stage 10 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Tests (auth / isolation / sync / teacher mode), Docker + Compose + Caddy, backups, documentation, ADRs, acceptance criteria, and the final audit.
- **Depends on:** stages 1-9 must be done (or their decisions recorded)
- **Source prompt sections:** §72, §73, §77, §78, §79, §80, §81  (part 2/4)

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

