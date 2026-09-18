# Teacher Mode and API Surface num in query 6

**Stage 6 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Keep teacher mode as a per-course role, preserve business semantics, and rework the API surface carefully.
- **Depends on:** stages 1-5 must be done (or their decisions recorded)
- **Source prompt sections:** §21, §22, §23, §24, §25, §65

---
## 21. Teacher mode must remain per-course and per-user

The existing teacher mode correctly recognizes that one Google account may be a teacher in some courses and a student in others.

Preserve this behavior.

The hosted migration must not collapse the role to a single account-level boolean.

The correct conceptual model remains:

```text
User
 ├── Course A → STUDENT
 ├── Course B → TEACHER
 └── Course C → STUDENT
```

Teacher-mode data is also user-owned.

Do not let another user access:

- teacher rosters;
- submissions of students in that teacher's courses;
- grades;
- course statistics;
- teacher-only coursework.

All teacher endpoints must enforce both:

```text
current authenticated user
AND
course role == TEACHER
```

The existing read-only Classroom scopes should be preserved unless the Google API implementation requires a documented adjustment.

Current intended read-only scope set:

```text
https://www.googleapis.com/auth/classroom.courses.readonly
https://www.googleapis.com/auth/classroom.student-submissions.me.readonly
https://www.googleapis.com/auth/classroom.student-submissions.students.readonly
https://www.googleapis.com/auth/classroom.rosters.readonly
```

Do not add write scopes merely for convenience.

Do not request student email access unless the feature genuinely requires it and the privacy/verification implications have been reviewed.

---

## 22. Preserve the important semantic rules

The existing project contains important business semantics. Preserve them during migration.

Examples:

- Missing grade is not zero.
- Student and teacher assignment views are different.
- Teacher aggregates must not be interpreted as the teacher's personal submission.
- Archived courses are filtered appropriately.
- Submission states remain explicit.
- `not_submitted`, `turned_in`, `returned`, and `graded` semantics should not regress.
- Derived percentages remain consistent.
- Client-side calendar/search/filter behavior should keep working unless moved server-side for a concrete reason.

Do not silently change business meaning while performing infrastructure migration.

---

## 23. Rework the API surface carefully

The frontend currently uses `/api/...` and should continue to do so.

The API may gain routes such as:

```text
GET  /api/auth/status
POST /api/auth/login
GET  /api/auth/callback
POST /api/auth/logout

GET  /api/me

GET  /api/courses
GET  /api/courses/{course_id}
GET  /api/courses/{course_id}/coursework
GET  /api/courses/{course_id}/students
GET  /api/courses/{course_id}/grades
GET  /api/courses/{course_id}/coursework/{coursework_id}
GET  /api/courses/{course_id}/coursework/{coursework_id}/submissions
GET  /api/courses/{course_id}/students/{student_id}/grades

GET  /api/assignments
GET  /api/grades
GET  /api/calendar
GET  /api/status
POST /api/sync
```

Adapt the exact set to the current implementation rather than duplicating routes.

The backend should return `401 Unauthorized` when there is no valid application session.

Use `403 Forbidden` when the user is authenticated but lacks permission for the requested resource (for example, a student opening teacher-only course data).

Use `404 Not Found` when appropriate for resources that do not belong to the current user, depending on the desired information-disclosure policy. Avoid leaking whether another user's resource exists.

---

## 24. Rework `/api/auth/status`

The hosted auth status should describe the current browser's application session, not a global server login.

A reasonable response shape:

```json
{
  "authenticated": true,
  "user": {
    "id": "local-id",
    "name": "...",
    "email": "..."
  }
}
```

Do not include:

- access tokens;
- refresh tokens;
- client secret;
- OAuth authorization code;
- full Google credential object.

The frontend should not need to know any Google OAuth internals beyond whether login is required and perhaps a display name/email.

---

## 25. Login UX changes

The current local application can automatically open a browser window and expose an OAuth URL in its settings.

For the hosted web application, the desired UX is simpler:

```text
User opens site
    ↓
Not authenticated
    ↓
"Sign in with Google"
    ↓
Google consent
    ↓
redirect back
    ↓
dashboard
```

Do not expose loopback callback URLs in the hosted UI.

Do not require copying authorization URLs from logs.

The desktop OAuth UX should remain separate from the web OAuth UX.

---

## 65. Explicitly review teacher-mode API volume

Teacher mode can generate significantly more Google Classroom requests than the student view because it may load:

- all coursework;
- roster;
- all student submissions;
- related teacher/course data.

Keep the existing parallel staged approach but add:

- user-level concurrency limits;
- global limits;
- backoff;
- observability;
- pagination correctness.

Do not assume one teacher sync is representative of server-wide load.

---

