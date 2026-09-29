# Security Audit Report: google_class_help

**Audit Date**: September 25, 2026  
**Audit Directory**: `~/docs/audits/google-class-help-2026-09-25`  
**Run ID**: `gch-2026-09-25-quick`  
**Target Git Commit**: `e33d620c9c8205f0b15052b592a56b48fd842cbf` (branch `Phase-10`)  
**Run Profile**: `quick` (source-and-local-only inspection; no live targets)  
**Execution Policy**: Source analysis with local static trace evaluation  

---

## 1. Executive Summary & Security Posture

The `google_class_help` codebase is a FastAPI backend and React frontend application supporting both desktop local-mode execution and multi-user hosted operation behind Caddy and Cloudflare tunnels.

The audit identified strong defensive practices in multi-tenant data isolation and session boundaries:
- **Tenant Isolation**: Database queries consistently bind tenant queries to `owner_id` or `user_id` extracted from validated server sessions.
- **CSRF & Session Security**: Hosted mode utilizes `SameSite=Lax`, `Secure`, and `HttpOnly` cookie hygiene, paired with explicit double-submit CSRF headers across mutating endpoints.
- **OAuth Safety**: OAuth flow states in `backend/hosted_auth.py` are strictly single-use and deleted prior to upstream token exchange, eliminating authorization replay vectors.
- **Client Sanitization**: HTML previews and rendered Markdown employ DOMPurify sanitization.

Three confirmed findings were identified in service availability, distributed deployment rate-limiting, and supply chain tag mutability. In addition, three deployment-dependent candidates were documented for operator validation.

---

## 2. Confirmed Findings Summary

| Severity | Finding ID | Title | Affected Boundary | Observed Result |
| :--- | :--- | :--- | :--- | :--- |
| **Medium** | `gch/turnstile-siteverify-no-timeout` | Missing outbound socket timeout on Cloudflare Turnstile siteverify | Anonymous low-trust request vs shared worker pool | Unbounded socket wait retains worker thread during slow upstream responses. |
| **Medium** | `gch/inmemory-ratelimit-diverges-across-replicas` | In-memory rate limiting diverges across multiple web replicas | Anonymous low-trust request vs shared service spend | Per-process token bucket permits aggregate traffic scaling linearly with replica count. |
| **Low** | `gch/unpinned-cloudflared-image-tag` | Mutable `latest` tag on `cloudflared` container image | Deployment configuration vs external supply chain | Redeploying pulls arbitrary upstream image digests without repository version changes. |

---

## 3. Confirmed Findings Detail & Remediation

### 3.1. `gch/turnstile-siteverify-no-timeout`
- **Severity**: Medium (Likelihood: Medium, Impact: Medium)
- **File**: `backend/hosted_auth.py:365-366`
- **Vulnerability**: Outbound HTTPS POST to Cloudflare Turnstile `siteverify` uses `httplib2.Http()` without configuring a socket `timeout`.
- **Impact**: Unauthenticated remote clients hitting `POST /api/auth/login/start` can hold web server worker threads indefinitely if Cloudflare's endpoint hangs or delays response, leading to thread pool starvation.
- **Remediation**: Pass an explicit timeout (e.g. `timeout=TOKEN_TIMEOUT_SECONDS` or `10.0` seconds) to `httplib2.Http()`, matching the outbound timeouts used in `backend/oauth_transport.py`.

### 3.2. `gch/inmemory-ratelimit-diverges-across-replicas`
- **Severity**: Medium (Likelihood: Medium, Impact: Medium)
- **File**: `backend/rate_limit.py:8`, `backend/main.py:230`
- **Vulnerability**: Throttling uses a process-local in-memory token bucket registry.
- **Impact**: When scaling out web replicas in hosted environments behind a round-robin load balancer or tunnel, an abusive client's requests are distributed among replicas, allowing effective throughput to multiply by the replica count.
- **Remediation**: In multi-replica hosted configurations, back rate limit buckets with a shared distributed data store (such as Redis) or enforce aggregate throttling at the reverse proxy/edge layer (Cloudflare / Caddy).

### 3.3. `gch/unpinned-cloudflared-image-tag`
- **Severity**: Low (Likelihood: Low, Impact: Low)
- **File**: `compose.yml:142`
- **Vulnerability**: The edge tunnel container uses `image: cloudflare/cloudflared:latest`, whereas postgres and Caddy use pinned versions (`postgres:16-alpine`, `caddy:2-alpine`).
- **Impact**: Container recreations or redeployments pull whatever image Cloudflare tags as latest, introducing untested or unreviewed binaries into the production edge boundary.
- **Remediation**: Pin `cloudflare/cloudflared` to a specific version tag or immutable SHA256 image digest.

---

## 4. Needs Validation Leads

| Lead ID | Title | Blocker | Recommended Owner Action |
| :--- | :--- | :--- | :--- |
| `gch/edge-header-trust-needs-deployment-check` | Throttle identity depends on edge header handling | Production edge proxy configuration (whether Caddy/Cloudflare strips unverified client-supplied headers) is outside repo source. | Verify at the edge tunnel and reverse proxy firewall that untrusted inbound forwarded IP headers are overwritten, and verify that the origin only accepts traffic from the proxy. |
| `gch/hsts-edge-duplication-needs-check` | HSTS emission depends on edge HTTPS observation | Deployment-specific edge header handling cannot be fully verified from repository static configuration. | Inspect HTTPS responses from the production domain to ensure `Strict-Transport-Security` is present, correctly formatted, and not duplicated between edge and origin. |
| `gch/teacher-role-relies-on-google-membership` | Teacher-role enforcement relies on live Google membership | The authoritative per-course role assignment is determined dynamically by Google Classroom API responses for the caller's credentials. | In an integration staging environment with real Google accounts, test teacher-only routes with student credentials to verify Google-side rejection and 403 handling. |

---

## 5. Coverage Ledger Summary

All 6 attack-surface units defined in `coverage-ledger.json` have been evaluated and closed under Wave 1:
- `availability-abuse` (Denial of Service): `candidate` (2 confirmed findings recorded).
- `client-session-handling` (Cross-site Scripting): `covered` (DOMPurify, React escaping, and CSP headers validated).
- `data-isolation-lifecycle` (Access Control): `covered` (Tenant scoping on all cache, course, and sync queries verified).
- `deployment-configuration` (Cryptography & Secrets): `candidate` (1 confirmed finding recorded).
- `supply-chain-release` (Third-party Code): `covered` (CI dependencies, lockfiles, and container builds checked).
- `web-oauth-session` (Access Control): `covered` (Single-use OAuth states and secure session token lifecycles confirmed).

