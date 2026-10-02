"""Cache reads the two-role tables hide, and the destructive purges (§2.3).

``get_submission`` exists because one fact lives in two tables (ADR-0003): a
teacher course keeps per-student rows in CourseWorkSubmission, the student
route keeps the owner's own row in StudentSubmission. The role picks the table
here so callers never branch on it themselves.

The purges are separate because they are the only operations in the cache layer
that DELETE: they exist for archived/unenrolled courses and for the confirmed
"clear my cache" action, and being in one module makes the blast radius of a
mistaken scope obvious at a glance.
"""

import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from db.models.classroom import (
    Course,
    CourseRole,
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
    StudentSubmission,
    SyncStatus,
)

logger = logging.getLogger(__name__)

SubmissionRow = CourseWorkSubmission | StudentSubmission

# ------------------------------------------------------- unified access §2.3


def get_submission(
    db: Session,
    user_id: int,
    course_id: str,
    coursework_id: str,
    student_id: str,
    *,
    is_teacher: bool,
) -> SubmissionRow | None:
    """One access point to a student's submission (review §2.3).

    The same fact lives in two tables (ADR-0003 cache compatibility): a
    teacher course keeps per-student rows in CourseWorkSubmission, the
    student route keeps the user's own row in StudentSubmission. The role
    picks the table here, so callers never branch on it themselves. Both
    lookups are scoped to the cache owner (user_id) — stage 3.
    """
    if is_teacher:
        return db.get(
            CourseWorkSubmission, (user_id, course_id, coursework_id, student_id)
        )
    return db.get(StudentSubmission, (user_id, course_id, coursework_id))


# ------------------------------------------------------------------ purging


def _purge_course(db: Session, user_id: int, course_id: str) -> None:
    """Remove one owner's course and its cached rows (archived/gone courses).

    SQLite runs with PRAGMA foreign_keys=ON (database.py) and PostgreSQL
    always enforces FKs, so the ondelete=CASCADE rules on every child table
    do the work — one delete instead of five hand-written ones (review
    §1.6). The composite key (user_id, course_id) keeps the delete inside
    one user's cache (audit Y3).
    """
    stale = db.get(Course, (user_id, course_id))
    if stale is None:
        return
    # A parameterized delete() statement, not an ORM instance delete: with
    # enforced foreign keys the DB cascades every child row itself.
    db.execute(delete(Course).where(Course.user_id == user_id, Course.id == course_id))
    db.commit()


def _purge_stale_courses(db: Session, user_id: int, active_ids: set[str]) -> None:
    """Remove THIS owner's cached courses the Classroom API no longer returns.

    Covers ARCHIVED courses as well as courses the user left (unenrolled) or
    that were deleted in Google. The API list call has already succeeded at
    this point, so a missing id is authoritative rather than an error. The
    user_id scope is essential (audit Y3): another user's identical course
    id must survive this purge untouched.
    """
    cached_ids = [
        row[0] for row in db.query(Course.id).filter(Course.user_id == user_id).all()
    ]
    for course_id in cached_ids:
        if course_id not in active_ids:
            _purge_course(db, user_id, course_id)


def reset_cache(db: Session, user_id: int) -> None:
    """Delete all cached Classroom data of one user (destructive, confirmed).

    Scoped to the calling user (migration stage 3 groundwork for §10/§12):
    deleting every table's rows regardless of owner would erase other
    users' caches. Explicit statements per table (no loop variable passed
    to delete()): the table set is fixed at compile time.
    """
    db.execute(
        delete(CourseWorkSubmission).where(CourseWorkSubmission.user_id == user_id)
    )
    db.execute(delete(CourseStudent).where(CourseStudent.user_id == user_id))
    db.execute(delete(CourseRole).where(CourseRole.user_id == user_id))
    db.execute(delete(StudentSubmission).where(StudentSubmission.user_id == user_id))
    db.execute(delete(CourseWork).where(CourseWork.user_id == user_id))
    db.execute(delete(Course).where(Course.user_id == user_id))
    db.execute(delete(SyncStatus).where(SyncStatus.user_id == user_id))
    db.commit()
