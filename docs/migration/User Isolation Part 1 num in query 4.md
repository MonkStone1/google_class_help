# User Isolation Part 1 num in query 4

**Stage 4 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Introduce the get_current_user dependency, make every query, cache, and data-access path user-scoped, and close IDOR gaps.
- **Depends on:** stages 1-3 must be done (or their decisions recorded)
- **Source prompt sections:** §12, §13, §14, §15, §16  (part 1/2)

---
## 12. User data isolation is a hard security requirement

This is one of the most important parts of the migration.

Every data access path must be filtered by the authenticated user.

A request such as:

```text
GET /api/courses/123
```

must mean:

```text
current session user
        ↓
lookup course 123 belonging to current user
        ↓
return it or 404/403
```

It must never mean:

```text
lookup global Course(id=123)
```

without a user constraint.

Audit every endpoint for IDOR-style vulnerabilities.

Specifically review:

- `/api/courses`
- `/api/courses/{course_id}`
- `/api/courses/{course_id}/coursework`
- `/api/courses/{course_id}/students`
- `/api/courses/{course_id}/grades`
- `/api/courses/{course_id}/coursework/{coursework_id}`
- `/api/courses/{course_id}/coursework/{coursework_id}/submissions`
- `/api/courses/{course_id}/students/{student_id}/grades`
- `/api/assignments`
- `/api/grades`
- `/api/calendar`
- `/api/status`
- `/api/sync`
- `/api/cache`
- all auth/session routes.

Also check indirect lookup paths. A user must not be able to reach another user's coursework by guessing its Google ID.

Prefer repository/service functions that receive an authenticated `user_id` and enforce ownership centrally instead of repeating fragile checks in every route.

---

## 13. Introduce an authenticated-user dependency

Create a reusable FastAPI dependency such as:

```python
current_user = Depends(get_current_user)
```

or an equivalent design.

The dependency should:

1. read the secure application session cookie;
2. validate the session;
3. load the local User record;
4. reject missing/expired/revoked sessions;
5. expose the authenticated user to route handlers.

Do not make route handlers trust a frontend-supplied `user_id`.

For example, prefer:

```python
@router.get("/courses")
def courses(current_user: User = Depends(get_current_user)):
    ...
```

rather than:

```python
@router.get("/courses")
def courses(user_id: int):
    ...
```

---

## 14. Application auth and Google auth must be separate layers

Keep these concerns separate:

```text
Authentication layer
    ↓
Who is the current local application user?

Google credential layer
    ↓
What Google OAuth credentials belong to that user?

Classroom service layer
    ↓
Use those credentials to call Google Classroom
```

Do not let `classroom_api.py` decide who the local browser user is.

Do not let React hold a Google token.

Do not make Classroom routes accept a token supplied by the browser.

---

## 15. Refactor the existing Google credential functions

The current functions such as:

- `load_credentials()`
- `get_valid_credentials()`
- `_save_credentials()`
- `logout()`

are process/global-user oriented.

Refactor them into user-scoped operations.

Conceptual interface:

```python
get_google_credentials(user_id)
save_google_credentials(user_id, credentials)
refresh_google_credentials(user_id)
delete_google_credentials(user_id)
```

The refresh lock must also become user-aware.

Current global refresh serialization is suitable for one user. On a multi-user server, do not allow one user's refresh traffic to block all users unnecessarily.

A per-user refresh lock or database-level coordination mechanism is preferable.

The implementation should still prevent duplicate concurrent refresh requests for the same user's token.

---

## 16. Refactor the current global login state

The existing `_login_state` is a global dictionary and is only safe because the current desktop app has one user.

For a hosted web app, do not use one global:

```python
{
    "in_progress": ...,
    "error": ...,
    "auth_url": ...,
}
```

for everyone.

Login attempts need to be correlated to the initiating browser/session.

Do not allow:

```text
User A starts OAuth
User B polls /api/auth/status
User B sees User A's OAuth URL/state/error
```

Use a short-lived login transaction keyed to a secure browser cookie or server-side transaction ID.

---

