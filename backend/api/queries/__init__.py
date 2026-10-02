"""Read side of the Classroom cache, one module per resource (ADR-0039).

These functions answer questions about rows a user owns. They deliberately
have NO ``fastapi`` import and never raise ``HTTPException``: a missing row is
``None``, a forbidden course is a role string, and translating either into 404
or 403 is ``api/guards.py``'s job (§23). That split is what makes the queries
reusable and unit-testable without spinning up an app, and it is what
``tests/test_backend_structure.py`` will enforce.

User scoping is structural: every function takes the ``owner_id`` of the cache
owner (§12/§13), and every join equates ``user_id`` on both sides so a
same-named Google id of another user can never join in (§67).

Import order matters and is one-directional:

    queries.courses  ←  queries.assignments  ←  queries.teacher

``assignments`` needs the course helpers, ``courses`` needs nothing from
``assignments``. Nothing imports back up, so there is no cycle to break.
"""

from api.queries import assignments, courses, dashboard, teacher

__all__ = ["assignments", "course_role", "courses", "dashboard", "teacher"]


def course_role(db, owner_id: int, course):
    """Role of the cache owner in a course ("TEACHER"/"STUDENT")."""
    return teacher.course_role(db, owner_id, course)