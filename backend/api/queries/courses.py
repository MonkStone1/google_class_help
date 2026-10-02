"""Course reads: cached courses, the role map and the per-course aggregates.

``_role_map`` and the two course lookups live here rather than in
``assignments.py`` because they are keyed by course, and because
``assignments`` already depends on this module — keeping the direction
one-way is what stops an import cycle.
"""

# ruff: noqa: DTZ005
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004);
#       due dates arrive from Classroom without a timezone.

from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from grading import SUBMITTED_STATES
from models import (
    Course,
    CourseRole,
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
    StudentSubmission,
)
from schemas import CourseOut

# ------------------------------------------------------------ derived SQL


def _role_map(db: Session, owner_id: int) -> dict[str, str]:
    """course_id → role of the cache owner ("TEACHER"/"STUDENT").

    Roles live in their own table so an older cache file keeps working
    (ADR-0003/0017); courses synced before teacher mode default to STUDENT.
    Scoped to the owner's rows (stage 3).
    """
    return {
        row.course_id: row.role
        for row in db.query(CourseRole).filter_by(user_id=owner_id).all()
    }


def _all_courses(db: Session, owner_id: int) -> dict[str, Course]:
    """Every cached course of the owner, keyed by id, with NO state filter.

    The archived-course rule is deliberately not applied here: the callers need
    two different ones and they disagree on a NULL ``course_state`` — the
    coursework listing keeps it, the per-course rollup in ``grades`` has always
    dropped it. Filtering in SQL here would silently pick a winner and change
    one of the two responses.
    """
    return {c.id: c for c in db.query(Course).filter_by(user_id=owner_id).all()}


def _active_courses(db: Session, owner_id: int) -> dict[str, Course]:
    """Non-archived courses of the owner, filtered Python-side (ADR-0003).

    Python-side, not SQL: ``None != "ARCHIVED"`` is True, so a course whose
    ``course_state`` is NULL is kept. That is the long-standing behaviour of
    every endpoint that lists coursework.
    """
    return {
        course_id: course
        for course_id, course in _all_courses(db, owner_id).items()
        if course.course_state != "ARCHIVED"
    }


def _course_stats_sql(db: Session, owner_id: int) -> dict[str, CourseOut]:
    """Per-course aggregates computed in SQL (review §2.1).

    Replaces the old approach of loading every coursework/submission row
    into Python and filtering with list comprehensions on every request.
    Student and teacher counters are computed in two separate grouped
    queries: a course has rows in exactly one of the two submission tables,
    so a single join of both would multiply rows. Student averages are
    mean-of-assignments, the same formula the Python code used; the teacher
    average is the mean over all class submissions (previously the mean of
    per-assignment means — the per-submission weighting is the fairer one).

    Scoped to the owner's rows, and every join equates ``user_id`` on both
    sides (§67): identical Google ids of another user must never join in.
    """
    now = datetime.now()
    own_pending = func.coalesce(StudentSubmission.state.not_in(SUBMITTED_STATES), True)
    own_rows = db.execute(
        select(
            Course.id,
            func.count(CourseWork.id).label("total"),
            func.coalesce(func.sum(case((own_pending, 1), else_=0)), 0).label("todo"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                CourseWork.due_at.is_not(None),
                                CourseWork.due_at < now,
                                own_pending,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("overdue"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            StudentSubmission.assigned_points.is_not(None),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("graded"),
            func.avg(
                case(
                    (
                        and_(
                            StudentSubmission.assigned_points.is_not(None),
                            CourseWork.max_points.is_not(None),
                            CourseWork.max_points > 0,
                        ),
                        StudentSubmission.assigned_points
                        / CourseWork.max_points
                        * 100,
                    ),
                    else_=None,
                )
            ).label("average"),
        )
        .outerjoin(
            CourseWork,
            and_(
                CourseWork.user_id == Course.user_id,
                CourseWork.course_id == Course.id,
            ),
        )
        .outerjoin(
            StudentSubmission,
            and_(
                StudentSubmission.user_id == CourseWork.user_id,
                StudentSubmission.coursework_id == CourseWork.id,
            ),
        )
        .filter(Course.user_id == owner_id, Course.course_state != "ARCHIVED")
        .group_by(Course.id)
    ).all()
    teacher_rows = db.execute(
        select(
            Course.id,
            func.coalesce(
                func.sum(
                    case(
                        (CourseWorkSubmission.state.in_(SUBMITTED_STATES), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("submitted"),
            func.coalesce(
                func.sum(
                    case(
                        (CourseWorkSubmission.assigned_points.is_not(None), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("graded"),
            func.avg(
                case(
                    (
                        and_(
                            CourseWorkSubmission.assigned_points.is_not(None),
                            CourseWork.max_points.is_not(None),
                            CourseWork.max_points > 0,
                        ),
                        CourseWorkSubmission.assigned_points
                        / CourseWork.max_points
                        * 100,
                    ),
                    else_=None,
                )
            ).label("average"),
        )
        .outerjoin(
            CourseWork,
            and_(
                CourseWork.user_id == Course.user_id,
                CourseWork.course_id == Course.id,
            ),
        )
        .outerjoin(
            CourseWorkSubmission,
            and_(
                CourseWorkSubmission.user_id == CourseWork.user_id,
                CourseWorkSubmission.coursework_id == CourseWork.id,
            ),
        )
        .filter(Course.user_id == owner_id, Course.course_state != "ARCHIVED")
        .group_by(Course.id)
    ).all()
    roles = _role_map(db, owner_id)
    roster_counts = {
        course_id: count
        for course_id, count in db.query(
            CourseStudent.course_id, func.count(CourseStudent.student_id)
        )
        .filter_by(user_id=owner_id)
        .group_by(CourseStudent.course_id)
        .all()
    }
    own = {row[0]: row[1:] for row in own_rows}
    teacher = {row[0]: row[1:] for row in teacher_rows}
    courses = (
        db.query(Course)
        .filter(Course.user_id == owner_id, Course.course_state != "ARCHIVED")
        .order_by(Course.name)
        .all()
    )
    stats: dict[str, CourseOut] = {}
    for course in courses:
        base = {
            "id": course.id,
            "name": course.name,
            "description": course.description,
            "section": course.section,
            "room": course.room,
            "course_state": course.course_state,
            "teachers": course.teacher_names or [],
        }
        if roles.get(course.id, "STUDENT") == "TEACHER":
            _submitted, graded, average = teacher.get(course.id, (0, 0, None))
            stats[course.id] = CourseOut(
                **base,
                role="TEACHER",
                student_count=roster_counts.get(course.id, 0),
                total_assignments=own[course.id][0],
                graded_count=graded,
                average_grade=round(average, 2) if average is not None else None,
            )
        else:
            total, todo, overdue, graded, average = own[course.id]
            stats[course.id] = CourseOut(
                **base,
                role="STUDENT",
                total_assignments=total,
                todo_count=todo,
                overdue_count=overdue,
                graded_count=graded,
                average_grade=round(average, 2) if average is not None else None,
            )
    return stats