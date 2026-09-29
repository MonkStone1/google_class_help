# Detailed Confirmed Findings

This document provides exhaustive technical evidence, reproduction paths, and remediation guidance for each confirmed vulnerability identified during the security audit.

---

## 1. `gch/turnstile-siteverify-no-timeout`

### Summary
- **Title**: Missing outbound socket timeout on Cloudflare Turnstile siteverify
- **Severity**: Medium (Likelihood: Medium, Impact: Medium)
- **CWE**: CWE-400 (Uncontrolled Resource Consumption)
- **Boundary**: Anonymous low-trust request versus shared service worker pool

### Description
In `backend/hosted_auth.py`, the Turnstile verification path performs an outbound HTTPS POST to Cloudflare's `siteverify` endpoint without specifying a socket timeout. The endpoint is reachable prior to authentication via `POST /api/auth/login/start`. When the remote service is slow or unresponsive, the request worker remains blocked indefinitely, allowing a small volume of concurrent requests to starve the application's thread pool.

### Trace & Evidence
1. **Entrypoint**: `backend/hosted_auth.py:473` (`login_start`) receives unauthenticated client POST requests with Turnstile token payloads.
2. **Propagation**: `backend/hosted_auth.py:365` constructs `httplib2.Http()` without a timeout argument.
3. **Sink**: `backend/hosted_auth.py:366` invokes `http.request(TURNSTILE_VERIFY_URL, method="POST", ...)` without an outbound deadline.
4. **Contrast**: `backend/oauth_transport.py:106` uses an explicit 30-second timeout (`TOKEN_TIMEOUT_SECONDS = 30.0`), demonstrating that outbound network calls in this service are expected to have socket timeouts.

### Local Reproduction
- **Instructions**:
  1. Inspect `backend/hosted_auth.py` around line 365.
  2. Simulate or trace an outbound call to `siteverify` where socket response is suspended.
  3. Notice that `httplib2.Http()` defaults to the system default socket timeout (which is infinite / none on Python unless set globally).
  4. The worker remains blocked until the OS-level TCP connection times out (often minutes).

### Remediation
Update `backend/hosted_auth.py` to specify a socket timeout:
```python
# backend/hosted_auth.py
http = httplib2.Http(timeout=10.0)
```

---

## 2. `gch/inmemory-ratelimit-diverges-across-replicas`

### Summary
- **Title**: In-memory rate limiting diverges across multiple web replicas
- **Severity**: Medium (Likelihood: Medium, Impact: Medium)
- **CWE**: CWE-770 (Allocation of Resources Without Limits or Throttling)
- **Boundary**: Anonymous low-trust request versus shared service and spend

### Description
Request throttling in `backend/rate_limit.py` uses an in-memory token bucket (`RateLimiter`) instance local to the running Python process. When deployed with multiple web replicas (e.g., multiple container instances behind a round-robin load balancer or tunnel), each replica maintains its own state. An abusive client can spread requests across replicas, multiplying aggregate allowed request volume by the replica count.

### Trace & Evidence
1. **Entrypoint**: `backend/main.py:230` instantiates a process-local rate limit registry.
2. **Propagation**: `backend/rate_limit.py:8` and `backend/rate_limit.py:4` manage token buckets entirely in memory (`self.limits = {}`).
3. **Sink**: Requests arriving at different replicas are throttled independently; no synchronization or shared cache coordinates bucket consumption.

### Local Reproduction
- **Instructions**:
  1. Start two distinct backend process instances simulating two replicas behind a load balancer.
  2. Send requests to replica A up to the rate limit threshold (e.g., 5 requests for login initiation).
  3. Send requests to replica B using the same client IP identity.
  4. Observe that replica B accepts the requests because its internal registry is isolated from replica A.

### Remediation
For multi-replica deployments:
1. Back rate limiting with a shared key-value store such as Redis.
2. Alternatively, enforce strict rate limiting at the reverse proxy/edge tier (Cloudflare Turnstile / Caddy `rate_limit` directive) before traffic hits the application container replicas.

---

## 3. `gch/unpinned-cloudflared-image-tag`

### Summary
- **Title**: Unpinned `latest` image tag for `cloudflared` service
- **Severity**: Low (Likelihood: Low, Impact: Low)
- **CWE**: CWE-829 (Inclusion of Functionality from Untrusted Control Sphere)
- **Boundary**: Internet deployment input versus container workload integrity

### Description
In `compose.yml`, the `cloudflared` tunnel container is configured with `image: cloudflare/cloudflared:latest`. Unlike `postgres` (`postgres:16-alpine`) and `caddy` (`caddy:2-alpine`), `latest` is mutable. Rebuilding or pulling images during redeployment can silently fetch a new upstream binary release without code review or version tracking in the repository.

### Trace & Evidence
1. `compose.yml:142` uses `image: cloudflare/cloudflared:latest`.
2. `compose.yml:21` and `compose.yml:118` pin `postgres:16-alpine` and `caddy:2-alpine`.

### Remediation
Pin the `cloudflared` container image to a specific version or digest in `compose.yml`:
```yaml
cloudflared:
  image: cloudflare/cloudflared:2026.9.1  # Pin to reviewed release
```
