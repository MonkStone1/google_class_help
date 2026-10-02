"""Global counters for the student dashboard header.

Separate from ``courses._course_stats_sql`` on purpose: that one aggregates
per course, this one answers "how many assignments does this user have at all"
in a single statement with no fan-out. ``/api/status`` is polled every ~1.5 s
while signing in, so the endpoint that calls it must not load tables.
"""

# ruff: noqa: DTZ005
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004).

from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from db.models.classroom import Course, CourseRole, CourseWork, StudentSubmission
from sync.grading import SUBMITTED_STATES


def _student_totals_sql(db: Session, owner_id: int) -> dict:
    """Global counters for the student dashboard, computed in SQL (§2.1).

    Every course the signed-in user does not teach (a missing CourseRole row
    defaults to STUDENT, like _role_map) and is not archived. One statement
    with no fan-out: CourseRole and StudentSubmission are both at most 1:1
    with a course/coursework row, so plain counts/sums are safe here.
    Scoped to the owner's rows; joins equate user_id on both sides (§67).
    """
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today_start + timedelta(days=1)
    is_student_course = or_(CourseRole.role.is_(None), CourseRole.role != "TEACHER")
    pending = func.coalesce(StudentSubmission.state.not_in(SUBMITTED_STATES), True)
    percent = case(
        (
            and_(
                StudentSubmission.assigned_points.is_not(None),
                CourseWork.max_points.is_not(None),
                CourseWork.max_points > 0,
            ),
            StudentSubmission.assigned_points / CourseWork.max_points * 100,
        ),
        else_=None,
    )
    total, completed, overdue, due_today, average = (
        db.query(
            func.count(CourseWork.id),
            func.coalesce(
                func.sum(
                    case((StudentSubmission.state.in_(SUBMITTED_STATES), 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                CourseWork.due_at.is_not(None),
                                CourseWork.due_at < now,
                                pending,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                CourseWork.due_at.is_not(None),
                                CourseWork.due_at >= today_start,
                                CourseWork.due_at < tomorrow,
                                pending,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.avg(percent),
        )
        .select_from(Course)
        .outerjoin(
            CourseRole,
            and_(
                CourseRole.user_id == Course.user_id, CourseRole.course_id == Course.id
            ),
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
        .filter(
            Course.user_id == owner_id,
            Course.course_state != "ARCHIVED",
            is_student_course,
        )
        .one()
    )
    return {
        "total_assignments": total or 0,
        "completed": completed or 0,
        # Missing and overdue are the same condition by definition (not
        # submitted and past due); both fields stay for API compatibility.
        "missing": overdue or 0,
        "overdue": overdue or 0,
        "due_today": due_today or 0,
        "average_grade": round(average, 2) if average is not None else None,
    }