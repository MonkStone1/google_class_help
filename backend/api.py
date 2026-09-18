"""HTTP API surface of the dashboard.

Endpoints are thin: they read from SQLite, derive views with the sync
service, and return Pydantic models. Google communication lives in
classroom_api.py / sync.py only.
"""

# ruff: noqa: B008, DTZ005, DTZ901
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004);
#       due dates arrive from Classroom without a timezone.

import threading
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

import auth
import sync
from classroom_api import ClassroomClient, build_service
from database import get_db
from grading import SUBMITTED_STATES
from models import (
    Course,
    CourseRole,
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
    StudentSubmission,
)
from schemas import (
    AssignmentDetailOut,
    AssignmentOut,
    AuthStatus,
    CourseDetailOut,
    CourseGrades,
    CourseOut,
    GradeColumn,
    GradeItem,
    MaterialOut,
    StudentGradeItem,
    StudentGradeRow,
    StudentGradesOut,
    StudentOut,
    SubmissionCell,
    SubmissionOut,
    SyncResult,
    SyncStatus,
    TeacherGradesOut,
)
from sync_store import SubmissionRow, get_submission

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- auth

# User profile cache (review §1.3): the frontend polls /api/status every
# ~1.5 s while logging in, and a network roundtrip to Google inside every
# poll is unacceptable. The profile changes about once a year, so it is
# cached for five minutes; the network call itself runs OUTSIDE the lock.
_profile_lock = threading.Lock()
_profile_cache: tuple[float, str | None, str | None] | None = None
PROFILE_TTL_SECONDS = 300


def _cached_profile(creds) -> tuple[str | None, str | None]:
    """User profile with a 5-minute TTL; one Google request at a time."""
    global _profile_cache
    with _profile_lock:
        if (
            _profile_cache is not None
            and time.monotonic() - _profile_cache[0] < PROFILE_TTL_SECONDS
        ):
            return _profile_cache[1], _profile_cache[2]
    profile = ClassroomClient(build_service(creds)).get_user_profile()
    name = profile.get("name", {})
    value = (
        name.get("fullName"),
        profile.get("emailAddress") or name.get("fullName"),
    )
    with _profile_lock:
        _profile_cache = (time.monotonic(), value[0], value[1])
    return value


def _reset_profile_cache() -> None:
    """Drop the cached profile (logout / re-login as another account)."""
    global _profile_cache
    with _profile_lock:
        _profile_cache = None


def _build_auth_status() -> AuthStatus:
    status = auth.login_status()
    user_name = None
    user_email = None
    creds = auth.get_valid_credentials()
    if creds is not None:
        user_name, user_email = _cached_profile(creds)
    return AuthStatus(**status, user_name=user_name, user_email=user_email)


@router.get("/auth/status", response_model=AuthStatus)
def auth_status() -> AuthStatus:
    return _build_auth_status()


@router.post("/auth/login", response_model=AuthStatus)
def login() -> AuthStatus:
    result = auth.start_login()
    if not result.get("started"):
        raise HTTPException(
            status_code=500, detail=result.get("error", "Login failed.")
        )
    return _build_auth_status()


@router.post("/auth/logout", response_model=AuthStatus)
def logout() -> AuthStatus:
    auth.logout()
    _reset_profile_cache()  # the next sign-in may be a different account
    return _build_auth_status()


# ------------------------------------------------------------ derived SQL


def _role_map(db: Session) -> dict[str, str]:
    """course_id → role of the signed-in user ("TEACHER"/"STUDENT").

    Roles live in their own table so an older cache file keeps working
    (ADR-0003/0017); courses synced before teacher mode default to STUDENT.
    """
    return {row.course_id: row.role for row in db.query(CourseRole).all()}


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


def _load_assignments(db: Session) -> list[AssignmentOut]:
    """Load cached assignments merged with the role-appropriate details.

    Student courses (the existing dashboard) merge the authenticated user's
    own submission into the personal fields. Teacher courses merge aggregate
    submission counts instead: the teacher is not a student in their own
    course, so `submitted`/`graded` stay false there and the aggregates live
    in `submission_count`/`graded_count`/`average_percent`.

    Archived courses are ignored everywhere (see sync): their cached rows, if
    any, are excluded from every response built here.
    """
    courses = {c.id: c for c in db.query(Course).all() if c.course_state != "ARCHIVED"}
    roles = _role_map(db)
    submissions = {
        (s.course_id, s.coursework_id): s for s in db.query(StudentSubmission).all()
    }
    teacher_submissions: dict[tuple[str, str], list[CourseWorkSubmission]] = {}
    for row in db.query(CourseWorkSubmission).all():
        teacher_submissions.setdefault((row.course_id, row.coursework_id), []).append(
            row
        )
    roster_counts = {
        course_id: count
        for course_id, count in db.query(
            CourseStudent.course_id, func.count(CourseStudent.user_id)
        )
        .group_by(CourseStudent.course_id)
        .all()
    }
    now = datetime.now()
    out: list[AssignmentOut] = []

    works = db.query(CourseWork).all()
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


def _assignment_by_id(db: Session, coursework_id: str) -> AssignmentOut | None:
    """One cached assignment by primary key (review §2.1).

    Replaces the old ``next(a for a in _load_assignments(db) ...)`` scan,
    which loaded every course/coursework/submission table to answer for a
    single row. Indexed gets only; archived or missing work is None/404.
    """
    work = db.get(CourseWork, coursework_id)
    if work is None:
        return None
    course = db.get(Course, work.course_id)
    if course is None or course.course_state == "ARCHIVED":
        return None
    role = _role_map(db).get(work.course_id, "STUDENT")
    roster_count = (
        db.query(func.count(CourseStudent.user_id))
        .filter_by(course_id=work.course_id)
        .scalar()
        or 0
    )
    return _build_assignment_out(
        work,
        course,
        role,
        get_submission(db, work.course_id, work.id, "me", is_teacher=False)
        if role != "TEACHER"
        else None,
        db.query(CourseWorkSubmission)
        .filter_by(course_id=work.course_id, coursework_id=work.id)
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


def _course_stats_sql(db: Session) -> dict[str, CourseOut]:
    """Per-course aggregates computed in SQL (review §2.1).

    Replaces the old approach of loading every coursework/submission row
    into Python and filtering with list comprehensions on every request.
    Student and teacher counters are computed in two separate grouped
    queries: a course has rows in exactly one of the two submission tables,
    so a single join of both would multiply rows. Student averages are
    mean-of-assignments, the same formula the Python code used; the teacher
    average is the mean over all class submissions (previously the mean of
    per-assignment means — the per-submission weighting is the fairer one).
    """
    now = datetime.now()
    own_pending = func.coalesce(StudentSubmission.state.not_in(SUBMITTED_STATES), True)
    own_rows = (
        db.query(
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
                        (StudentSubmission.assigned_points.is_not(None), 1),
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
                        StudentSubmission.assigned_points / CourseWork.max_points * 100,
                    ),
                    else_=None,
                )
            ).label("average"),
        )
        .outerjoin(CourseWork, CourseWork.course_id == Course.id)
        .outerjoin(StudentSubmission, StudentSubmission.coursework_id == CourseWork.id)
        .filter(Course.course_state != "ARCHIVED")
        .group_by(Course.id)
        .all()
    )
    teacher_rows = (
        db.query(
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
        .outerjoin(CourseWork, CourseWork.course_id == Course.id)
        .outerjoin(
            CourseWorkSubmission, CourseWorkSubmission.coursework_id == CourseWork.id
        )
        .filter(Course.course_state != "ARCHIVED")
        .group_by(Course.id)
        .all()
    )
    roles = _role_map(db)
    roster_counts = {
        course_id: count
        for course_id, count in db.query(
            CourseStudent.course_id, func.count(CourseStudent.user_id)
        )
        .group_by(CourseStudent.course_id)
        .all()
    }
    own = {row[0]: row[1:] for row in own_rows}
    teacher = {row[0]: row[1:] for row in teacher_rows}
    courses = (
        db.query(Course)
        .filter(Course.course_state != "ARCHIVED")
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


# ------------------------------------------------------------- data views


@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db)) -> list[CourseOut]:
    stats = _course_stats_sql(db)
    courses = (
        db.query(Course)
        .filter(Course.course_state != "ARCHIVED")
        .order_by(Course.name)
        .all()
    )
    return [stats[c.id] for c in courses if c.id in stats]


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(
    course_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AssignmentOut]:
    assignments = _student_only(_load_assignments(db))
    if course_id:
        assignments = [a for a in assignments if a.course_id == course_id]
    if search:
        needle = search.lower()
        assignments = [
            a
            for a in assignments
            if needle in a.title.lower()
            or needle in a.course_name.lower()
            or (a.description and needle in a.description.lower())
        ]
    if status == "todo":
        assignments = [a for a in assignments if not a.submitted]
    elif status == "overdue":
        assignments = [a for a in assignments if a.is_overdue]
    elif status == "completed":
        assignments = [a for a in assignments if a.submitted]
    elif status == "graded":
        assignments = [a for a in assignments if a.graded]
    elif status == "ungraded":
        assignments = [a for a in assignments if not a.graded]
    return assignments


@router.get("/assignments/upcoming", response_model=list[AssignmentOut])
def upcoming(
    days: int = Query(default=7, ge=1, le=60),
    db: Session = Depends(get_db),
) -> list[AssignmentOut]:
    now = datetime.now()
    end = now + timedelta(days=days)
    return [
        a
        for a in _student_only(_load_assignments(db))
        if a.due_at is not None and now <= a.due_at <= end and not a.submitted
    ]


@router.get("/assignments/overdue", response_model=list[AssignmentOut])
def overdue(db: Session = Depends(get_db)) -> list[AssignmentOut]:
    return [a for a in _student_only(_load_assignments(db)) if a.is_overdue]


@router.get("/grades", response_model=list[CourseGrades])
def grades(db: Session = Depends(get_db)) -> list[CourseGrades]:
    assignments = _student_only(_load_assignments(db))
    courses = (
        db.query(Course)
        .filter(Course.course_state != "ARCHIVED")
        .order_by(Course.name)
        .all()
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


@router.get("/calendar")
def calendar(
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> dict:
    def _parse(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    start = _parse(from_date) or datetime.now().replace(day=1)
    end = _parse(to_date) or (start + timedelta(days=62))
    grouped: dict[str, list] = {}
    for a in _student_only(_load_assignments(db)):
        if a.due_at is None or not (start <= a.due_at <= end):
            continue
        grouped.setdefault(a.due_at.date().isoformat(), []).append(a)
    return {"from": start.isoformat(), "to": end.isoformat(), "days": grouped}


def _student_totals_sql(db: Session) -> dict:
    """Global counters for the student dashboard, computed in SQL (§2.1).

    Every course the signed-in user does not teach (a missing CourseRole row
    defaults to STUDENT, like _role_map) and is not archived. One statement
    with no fan-out: CourseRole and StudentSubmission are both at most 1:1
    with a course/coursework row, so plain counts/sums are safe here.
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
        .outerjoin(CourseRole, CourseRole.course_id == Course.id)
        .outerjoin(CourseWork, CourseWork.course_id == Course.id)
        .outerjoin(StudentSubmission, StudentSubmission.coursework_id == CourseWork.id)
        .filter(Course.course_state != "ARCHIVED", is_student_course)
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


@router.get("/status", response_model=SyncStatus)
def status(db: Session = Depends(get_db)) -> SyncStatus:
    auth_status = _build_auth_status()
    return SyncStatus(
        authenticated=auth_status.authenticated,
        user_name=auth_status.user_name,
        user_email=auth_status.user_email,
        last_sync=sync.get_state_datetime(db, "last_sync"),
        last_sync_error=sync.get_state(db, "last_sync_error"),
        # Aggregated in SQL, not by loading every table: the frontend polls
        # this endpoint every ~1.5 s while signing in (review §2.1 / §1.3).
        **_student_totals_sql(db),
    )


@router.post("/sync", response_model=SyncResult)
def run_sync(db: Session = Depends(get_db)) -> SyncResult:
    result = sync.sync_now()
    if not result.get("ok") and "already running" in str(result.get("error", "")):
        # A running sync is not an error: 409 tells the client to keep
        # showing its spinner instead of surfacing a failure (review §3.9).
        raise HTTPException(
            status_code=409, detail="A synchronization is already running."
        )
    return SyncResult(**result)


@router.delete("/cache")
def clear_cache(
    confirm: bool = Query(default=False), db: Session = Depends(get_db)
) -> dict:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to clear all locally cached data.",
        )
    sync.reset_cache(db)
    return {"ok": True, "cleared": True}


# ------------------------------------------------------- teacher-mode views


def _get_course(db: Session, course_id: str) -> Course:
    """Course by id; ARCHIVED and missing courses are 404."""
    course = db.get(Course, course_id)
    if course is None or course.course_state == "ARCHIVED":
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


def _course_role(db: Session, course: Course) -> str:
    """Role of the signed-in user in this course ("TEACHER"/"STUDENT")."""
    row = db.get(CourseRole, course.id)
    return row.role if row else "STUDENT"


def _require_teacher(db: Session, course: Course) -> None:
    """Teacher-only endpoints must never be reachable from a student course."""
    if _course_role(db, course) != "TEACHER":
        raise HTTPException(
            status_code=403,
            detail="This course is not taught by the signed-in user.",
        )


def _roster_rows(db: Session, course_id: str) -> list[CourseStudent]:
    return (
        db.query(CourseStudent)
        .filter_by(course_id=course_id)
        .order_by(CourseStudent.full_name)
        .all()
    )


def _student_out(row: CourseStudent | None, fallback_id: str = "") -> StudentOut:
    if row is None:
        return StudentOut(id=fallback_id, full_name=fallback_id)
    return StudentOut(
        id=row.user_id,
        full_name=row.full_name or row.user_id,
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
    db: Session, course: Course, work: CourseWork
) -> list[SubmissionOut]:
    """Every roster student's state for one assignment (teacher view).

    Students with no submission row are still listed as "not submitted", so
    the assignment page shows the whole class rather than only those who
    turned work in.
    """
    if _course_role(db, course) != "TEACHER":
        sub = get_submission(db, course.id, work.id, "me", is_teacher=False)
        if sub is None:
            return []
        return [_submission_out_for(sub, "me", "", work)]

    rows = (
        db.query(CourseWorkSubmission)
        .filter_by(course_id=course.id, coursework_id=work.id)
        .all()
    )
    sub_map = {row.student_id: row for row in rows}
    roster = {row.user_id: row for row in _roster_rows(db, course.id)}
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


@router.get("/courses/{course_id}", response_model=CourseDetailOut)
def course_detail(course_id: str, db: Session = Depends(get_db)) -> CourseDetailOut:
    course = _get_course(db, course_id)
    stats = _course_stats_sql(db)
    role = _course_role(db, course)
    return CourseDetailOut(
        course=stats[course.id],
        role=role,
        students=[_student_out(row) for row in _roster_rows(db, course_id)],
        last_sync=sync.get_state_datetime(db, "last_sync"),
    )


@router.get("/courses/{course_id}/coursework", response_model=list[AssignmentOut])
def course_coursework(
    course_id: str, db: Session = Depends(get_db)
) -> list[AssignmentOut]:
    """Coursework of one course: all of it for a teacher, own work for a student."""
    _get_course(db, course_id)
    return [a for a in _load_assignments(db) if a.course_id == course_id]


@router.get("/courses/{course_id}/students", response_model=list[StudentOut])
def course_students(course_id: str, db: Session = Depends(get_db)) -> list[StudentOut]:
    course = _get_course(db, course_id)
    _require_teacher(db, course)
    return [_student_out(row) for row in _roster_rows(db, course_id)]


@router.get("/courses/{course_id}/grades", response_model=TeacherGradesOut)
def course_grades(course_id: str, db: Session = Depends(get_db)) -> TeacherGradesOut:
    """Spreadsheet-style grade matrix: every student × every assignment."""
    course = _get_course(db, course_id)
    _require_teacher(db, course)
    works = sorted(
        db.query(CourseWork).filter_by(course_id=course_id).all(),
        key=lambda work: (work.due_at is None, work.due_at or datetime.max),
    )
    rows = db.query(CourseWorkSubmission).filter_by(course_id=course_id).all()
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
    for student in _roster_rows(db, course_id):
        cells: list[SubmissionCell] = []
        row_percents: list[float] = []
        for work in works:
            has_sub = sub_map.get((work.id, student.user_id))
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
                student=_student_out(student),
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
        last_sync=sync.get_state_datetime(db, "last_sync"),
    )


@router.get(
    "/courses/{course_id}/coursework/{coursework_id}",
    response_model=AssignmentDetailOut,
)
def coursework_detail(
    course_id: str, coursework_id: str, db: Session = Depends(get_db)
) -> AssignmentDetailOut:
    """Full assignment page: metadata, materials and the submission table."""
    course = _get_course(db, course_id)
    work = db.get(CourseWork, coursework_id)
    if work is None or work.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    base = _assignment_by_id(db, coursework_id)  # PK lookup, not a full scan (§2.1)
    if base is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    submissions = _submissions_for_work(db, course, work)
    counts: dict[str, int] = {}
    for item in submissions:
        counts[item.status] = counts.get(item.status, 0) + 1
    return AssignmentDetailOut(
        **base.model_dump(), submissions=submissions, status_counts=counts
    )


@router.get(
    "/courses/{course_id}/coursework/{coursework_id}/submissions",
    response_model=list[SubmissionOut],
)
def coursework_submissions(
    course_id: str, coursework_id: str, db: Session = Depends(get_db)
) -> list[SubmissionOut]:
    course = _get_course(db, course_id)
    work = db.get(CourseWork, coursework_id)
    if work is None or work.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    return _submissions_for_work(db, course, work)


def _grade_submissions(
    db: Session, course_id: str, student_id: str, is_teacher: bool
) -> dict[str, CourseWorkSubmission | StudentSubmission]:
    """Submissions of one student in one course, from the right table.

    Teacher courses keep per-student rows in CourseWorkSubmission; the
    student route keeps the user's own rows in StudentSubmission (ADR-0010).
    Reading only CourseWorkSubmission made this endpoint return an empty
    grade list for every student course.
    """
    if is_teacher:
        rows = (
            db.query(CourseWorkSubmission)
            .filter_by(course_id=course_id, student_id=student_id)
            .all()
        )
        return {row.coursework_id: row for row in rows}
    rows = db.query(StudentSubmission).filter_by(course_id=course_id).all()
    return {row.coursework_id: row for row in rows}


@router.get(
    "/courses/{course_id}/students/{student_id}/grades",
    response_model=StudentGradesOut,
)
def student_grades(
    course_id: str, student_id: str, db: Session = Depends(get_db)
) -> StudentGradesOut:
    """One student's coursework, submission state and grade for a course."""
    course = _get_course(db, course_id)
    is_teacher = _course_role(db, course) == "TEACHER"
    if not is_teacher and student_id != "me":
        raise HTTPException(
            status_code=403,
            detail="Students can only view their own grades.",
        )
    student = (
        _student_out(db.get(CourseStudent, (course_id, student_id)), student_id)
        if is_teacher
        else StudentOut(id="me")
    )
    works = sorted(
        db.query(CourseWork).filter_by(course_id=course_id).all(),
        key=lambda work: (work.due_at is None, work.due_at or datetime.max),
    )
    sub_map = _grade_submissions(db, course_id, student_id, is_teacher)
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
        last_sync=sync.get_state_datetime(db, "last_sync"),
    )
