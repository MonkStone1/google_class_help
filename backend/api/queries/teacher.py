"""Teacher-side reads: roster, per-student submissions, grade rows.

``_submission_out_for`` is the ONE field mapping for a submission row from
either submission table (§2.3): ``sync_store.get_submission`` picks the table by
role, and fields only teacher rows have (``submitted_at``, ``attachments``) are
read with ``getattr`` and default to empty for the student's own row. A missing
row is "not submitted", not 0/100.
"""

# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004).

from sqlalchemy.orm import Session

import sync
from db.models.classroom import (
    Course,
    CourseRole,
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
    StudentSubmission,
)
from schemas.dashboard import MaterialOut, StudentOut, SubmissionOut
from sync.store import SubmissionRow, get_submission


def course_role(db: Session, owner_id: int, course: Course) -> str:
    """Role of the cache owner in this course ("TEACHER"/"STUDENT")."""
    row = db.get(CourseRole, (owner_id, course.id))
    return row.role if row else "STUDENT"


def _roster_rows(db: Session, owner_id: int, course_id: str) -> list[CourseStudent]:
    return (
        db.query(CourseStudent)
        .filter_by(user_id=owner_id, course_id=course_id)
        .order_by(CourseStudent.full_name)
        .all()
    )


def _student_out(row: CourseStudent | None, fallback_id: str = "") -> StudentOut:
    if row is None:
        return StudentOut(id=fallback_id, full_name=fallback_id)
    return StudentOut(
        id=row.student_id,
        full_name=row.full_name or row.student_id,
        email=row.email,
        photo_url=row.photo_url,
    )


def _submission_out_for(
    row: SubmissionRow | None,
    student_id: str,
    student_name: str,
    work: CourseWork,
) -> SubmissionOut:
    """Normalize one submission row from either submission table (§2.3).

    The table is picked by sync_store.get_submission, so the caller never
    branches on the role; fields that only teacher rows have (submitted_at,
    attachments) are read with getattr and default to empty for the
    student's own row. A missing row is "not submitted", not 0/100.
    """
    if row is None:
        return SubmissionOut(
            student_id=student_id,
            student_name=student_name,
            coursework_id=work.id,
            status="not_submitted",
            max_points=work.max_points,
        )
    graded = row.assigned_points is not None
    return SubmissionOut(
        student_id=student_id,
        student_name=student_name,
        coursework_id=work.id,
        submission_state=row.state,
        status=sync.derive_submission_status(row.state, graded),
        submitted=sync.is_submitted_state(row.state),
        returned=row.state == "RETURNED",
        graded=graded,
        late=row.late,
        points=row.assigned_points,
        max_points=work.max_points,
        percent=sync.grade_percent(row.assigned_points, work.max_points),
        submitted_at=getattr(row, "submitted_at", None),
        updated_at=row.updated_time,
        attachments=[
            MaterialOut(**m) for m in (getattr(row, "attachments", None) or [])
        ],
    )


def _submissions_for_work(
    db: Session, owner_id: int, course: Course, work: CourseWork
) -> list[SubmissionOut]:
    """Every roster student's state for one assignment (teacher view).

    Students with no submission row are still listed as "not submitted", so
    the assignment page shows the whole class rather than only those who
    turned work in.
    """
    if course_role(db, owner_id, course) != "TEACHER":
        sub = get_submission(db, owner_id, course.id, work.id, "me", is_teacher=False)
        if sub is None:
            return []
        return [_submission_out_for(sub, "me", "", work)]

    rows = (
        db.query(CourseWorkSubmission)
        .filter_by(user_id=owner_id, course_id=course.id, coursework_id=work.id)
        .all()
    )
    sub_map = {row.student_id: row for row in rows}
    roster = {row.student_id: row for row in _roster_rows(db, owner_id, course.id)}
    # A submission for an unknown student must still surface, not vanish.
    for student_id in sub_map:
        roster.setdefault(student_id, None)  # type: ignore[arg-type]
    out = [
        _submission_out_for(
            sub_map.get(student_id),
            student_id,
            (roster[student_id].full_name if roster[student_id] else student_id)
            or student_id,
            work,
        )
        for student_id in roster
    ]
    out.sort(key=lambda item: item.student_name.lower())
    return out


def _grade_submissions(
    db: Session, owner_id: int, course_id: str, student_id: str, is_teacher: bool
) -> dict[str, CourseWorkSubmission | StudentSubmission]:
    """Submissions of one student in one course, from the right table.

    Teacher courses keep per-student rows in CourseWorkSubmission; the
    student route keeps the user's own rows in StudentSubmission (ADR-0010).
    Reading only CourseWorkSubmission made this endpoint return an empty
    grade list for every student course. Scoped to the cache owner (stage 3).
    """
    if is_teacher:
        rows = (
            db.query(CourseWorkSubmission)
            .filter_by(user_id=owner_id, course_id=course_id, student_id=student_id)
            .all()
        )
        return {row.coursework_id: row for row in rows}
    rows = (
        db.query(StudentSubmission)
        .filter_by(user_id=owner_id, course_id=course_id)
        .all()
    )
    return {row.coursework_id: row for row in rows}