# Overview and Stage Order num in query 0

> Navigation for the **Google Class Help — Hosting Migration** prompt, split into 10 stages,
> each stage split into parts of ~200 lines max.
> Source document: `docs/prompt/GoogleClassHelp_Hosting_Migration_Prompt (2).md`.
> Implementation order follows §81 of the source prompt: do not start with Docker before the application model is correct.

| # | Stage / part file | Goal |
|---|---|---|
| 1 | `Audit and Target Architecture num in query 1.md` | Understand the current architecture, fix the target hosted architecture, find every single-user assumption, and classify all process-global state. |
| 2 | `Web OAuth and Sessions Part 1 num in query 2.md` | Replace desktop loopback OAuth with a server-owned web OAuth flow; introduce users / sessions / oauth_tokens and secret-management rules. (part 1) |
| 2 | `Web OAuth and Sessions Part 2 num in query 2.md` | Replace desktop loopback OAuth with a server-owned web OAuth flow; introduce users / sessions / oauth_tokens and secret-management rules. (part 2) |
| 3 | `PostgreSQL and Migrations num in query 3.md` | Move from SQLite to PostgreSQL, introduce Alembic, and build a user-scoped schema with correct uniqueness constraints. |
| 4 | `User Isolation Part 1 num in query 4.md` | Introduce the get_current_user dependency, make every query, cache, and data-access path user-scoped, and close IDOR gaps. (part 1) |
| 4 | `User Isolation Part 2 num in query 4.md` | Introduce the get_current_user dependency, make every query, cache, and data-access path user-scoped, and close IDOR gaps. (part 2) |
| 5 | `Multi-User Synchronization num in query 5.md` | Rework background synchronization from one global loop into per-user jobs with a scheduler/worker and bounded concurrency. |
| 6 | `Teacher Mode and API Surface num in query 6.md` | Keep teacher mode as a per-course role, preserve business semantics, and rework the API surface carefully. |
| 7 | `Frontend and Configuration Part 1 num in query 7.md` | Adapt the frontend to cookie sessions and 401 handling; configure CORS, host validation, trusted proxy, and environment settings. (part 1) |
| 7 | `Frontend and Configuration Part 2 num in query 7.md` | Adapt the frontend to cookie sessions and 401 handling; configure CORS, host validation, trusted proxy, and environment settings. (part 2) |
| 8 | `Desktop and Hosted Coexistence Part 1 num in query 8.md` | Split desktop and hosted startup/auth paths, choose the static-asset strategy, and enable HTTPS, cookies, CSRF, and security headers. (part 1) |
| 8 | `Desktop and Hosted Coexistence Part 2 num in query 8.md` | Split desktop and hosted startup/auth paths, choose the static-asset strategy, and enable HTTPS, cookies, CSRF, and security headers. (part 2) |
| 9 | `Rate Limits and Capacity Planning Part 1 num in query 9.md` | Rate limiting, Google API quotas, token-failure handling, logging, privacy, retention, and capacity planning for ~1,000 users. (part 1) |
| 9 | `Rate Limits and Capacity Planning Part 2 num in query 9.md` | Rate limiting, Google API quotas, token-failure handling, logging, privacy, retention, and capacity planning for ~1,000 users. (part 2) |
| 9 | `Rate Limits and Capacity Planning Part 3 num in query 9.md` | Rate limiting, Google API quotas, token-failure handling, logging, privacy, retention, and capacity planning for ~1,000 users. (part 3) |
| 9 | `Rate Limits and Capacity Planning Part 4 num in query 9.md` | Rate limiting, Google API quotas, token-failure handling, logging, privacy, retention, and capacity planning for ~1,000 users. (part 4) |
| 10 | `Testing and Deployment Part 1 num in query 10.md` | Tests (auth / isolation / sync / teacher mode), Docker + Compose + Caddy, backups, documentation, ADRs, acceptance criteria, and the final audit. (part 1) |
| 10 | `Testing and Deployment Part 2 num in query 10.md` | Tests (auth / isolation / sync / teacher mode), Docker + Compose + Caddy, backups, documentation, ADRs, acceptance criteria, and the final audit. (part 2) |
| 10 | `Testing and Deployment Part 3 num in query 10.md` | Tests (auth / isolation / sync / teacher mode), Docker + Compose + Caddy, backups, documentation, ADRs, acceptance criteria, and the final audit. (part 3) |
| 10 | `Testing and Deployment Part 4 num in query 10.md` | Tests (auth / isolation / sync / teacher mode), Docker + Compose + Caddy, backups, documentation, ADRs, acceptance criteria, and the final audit. (part 4) |
