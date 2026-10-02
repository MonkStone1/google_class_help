"""HTTP guards: the only place a cache fact becomes a 404 or a 403.

``api/queries/*`` answers questions about the cache and returns ``None`` when
a row is absent, so it stays free of ``fastapi`` and can be reused and unit
tested without an HTTP layer. These helpers are the translation step: "the
owner has no such course" and "the owner does not teach this course" are not
cache facts but API answers, so they live here instead (§23 status codes).

``course_role`` itself is NOT here — it is an ordinary cache read and stays in
``api/queries/teacher.py``; only the raising wrappers are here.
"""

# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api import queries
from db.models.classroom import Course


def _get_course(db: Session, owner_id: int, course_id: str) -> Course:
    """The owner's course by id; ARCHIVED and missing courses are 404."""
    course = db.get(Course, (owner_id, course_id))
    if course is None or course.course_state == "ARCHIVED":
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


def _course_role(db: Session, owner_id: int, course: Course) -> str:
    """Role of the cache owner in this course ("TEACHER"/"STUDENT")."""
    return queries.course_role(db, owner_id, course)


def _require_teacher(db: Session, owner_id: int, course: Course) -> None:
    """Teacher-only endpoints must never be reachable from a student course."""
    if _course_role(db, owner_id, course) != "TEACHER":
        raise HTTPException(
            status_code=403,
            detail="This course is not taught by the signed-in user.",
        )