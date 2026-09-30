# Desktop and Hosted Coexistence Part 2 num in query 8

**Stage 8 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Split desktop and hosted startup/auth paths, choose the static-asset strategy, and enable HTTPS, cookies, CSRF, and security headers.
- **Depends on:** stages 1-7 must be done (or their decisions recorded)
- **Source prompt sections:** §48, §49, §50, §74, §75, §76  (part 2/2)

---
## 48. Security headers

Configure appropriate production headers, either in Caddy or FastAPI, including as appropriate:

- `Strict-Transport-Security` after HTTPS is stable;
- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy` with a privacy-conscious value;
- `X-Frame-Options` or an appropriate CSP `frame-ancestors` policy;
- a Content Security Policy appropriate for the actual React bundle and Google OAuth redirects.

Do not add a CSP that breaks the app without testing it.

Document any external origins required by the frontend.

---

## 49. Frontend security review

Search the built frontend and source tree for accidental secrets.

Check that no production build contains:

- client secret;
- PostgreSQL credentials;
- session secret;
- OAuth token;
- refresh token;
- internal hostnames that should not be public;
- development `.env` values.

Remember that anything in `frontend/dist` is public.

---

## 50. Google OAuth verification / branding compatibility

The hosted app is intended to be a public web service and already has a public domain planned for its privacy/terms/branding pages.

Ensure the implementation supports these production OAuth requirements:

```text
https://classroomhelp.pp.ua/
https://classroomhelp.pp.ua/privacy
https://classroomhelp.pp.ua/terms
```

The exact page paths may be different, but there must be publicly accessible pages for the information Google requires.

The OAuth branding and privacy URLs must match the actual hosted service.

Do not put the hosted OAuth client secret in GitHub Pages or any public static hosting.

---

## 74. Keep current desktop production support intact unless intentionally removed

The repository already contains:

- Nuitka build decisions;
- Windows launcher;
- `path_config.py` compiled-build logic;
- embedded OAuth client obfuscation;
- local loopback OAuth implementation;
- tray/single-instance functionality.

Do not destroy these features merely to create the hosted version.

Refactor shared code so the desktop and hosted targets coexist safely.

The hosted web deployment should not import Windows-only desktop modules.

---

## 75. Desktop OAuth and hosted OAuth must use separate redirect configuration

Desktop:

```text
loopback 127.0.0.1 + random/free local port
```

Hosted:

```text
https://classroomhelp.pp.ua/api/auth/callback
```

Do not dynamically reuse one redirect URI implementation for both modes unless the code clearly handles both paths without weakening security.

---

## 76. Do not expose the hosted OAuth client secret through Nuitka or React

The desktop embedded secret mechanism and hosted server secret mechanism are different security domains.

For desktop:

- the client secret is not a true security boundary;
- obfuscation is only a casual-observation measure.

For hosted:

- the web client secret is server-only;
- it must never be in the browser;
- it must never be in public repository artifacts.

Document this distinction.

---

