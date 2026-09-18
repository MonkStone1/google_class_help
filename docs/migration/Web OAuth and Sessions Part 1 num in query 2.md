# Web OAuth and Sessions Part 1 num in query 2

**Stage 2 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Replace desktop loopback OAuth with a server-owned web OAuth flow; introduce users / sessions / oauth_tokens and secret-management rules.
- **Depends on:** stages 1-1 must be done (or their decisions recorded)
- **Source prompt sections:** §4, §5, §6, §7  (part 1/2)

---
## 4. Hard architectural decision: web OAuth instead of desktop OAuth

The hosted version must **not** use the current desktop loopback OAuth flow as its primary authentication flow.

The existing desktop OAuth flow was intentionally designed for a native application and includes a local callback server on `127.0.0.1`. That remains valid for the desktop build, but the hosted web application needs a proper web OAuth flow.

Use a **separate Google OAuth client of type Web application** for the hosted service.

Recommended Google Cloud arrangement:

```text
One Google Cloud project
├── Desktop OAuth client
│     └── existing local/Nuitka application
│
└── Web OAuth client
      └── hosted Google Class Help
```

Do not mix the redirect URI assumptions between the two clients.

The hosted application should use a redirect URI such as:

```text
https://monkstonecor.pp.ua/api/auth/callback
```

The exact path may differ if the implementation has a better route, but it must be HTTPS in production and must exactly match the Google Cloud Console configuration.

The web client secret is a real server-side secret and must never be shipped to the browser, embedded into React assets, or committed to Git.

---

## 5. Hosted OAuth flow

Implement a secure server-owned web OAuth flow.

Desired flow:

```text
Browser
  ↓
GET/POST /api/auth/login
  ↓
FastAPI generates OAuth authorization URL
  ↓
Browser redirects to Google
  ↓
Google consent/login
  ↓
Google redirects to
https://monkstonecor.pp.ua/api/auth/callback
  ↓
FastAPI validates OAuth state
  ↓
FastAPI exchanges authorization code
  ↓
FastAPI obtains Google credentials
  ↓
FastAPI identifies the Google user
  ↓
Create/find local user record
  ↓
Persist encrypted/protected token data server-side
  ↓
Create authenticated application session
  ↓
Redirect browser back to the dashboard
```

Important security requirements:

- Generate a cryptographically random OAuth `state` for every login attempt.
- Store state server-side or bind it securely to the initiating browser session.
- Reject state mismatches.
- Do not trust a user ID supplied by the frontend.
- Do not accept `user_id` as an authorization mechanism.
- Do not let the frontend select another local user by changing an ID in a URL.
- Use an application session after Google login.
- Prefer an opaque random session identifier stored in an `HttpOnly`, `Secure`, `SameSite` cookie.
- Do not store the application session token in localStorage if it can be avoided.
- Do not place Google access tokens or refresh tokens into frontend JSON responses.
- Do not place refresh tokens in browser cookies.
- Never log access tokens, refresh tokens, client secrets, authorization codes, or raw credential JSON.

---

## 6. Decide and document the session architecture

Use a server-side session model.

Recommended schema:

```text
users
sessions
oauth_tokens
```

Conceptually:

```text
users
-----
id
provider                 # google
provider_subject         # stable Google subject/user id
email                    # optional/local profile field
display_name
created_at
updated_at
last_login_at
is_active

sessions
--------
id / session_token_hash
user_id
created_at
expires_at
last_seen_at
revoked_at
user_agent              # optional, only if useful
ip_hash                  # optional; do not store raw IP without a reason

oauth_tokens
------------
user_id
access_token
refresh_token
token_uri
scopes
expires_at
created_at
updated_at
```

The exact schema can vary, but the following relationship must exist:

```text
Google account
      ↓
local User
      ↓
OAuth credentials
      ↓
session(s)
```

A user session is an application authentication concept. A Google OAuth token is a credential used by the backend when talking to Google APIs. Do not conflate the two.

Sessions should be revocable independently of Google tokens.

Logging out should revoke the application session. Decide whether the UI logout should also revoke/delete stored Google credentials. For the first hosted implementation, prefer:

- revoke the current application session;
- do not necessarily revoke the Google grant at Google;
- retain the refresh token server-side so the next login/session can be efficient if the application's security model permits it.

Document the decision and make sure the implementation matches it. A stronger privacy-oriented design may delete local OAuth credentials on explicit account removal.

---

## 7. User identity: use Google's stable subject identifier

Do not identify users solely by email.

Use Google's stable OpenID/OAuth subject identifier as the primary external identity key, or the equivalent stable Google user ID returned by the chosen Google identity endpoint.

Email can change. The stable subject is the identity link.

The implementation must correctly handle:

- first login;
- returning login;
- same Google account on a second browser;
- logout/login as a different Google account;
- two users with the same display name;
- changed email address;
- revoked Google authorization;
- expired access token with valid refresh token;
- invalid refresh token;
- deleted/deactivated local user.

---

