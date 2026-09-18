# User Isolation Part 2 num in query 4

**Stage 4 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Introduce the get_current_user dependency, make every query, cache, and data-access path user-scoped, and close IDOR gaps.
- **Depends on:** stages 1-3 must be done (or their decisions recorded)
- **Source prompt sections:** §17 "Profile caching must become user-scoped", §67 "API response ownership"  (part 2/2)

---
## 17. Profile caching must become user-scoped

The current profile cache is global:

```python
_profile_cache
```

This is unsafe when multiple users are logged in.

Replace it with a user-scoped cache, database value, or a short-lived cache keyed by local user ID.

At minimum:

```text
user_id -> profile cache
```

Never allow User B to receive User A's cached name/email.

---

## 67. API response ownership

Every API response containing user data must have an obvious ownership path.

Examples:

```text
Assignment
  → Course
    → User
```

or

```text
CourseWorkSubmission
  → CourseWork
  → Course
  → User
```

Avoid query patterns that can accidentally join across users.

Use explicit SQLAlchemy filters.

---

