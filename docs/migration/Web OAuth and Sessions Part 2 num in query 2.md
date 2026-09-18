# Web OAuth and Sessions Part 2 num in query 2

**Stage 2 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Replace desktop loopback OAuth with a server-owned web OAuth flow; introduce users / sessions / oauth_tokens and secret-management rules.
- **Depends on:** stages 1-1 must be done (or their decisions recorded)
- **Source prompt sections:** §8 "Replace the single global token file", §9 "Secret management"  (part 2/2)

---
## 8. Replace the single global token file

The current project has a single `TOKEN_FILE` and functions that load/save one credential set.

That design must be replaced for the hosted service.

Never do this in the hosted multi-user process:

```python
TOKEN_FILE = DATA_DIR / "token.json"
```

for all users.

Do not solve multi-user support by creating:

```text
users/user1/token.json
users/user2/token.json
```

unless there is a very strong reason. Database-backed credentials are easier to transactionally associate with a user, revoke, rotate, and secure.

Recommended approach:

- store OAuth credentials in PostgreSQL;
- encrypt the credential fields at rest using a server-side application encryption key if practical;
- keep the encryption key outside the database and outside source control;
- load/decrypt credentials only inside backend memory when needed;
- never return raw credentials through an API endpoint.

If implementing application-level encryption, use a standard authenticated encryption construction/library. Do not invent custom XOR/base64 encryption.

The existing desktop `embedded_secrets.py` / XOR obfuscation mechanism is not an acceptable security mechanism for server secrets.

---

## 9. Secret management

Separate secrets into categories.

### Public client identifier

The Google OAuth `client_id` is not a security boundary and may be present in frontend configuration when appropriate, but keep the web OAuth implementation server-owned anyway.

### Server-only secrets

These must remain on the server:

- Google web OAuth client secret;
- session signing/encryption key, if using signed sessions;
- OAuth-token encryption key, if used;
- PostgreSQL password/connection credentials;
- any future server API keys;
- any SMTP credentials if email is later added.

Inject them through environment variables or the hosting platform's secret mechanism.

Never:

- commit them;
- put them in React source;
- put them into `frontend/dist`;
- put them into logs;
- put them into GitHub Pages;
- put them into Docker image layers when avoidable;
- put them into a public `.env` file.

Provide a safe `.env.example` with placeholders only.

---

