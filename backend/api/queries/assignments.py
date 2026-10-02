"""Assignment reads: the merged student/teacher assignment list and its filters.

The bulk loader here and the single-row lookup ``_assignment_by_id`` build
identical output through ``_build_assignment_out`` on purpose — one of them
used to be a linear scan that loaded every coursework and submission table to
answer for a single row (review §2.1).
"""

# ruff: noqa: DTZ005, DTZ901
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004);
#       due dates arrive from Classroom without a timezone.

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

import sync
from api import queries
from db.models.classroom import (
    Course,
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
    StudentSubmission,
)
from schemas.dashboard import AssignmentOut, MaterialOut
from sync.store import SubmissionRow, get_submission


def _build_assignment_out(
    work: CourseWork,
    course: Course,
    role: str,
    sub: SubmissionRow | None,
    teacher_rows: list[CourseWorkSubmission],
    roster_count: int,
    now: datetime,
) -> AssignmentOut:
    """One AssignmentOut from preloaded rows — shared by the bulk loader and
    the PK lookup (_assignment_by_id), so both paths build identical rows."""
    common = {
        "id": work.id,
        "course_id": work.course_id,
        "course_name": course.name,
        "title": work.title,
        "description": work.description,
        "due_at": work.due_at,
        "max_points": work.max_points,
        "work_type": work.work_type,
        "state": work.state,
        "alternate_link": work.alternate_link,
        "materials": [MaterialOut(**m) for m in (work.materials or [])],
        "created_at": work.creation_time,
        "updated_at": work.updated_time,
        "role": role,
    }
    if role == "TEACHER":
        graded_rows = [row for row in teacher_rows if row.assigned_points is not None]
        percents = [
            percent
            for row in graded_rows
            if (percent := sync.grade_percent(row.assigned_points, work.max_points))
            is not None
        ]
        return AssignmentOut(
            **common,
            student_count=roster_count,
            submission_count=len(
                [row for row in teacher_rows if sync.is_submitted_state(row.state)]
            ),
            graded_count=len(graded_rows),
            average_percent=(
                round(sum(percents) / len(percents), 1) if percents else None
            ),
        )
    sub_state = sub.state if sub else None
    submitted = sync.is_submitted_state(sub_state)
    graded = sub is not None and sub.assigned_points is not None
    is_overdue = work.due_at is not None and work.due_at < now and not submitted
    return AssignmentOut(
        **common,
        submission_state=sub_state,
        submitted=submitted,
        graded=graded,
        points=sub.assigned_points if sub else None,
        late=sub.late if sub else False,
        is_overdue=is_overdue,
        priority=sync.compute_priority(
            work.due_at, is_overdue, now, is_todo=not submitted
        ),
    )


def _load_assignments(
    db: Session, owner_id: int, courses: dict[str, Course] | None = None
) -> list[AssignmentOut]:
    """Load the owner's cached assignments merged with role-appropriate details.

    Student courses (the existing dashboard) merge their own submission into
    the personal fields. Teacher courses merge aggregate submission counts
    instead: the teacher is not a student in their own course, so
    `submitted`/`graded` stay false there and the aggregates live in
    `submission_count`/`graded_count`/`average_percent`.

    Archived courses are ignored everywhere (see sync): their cached rows, if
    any, are excluded from every response built here. Every query is scoped
    to the request's cache owner (stage 3); the joins in
    _course_stats_sql/_student_totals_sql additionally equate user_id so a
    same-named row of another user can never leak into an aggregate (§67).
    """
    if courses is None:
        courses = queries.courses._active_courses(db, owner_id)
    roles = queries.courses._role_map(db, owner_id)
    submissions = {
        (s.course_id, s.coursework_id): s
        for s in db.query(StudentSubmission).filter_by(user_id=owner_id).all()
    }
    teacher_submissions: dict[tuple[str, str], list[CourseWorkSubmission]] = {}
    for row in db.query(CourseWorkSubmission).filter_by(user_id=owner_id).all():
        teacher_submissions.setdefault((row.course_id, row.coursework_id), []).append(
            row
        )
    roster_counts = {
        course_id: count
        for course_id, count in db.query(
            CourseStudent.course_id, func.count(CourseStudent.student_id)
        )
        .filter_by(user_id=owner_id)
        .group_by(CourseStudent.course_id)
        .all()
    }
    now = datetime.now()
    out: list[AssignmentOut] = []

    works = db.query(CourseWork).filter_by(user_id=owner_id).all()
    for work in works:
        course = courses.get(work.course_id)
        if course is None:
            # Course missing from the cache or archived: never show its work.
            continue
        role = roles.get(work.course_id) or "STUDENT"
        out.append(
            _build_assignment_out(
                work,
                course,
                role,
                submissions.get((work.course_id, work.id))
                if role != "TEACHER"
                else None,
                teacher_submissions.get((work.course_id, work.id), [])
                if role == "TEACHER"
                else [],
                roster_counts.get(work.course_id, 0),
                now,
            )
        )
    out.sort(key=lambda a: a.due_at or datetime.max, reverse=False)
    return out


def _assignment_by_id(
    db: Session, owner_id: int, coursework_id: str
) -> AssignmentOut | None:
    """One cached assignment by primary key (review §2.1).

    Replaces the old ``next(a for a in _load_assignments(db) ...)`` scan,
    which loaded every course/coursework/submission table to answer for a
    single row. Indexed gets only; archived or missing work is None/404.
    The PK includes the owner (stage 3).
    """
    work = db.get(CourseWork, (owner_id, coursework_id))
    if work is None:
        return None
    course = db.get(Course, (owner_id, work.course_id))
    if course is None or course.course_state == "ARCHIVED":
        return None
    role = queries.courses._role_map(db, owner_id).get(work.course_id, "STUDENT")
    roster_count = (
        db.query(func.count(CourseStudent.student_id))
        .filter_by(user_id=owner_id, course_id=work.course_id)
        .scalar()
        or 0
    )
    return _build_assignment_out(
        work,
        course,
        role,
        get_submission(db, owner_id, work.course_id, work.id, "me", is_teacher=False)
        if role != "TEACHER"
        else None,
        db.query(CourseWorkSubmission)
        .filter_by(user_id=owner_id, course_id=work.course_id, coursework_id=work.id)
        .all()
        if role == "TEACHER"
        else [],
        roster_count,
        datetime.now(),
    )


def _student_only(assignments: list[AssignmentOut]) -> list[AssignmentOut]:
    """The authenticated user's own assignments (the existing dashboard).

    Teacher-order coursework belongs to the class, not to the signed-in user,
    so it is excluded from the student dashboard aggregates; it is served by
    the course/teacher endpoints instead.
    """
    return [a for a in assignments if a.role != "TEACHER"]