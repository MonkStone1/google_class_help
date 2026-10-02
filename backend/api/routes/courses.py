"""Course endpoints: the list, one course's detail, its coursework, its roster
and its grade matrix.

Every course is resolved through ``guards._get_course`` (404 for missing or
archived) and, where the answer is class data, through ``guards._require_teacher``
(403 for a student course). Those two guards are why this module contains no
ownership logic of its own.
"""

# ruff: noqa: B008, DTZ901
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004).

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import sync
from api import guards, queries
from api.deps import current_user_id
from database import get_db
from models import Course, CourseWork, CourseWorkSubmission
from schemas import (
    AssignmentOut,
    CourseDetailOut,
    CourseOut,
    GradeColumn,
    StudentGradeRow,
    StudentOut,
    SubmissionCell,
    TeacherGradesOut,
)

router = APIRouter()


@router.get("/courses", response_model=list[CourseOut])
def list_courses(
    owner_id: int = Depends(current_user_id), db: Session = Depends(get_db)
) -> list[CourseOut]:
    stats = queries.courses._course_stats_sql(db, owner_id)
    courses = (
        db.query(Course)
        .filter(Course.user_id == owner_id, Course.course_state != "ARCHIVED")
        .order_by(Course.name)
        .all()
    )
    return [stats[c.id] for c in courses if c.id in stats]


@router.get("/courses/{course_id}", response_model=CourseDetailOut)
def course_detail(
    course_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> CourseDetailOut:
    course = guards._get_course(db, owner_id, course_id)
    stats = queries.courses._course_stats_sql(db, owner_id)
    role = guards._course_role(db, owner_id, course)
    # §21: the roster is teacher-only data. A student course has no roster
    # rows to begin with; gating on the role also keeps rows left over from
    # a former teaching period out of the response.
    students = (
        [
            queries.teacher._student_out(row)
            for row in queries.teacher._roster_rows(db, owner_id, course_id)
        ]
        if role == "TEACHER"
        else []
    )
    return CourseDetailOut(
        course=stats[course.id],
        role=role,
        students=students,
        last_sync=sync.last_sync_time(db, owner_id),
    )


@router.get("/courses/{course_id}/coursework", response_model=list[AssignmentOut])
def course_coursework(
    course_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> list[AssignmentOut]:
    """Coursework of one course: all of it for a teacher, own work for a student."""
    guards._get_course(db, owner_id, course_id)
    return [
        a
        for a in queries.assignments._load_assignments(db, owner_id)
        if a.course_id == course_id
    ]


@router.get("/courses/{course_id}/students", response_model=list[StudentOut])
def course_students(
    course_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> list[StudentOut]:
    course = guards._get_course(db, owner_id, course_id)
    guards._require_teacher(db, owner_id, course)
    return [
        queries.teacher._student_out(row)
        for row in queries.teacher._roster_rows(db, owner_id, course_id)
    ]
@router.get("/courses/{course_id}/grades", response_model=TeacherGradesOut)
def course_grades(
    course_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> TeacherGradesOut:
    """Spreadsheet-style grade matrix: every student × every assignment."""
    course = guards._get_course(db, owner_id, course_id)
    guards._require_teacher(db, owner_id, course)
    works = sorted(
        db.query(CourseWork).filter_by(user_id=owner_id, course_id=course_id).all(),
        key=lambda work: (work.due_at is None, work.due_at or datetime.max),
    )
    rows = (
        db.query(CourseWorkSubmission)
        .filter_by(user_id=owner_id, course_id=course_id)
        .all()
    )
    sub_map = {(row.coursework_id, row.student_id): row for row in rows}
    assignments = [
        GradeColumn(
            assignment_id=work.id,
            title=work.title,
            max_points=work.max_points,
            due_at=work.due_at,
        )
        for work in works
    ]
    student_rows: list[StudentGradeRow] = []
    class_percents: list[float] = []
    for student in queries.teacher._roster_rows(db, owner_id, course_id):
        cells: list[SubmissionCell] = []
        row_percents: list[float] = []
        for work in works:
            has_sub = sub_map.get((work.id, student.student_id))
            if has_sub is None:
                cells.append(SubmissionCell(coursework_id=work.id))
                continue
            graded = has_sub.assigned_points is not None
            percent = sync.grade_percent(has_sub.assigned_points, work.max_points)
            if percent is not None:
                row_percents.append(percent)
            cells.append(
                SubmissionCell(
                    coursework_id=work.id,
                    status=sync.derive_submission_status(has_sub.state, graded),
                    submitted=sync.is_submitted_state(has_sub.state),
                    returned=has_sub.state == "RETURNED",
                    graded=graded,
                    late=has_sub.late,
                    points=has_sub.assigned_points,
                    max_points=work.max_points,
                    percent=percent,
                    submitted_at=has_sub.submitted_at,
                    updated_at=has_sub.updated_time,
                )
            )
        average = (
            round(sum(row_percents) / len(row_percents), 1) if row_percents else None
        )
        if average is not None:
            class_percents.append(average)
        student_rows.append(
            StudentGradeRow(
                student=queries.teacher._student_out(student),
                cells=cells,
                average_percent=average,
            )
        )
    return TeacherGradesOut(
        course_id=course.id,
        course_name=course.name,
        role="TEACHER",
        assignments=assignments,
        rows=student_rows,
        class_average=(
            round(sum(class_percents) / len(class_percents), 2)
            if class_percents
            else None
        ),
        last_sync=sync.last_sync_time(db, owner_id),
    )