# Needs Validation Leads

This document lists candidate security concerns that depend on external deployment facts, live cloud provider behavior, or live Google Classroom account memberships outside the repository checkout.

---

## 1. `gch/edge-header-trust-needs-deployment-check`

### Focus
Forwarded client IP header trust and abuse throttling.

### Context & Evidence
- In `backend/proxy.py:136-137`, the application resolves client IP from `CF-Connecting-IP` or `X-Forwarded-For` only if the immediate TCP peer is in `TRUSTED_PROXIES`.
- In `Caddyfile:30`, Caddy forwards client identity headers to the backend.

### Exact Blocker
Whether the public edge (Cloudflare tunnel / external network firewall) strips or normalizes client-injected headers before traffic reaches Caddy cannot be determined from code alone. If an attacker can directly reach Caddy or the backend bypassing the tunnel, IP spoofing could evade throttling.

### Recommended Owner Validation Plan
1. **Deployment Check**: From an external network client, send requests with forged `CF-Connecting-IP` and `X-Forwarded-For` headers. Inspect backend logs or throttle response headers to ensure the effective identity remains the actual tunnel exit or edge peer.
2. **Network Perimeter Check**: Verify that origin firewall rules reject direct external connections to ports 80/443/8000, accepting traffic strictly via the Cloudflare tunnel daemon.

---

## 2. `gch/hsts-edge-duplication-needs-check`

### Focus
HTTP Strict Transport Security (HSTS) header emission.

### Context & Evidence
- In `backend/main.py:447-450`, the origin FastAPI middleware conditionally adds `Strict-Transport-Security` when HSTS is configured and `external_scheme` is `https`.
- In `backend/proxy.py:86`, external scheme resolution relies on trusted proxy headers.

### Exact Blocker
Whether the production edge (Cloudflare Edge or Caddy) also emits HSTS headers cannot be determined solely from repository files. If both origin and edge add HSTS with conflicting directives, browsers may handle headers unpredictably.

### Recommended Owner Validation Plan
1. **Deployment Check**: Send an HTTPS request to the production hostname and inspect the response headers for duplicated `Strict-Transport-Security` headers.
2. **Configuration Check**: Ensure either the edge or the backend is designated as the sole HSTS issuer.

---

## 3. `gch/teacher-role-relies-on-google-membership`

### Focus
Teacher-only authorization gates across Classroom courses.

### Context & Evidence
- In `backend/api.py:848` and `backend/api.py:863`, teacher routes check the caller's role for the specified course.
- In `backend/api.py:733`, the user's role is obtained directly from the Google Classroom API via the user's OAuth credentials.

### Exact Blocker
The source code correctly relies on Google Classroom's authoritative response for the caller's credentials. Unit tests with mocked responses cannot observe live Google Classroom permission behavior.

### Recommended Owner Validation Plan
1. **Deployment Check**: Using two real Google test accounts enrolled in a Classroom course (one as student, one as teacher), send requests to teacher endpoints with the student session token.
2. **Verify**: Ensure the backend receives non-teacher role from Google and responds with `403 Forbidden`, leaking no student rosters or grading submissions.
