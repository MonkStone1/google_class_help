# PostgreSQL and Migrations num in query 3

**Stage 3 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Move from SQLite to PostgreSQL, introduce Alembic, and build a user-scoped schema with correct uniqueness constraints.
- **Depends on:** stages 1-2 must be done (or their decisions recorded)
- **Source prompt sections:** §10, §11, §69, §71

---
## 10. Database migration: SQLite → PostgreSQL

The hosted version should use PostgreSQL.

Do not continue to use the local SQLite cache as the production primary datastore.

The existing SQLAlchemy models can be reused conceptually, but they are currently designed around a single authenticated user. That must change.

Current examples include:

- `Course`
- `CourseWork`
- `StudentSubmission`
- `CourseRole`
- `CourseStudent`
- `CourseWorkSubmission`
- `SyncState`

The key architectural change is user ownership.

At minimum, cache records that can differ by Google account must become user-scoped.

A safe conceptual model is:

```text
users
  │
  ├── courses
  │      ├── coursework
  │      ├── course_roles
  │      ├── course_students
  │      ├── student_submissions
  │      └── coursework_submissions
  │
  ├── oauth_tokens
  └── sessions
```

Possible columns:

```text
courses
-------
id                     # local PK may be composite or internal integer
user_id                # FK to users
provider_course_id     # Google Classroom course id
...
```

For Coursework:

```text
coursework
----------
id
user_id
course_id
provider_coursework_id
...
```

For student submissions:

```text
submissions
-----------
user_id
course_id
coursework_id
...
```

For teacher submissions:

```text
coursework_submissions
----------------------
user_id
course_id
coursework_id
student_id
...
```

For teacher course roles:

```text
course_roles
------------
user_id
course_id
role
```

For course students:

```text
course_students
---------------
user_id
course_id
student_id
...
```

Do not blindly add `user_id` everywhere without reviewing primary keys and uniqueness constraints.

A Google Classroom course ID may be identical across different authenticated users. The cache must never assume global uniqueness for user-specific records.

Use uniqueness constraints appropriate to the scope, for example:

```text
(user_id, provider_course_id)
(user_id, provider_coursework_id)
(user_id, course_id, coursework_id)
(user_id, course_id, coursework_id, student_id)
```

The exact schema must be based on the existing foreign-key relationships and actual query patterns.

---

## 11. Add proper database migrations

Do not rely on `Base.metadata.create_all()` as the production schema migration system.

Introduce a real migration mechanism, preferably Alembic, for PostgreSQL.

Required migration path:

1. Fresh installation creates the full schema.
2. Existing development databases can be recreated or migrated in a controlled way.
3. Production migrations are versioned.
4. Destructive schema changes require explicit review.
5. No production deployment should depend on silently creating missing columns.

A local legacy SQLite database does not need to be migrated automatically unless there is a concrete requirement. If migration from existing user data is implemented, provide a deliberate import/migration script rather than guessing.

---

## 69. PostgreSQL compatibility details

Review SQLite-specific assumptions such as:

- SQLite-specific SQL;
- implicit transaction behavior;
- JSON behavior;
- Boolean behavior;
- datetime semantics;
- `ON CONFLICT` syntax;
- case sensitivity;
- null handling;
- connection/thread assumptions.

Keep SQLAlchemy abstractions wherever possible.

Use PostgreSQL-native types only when they provide a concrete benefit.

---

## 71. Production database credentials and least privilege

Create a PostgreSQL role dedicated to the application.

Do not run the application as the PostgreSQL superuser.

Do not expose PostgreSQL admin credentials to the web container.

Use separate roles for migration/administration if practical.

---

