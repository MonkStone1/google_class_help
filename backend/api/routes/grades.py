"""Grade endpoints: the per-course rollup for the student dashboard and the
single-student view shared by the student and teacher routes.

The rollup keeps a historical quirk on purpose: it drops courses whose
``course_state`` is NULL, while the coursework listing keeps them. The two
readers apply DIFFERENT archived rules and both are preserved exactly — see the
comment inside ``grades``.
"""

# ruff: noqa: B008, DTZ901
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004).

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import sync
from api import guards, queries
from api.deps import current_user_id
from db.models.classroom import CourseStudent, CourseWork
from db.session import get_db
from schemas.dashboard import (
    CourseGrades,
    GradeItem,
    MaterialOut,
    StudentGradeItem,
    StudentGradesOut,
    StudentOut,
)

router = APIRouter()


@router.get("/grades", response_model=list[CourseGrades])
def grades(
    owner_id: int = Depends(current_user_id), db: Session = Depends(get_db)
) -> list[CourseGrades]:
    # One course query for the whole request instead of two: _load_assignments
    # re-read the courses table, and this endpoint read it a second time.
    #
    # The two readers apply DIFFERENT archived rules and both are kept exactly as
    # they were: the coursework list keeps a NULL course_state (Python `!=`),
    # while this rollup has always dropped it (SQL `!=` never matches NULL).
    # Unifying them would either add a course to /api/grades or remove its
    # coursework from /api/assignments.
    cached_courses = queries.courses._all_courses(db, owner_id)
    assignments = queries.assignments._student_only(
        queries.assignments._load_assignments(
            db,
            owner_id,
            {
                course_id: course
                for course_id, course in cached_courses.items()
                if course.course_state != "ARCHIVED"
            },
        )
    )
    courses = sorted(
        (
            course
            for course in cached_courses.values()
            if course.course_state not in (None, "ARCHIVED")
        ),
        key=lambda course: course.name,
    )
    out: list[CourseGrades] = []
    for course in courses:
        graded_ok = [
            a
            for a in assignments
            if a.course_id == course.id
            and a.graded
            and a.points is not None
            and a.max_points
        ]
        if not graded_ok:
            continue
        items = []
        for a in sorted(
            graded_ok, key=lambda x: x.due_at or datetime.min, reverse=True
        ):
            percent = sync.grade_percent(a.points, a.max_points)
            items.append(
                GradeItem(
                    assignment_id=a.id,
                    title=a.title,
                    points=a.points,
                    max_points=a.max_points,
                    percent=percent,
                    graded_at=None,
                    due_at=a.due_at,
                )
            )
        percents = [i.percent for i in items if i.percent is not None]
        out.append(
            CourseGrades(
                course_id=course.id,
                course_name=course.name,
                average=round(sum(percents) / len(percents), 2) if percents else None,
                items=items,
            )
        )
    return out


@router.get(
    "/courses/{course_id}/students/{student_id}/grades",
    response_model=StudentGradesOut,
)
def student_grades(
    course_id: str,
    student_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> StudentGradesOut:
    """One student's coursework, submission state and grade for a course."""
    course = guards._get_course(db, owner_id, course_id)
    is_teacher = guards._course_role(db, owner_id, course) == "TEACHER"
    if not is_teacher and student_id != "me":
        raise HTTPException(
            status_code=403,
            detail="Students can only view their own grades.",
        )
    # §23: a teacher asking for a student who is not enrolled in this course
    # gets 404, not a fabricated empty student row. The student route keeps
    # the "me" sentinel (ADR-0010).
    roster_row = None
    if is_teacher:
        roster_row = db.get(CourseStudent, (owner_id, course_id, student_id))
        if roster_row is None:
            raise HTTPException(status_code=404, detail="Student not found.")
    student = (
        queries.teacher._student_out(roster_row, student_id)
        if is_teacher
        else StudentOut(id="me")
    )
    works = sorted(
        db.query(CourseWork).filter_by(user_id=owner_id, course_id=course_id).all(),
        key=lambda work: (work.due_at is None, work.due_at or datetime.max),
    )
    sub_map = queries.teacher._grade_submissions(
        db, owner_id, course_id, student_id, is_teacher
    )
    items: list[StudentGradeItem] = []
    percents: list[float] = []
    for work in works:
        row = sub_map.get(work.id)
        graded = row is not None and row.assigned_points is not None
        percent = (
            sync.grade_percent(row.assigned_points, work.max_points)
            if row is not None
            else None
        )
        if percent is not None:
            percents.append(percent)
        items.append(
            StudentGradeItem(
                assignment_id=work.id,
                title=work.title,
                due_at=work.due_at,
                max_points=work.max_points,
                submission_state=row.state if row else None,
                status=sync.derive_submission_status(
                    row.state if row else None, graded
                ),
                submitted=sync.is_submitted_state(row.state if row else None),
                returned=bool(row and row.state == "RETURNED"),
                graded=graded,
                late=row.late if row else False,
                points=row.assigned_points if row else None,
                percent=percent,
                submitted_at=getattr(row, "submitted_at", None) if row else None,
                updated_at=row.updated_time if row else None,
                attachments=[
                    MaterialOut(**m)
                    for m in (
                        (getattr(row, "attachments", None) if row else None) or []
                    )
                ],
                alternate_link=work.alternate_link,
            )
        )
    return StudentGradesOut(
        course_id=course.id,
        course_name=course.name,
        student=student,
        average_percent=(round(sum(percents) / len(percents), 2) if percents else None),
        items=items,
        last_sync=sync.last_sync_time(db, owner_id),
    )