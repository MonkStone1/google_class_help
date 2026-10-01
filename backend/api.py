"""HTTP API surface of the dashboard.

Endpoints are thin: they read from the Classroom cache, derive views with
the sync service, and return Pydantic models. Google communication lives
in classroom_api.py / sync.py only.

User isolation (migration stage 4, §12/§13): every endpoint takes the
authenticated user through the ``get_current_user`` dependency
(ownership.py) — the validated session user in hosted mode, the synthetic
local owner on desktop — and every cache read is scoped to that user's
rows. No handler accepts or trusts a user id from the request itself;
IDOR-style cross-user access, including coursework reached by guessing a
Google id, resolves to 404/403. The desktop /api/auth/* endpoints keep
the loopback flow's single-account state by design (ADR-0019); in hosted
mode they are shadowed by hosted_auth.py (§16: per-attempt login state).

API response ownership (migration stage 4, §67): every response carries
user data through exactly one ownership path down to ``users.id``, and no
query joins two users' rows — aggregate joins equate ``user_id`` on both
sides:

    CourseOut / CourseDetailOut         → Course.user_id
    AssignmentOut / AssignmentDetailOut → CourseWork.user_id → Course.user_id
    StudentGradesOut                    → CourseWork/Course.user_id
                                          + StudentSubmission.user_id
    TeacherGradesOut                    → CourseStudent / CourseWorkSubmission
                                          → Course.user_id
    SubmissionOut                       → CourseWorkSubmission.user_id (teacher)
                                          or StudentSubmission.user_id (student)
    SyncStatus / AuthStatus             → the authenticated user itself

The schema makes the path structural: every cache table has ``user_id`` in
its primary key with an ownership FK (models.py, §10), so a row without an
owner cannot exist and a same-named Google id is unique only within one
user's scope. ``tests/test_user_isolation.py`` guards both the schema
shape and the aggregates.

Teacher mode and API surface (migration stage 6, §21–§24): roles stay
per-course and per-user (ADR-0017), every teacher-only view is gated on
BOTH the authenticated user and ``role == TEACHER``, and every response
keeps the stage-4 ownership path. ``GET /api/me`` exposes the caller's own
identity, and ``AuthStatus.user`` is the only identity shape — the flat
``user_name``/``user_email`` mirrors were removed in stage 7 (§26).
Status codes are
checked per §23: 401 for a missing application session, 403 for an
authenticated user without the course role, 404 for a resource outside the
caller's scope (never disclosing whether another user's row exists).
"""

# ruff: noqa: B008, DTZ005, DTZ901
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004);
#       due dates arrive from Classroom without a timezone.

import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

import maintenance
import metrics
import ownership
import sync
from classroom_api import ClassroomClient, build_service
from config import SYNC_STUCK_SECONDS
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
from models_auth import User
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
    UserOut,
)
from sync_store import SubmissionRow, get_submission

router = APIRouter(prefix="/api")


# ------------------------------------------------------- user profile (§17)

# The frontend polls the status endpoints every ~1.5 s while logging in or following a queued/running sync, and
# a network roundtrip to Google inside every poll is unacceptable. The
# profile changes about once a year, so it is cached for five minutes; the
# network call itself runs OUTSIDE the lock.
#
# The cache is keyed by the LOCAL USER ID (§17): one entry per user, never a
# process-global "last profile" another user could read. Hosted users do not
# use it at all — their `users` row is the authoritative profile, refreshed
# from Google at every login (§7) — so this path serves the desktop build's
# single local owner, whose row stays empty until the first Google lookup.
_profile_lock = threading.Lock()
_profile_cache: dict[int, tuple[float, str | None, str | None]] = {}
PROFILE_TTL_SECONDS = 300


def _cached_profile(user: User, creds) -> tuple[str | None, str | None]:
    """Profile of ONE user, cached under that user's id (§17).

    A users row that already carries a profile (hosted: written at login)
    is returned directly; otherwise Google userinfo is asked once and the
    answer is remembered under ``user.id`` for PROFILE_TTL_SECONDS. User B
    can never receive User A's cached name/email: lookups and writes use
    the id, not a module global.
    """
    if user.display_name or user.email:
        return user.display_name, user.email
    with _profile_lock:
        cached = _profile_cache.get(user.id)
        if cached is not None and time.monotonic() - cached[0] < PROFILE_TTL_SECONDS:
            return cached[1], cached[2]
    profile = ClassroomClient(build_service(creds)).get_user_profile()
    name = profile.get("name", {})
    value = (
        name.get("fullName"),
        profile.get("emailAddress") or name.get("fullName"),
    )
    with _profile_lock:
        _profile_cache[user.id] = (time.monotonic(), value[0], value[1])
    return value


def _reset_profile_cache(user_id: int | None = None) -> None:
    """Drop one user's cached profile (§17); no id clears every entry."""
    with _profile_lock:
        if user_id is None:
            _profile_cache.clear()
        else:
            _profile_cache.pop(user_id, None)


def _user_out(user: User) -> UserOut:
    """The identity fields of the caller (§24) plus the admin flag (ADR-0035).

    Built from the local ``users`` row only — never from a Google
    credential, token or OAuth object, none of which may appear in any
    response. ``is_admin`` is a BOOLEAN derived by the backend from
    ``config.is_admin_email``; the administrator address list itself never
    appears in a response.
    """
    from config import is_admin_email

    return UserOut(
        id=user.id,
        name=user.display_name,
        email=user.email,
        is_admin=is_admin_email(user.email),
    )


def _build_auth_status(user: User) -> AuthStatus:
    """AuthStatus of ONE user (§16) with their own profile (§17).

    Hosted: the ``users`` row is the authoritative profile (refreshed from
    Google at every login, §7) and there is no loopback login state.
    Desktop: the loopback flow's single-account state, plus the Google
    userinfo profile cached under the local owner's id.

    §24/§26: the payload describes THIS browser's application session,
    carries no OAuth internals (no access/refresh token, no client secret,
    no authorization code), and exposes identity only through ``user``.
    """
    if user.provider == "google":
        return AuthStatus(
            authenticated=True,
            login_in_progress=False,
            error=None,
            auth_url=None,
            user=_user_out(user),
        )
    # Desktop-only branch: auth (the loopback flow) is imported here so the
    # hosted service never loads the desktop module (migration stage 8, §32).
    import auth

    status = auth.login_status()
    identity: UserOut | None = None
    if status["authenticated"]:
        creds = auth.get_valid_credentials()
        if creds is not None:
            user_name, user_email = _cached_profile(user, creds)
            from config import is_admin_email

            # The desktop local owner has no address, so this is always False
            # there — the flag is computed by the same test as the API gate.
            identity = UserOut(
                id=user.id,
                name=user_name,
                email=user_email,
                is_admin=is_admin_email(user.email or user_email),
            )
    return AuthStatus(**status, user=identity)


def _is_authenticated(user: User) -> bool:
    """Signed-in state alone — no profile lookup (§17/§26).

    ``/api/status`` is polled every ~1.5 s while a sign-in is in flight, so
    it must not reach Google for identity fields it no longer exposes.
    """
    if user.provider == "google":
        return True
    import auth

    return bool(auth.login_status().get("authenticated"))


@router.get("/auth/status", response_model=AuthStatus)
def auth_status(user: User = Depends(ownership.get_current_user)) -> AuthStatus:
    return _build_auth_status(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(ownership.get_current_user)) -> UserOut:
    """Identity of the signed-in user (§23/§24).

    Same identity source as ``/api/auth/status``: the validated session
    user in hosted mode, the desktop local owner (with the Google profile
    resolved and cached per user) in desktop mode. A request without a
    valid application session is rejected earlier with 401 (hosted session
    gate / dependency); this handler never sees an anonymous caller.
    """
    status = _build_auth_status(user)
    # ``user`` is always populated by _build_auth_status; the fallback keeps
    # the type honest without inventing a second identity source.
    return status.user or _user_out(user)


@router.post("/auth/login", response_model=AuthStatus)
def login(user: User = Depends(ownership.get_current_user)) -> AuthStatus:
    import auth

    result = auth.start_login()
    if not result.get("started"):
        raise HTTPException(
            status_code=500, detail=result.get("error", "Login failed.")
        )
    return _build_auth_status(user)


@router.post("/auth/logout", response_model=AuthStatus)
def logout(user: User = Depends(ownership.get_current_user)) -> AuthStatus:
    import auth

    auth.logout()
    # Only the caller's cached profile is dropped (§17); the next sign-in on
    # this browser may be another account, but other users' entries stay.
    _reset_profile_cache(user.id)
    return _build_auth_status(user)


# ------------------------------------------------------- current user (§13)


def current_user_id(user: User = Depends(ownership.get_current_user)) -> int:
    """The authenticated user's id — the cache owner of this request (§13).

    Thin derivation over ``ownership.get_current_user``, which validates
    the hosted session (or resolves the desktop local owner) itself and
    never trusts a request-supplied id. Most cache reads need only the id;
    the endpoints that need the profile take the user dependency directly.
    """
    return user.id


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
        courses = _active_courses(db, owner_id)
    roles = _role_map(db, owner_id)
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
    role = _role_map(db, owner_id).get(work.course_id, "STUDENT")
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
                        StudentSubmission.assigned_points / CourseWork.max_points * 100,
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


# ------------------------------------------------------------- data views


@router.get("/courses", response_model=list[CourseOut])
def list_courses(
    owner_id: int = Depends(current_user_id), db: Session = Depends(get_db)
) -> list[CourseOut]:
    stats = _course_stats_sql(db, owner_id)
    courses = (
        db.query(Course)
        .filter(Course.user_id == owner_id, Course.course_state != "ARCHIVED")
        .order_by(Course.name)
        .all()
    )
    return [stats[c.id] for c in courses if c.id in stats]


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(
    course_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> list[AssignmentOut]:
    assignments = _student_only(_load_assignments(db, owner_id))
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
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> list[AssignmentOut]:
    now = datetime.now()
    end = now + timedelta(days=days)
    return [
        a
        for a in _student_only(_load_assignments(db, owner_id))
        if a.due_at is not None and now <= a.due_at <= end and not a.submitted
    ]


@router.get("/assignments/overdue", response_model=list[AssignmentOut])
def overdue(
    owner_id: int = Depends(current_user_id), db: Session = Depends(get_db)
) -> list[AssignmentOut]:
    return [a for a in _student_only(_load_assignments(db, owner_id)) if a.is_overdue]


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
    cached_courses = _all_courses(db, owner_id)
    assignments = _student_only(
        _load_assignments(
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


@router.get("/calendar")
def calendar(
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    owner_id: int = Depends(current_user_id),
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
    for a in _student_only(_load_assignments(db, owner_id)):
        if a.due_at is None or not (start <= a.due_at <= end):
            continue
        grouped.setdefault(a.due_at.date().isoformat(), []).append(a)
    return {"from": start.isoformat(), "to": end.isoformat(), "days": grouped}


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


@router.get("/status", response_model=SyncStatus)
def status(
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> SyncStatus:
    # Signed-in state of the CALLING user (§16): hosted reads the session
    # user, desktop the loopback account — never a global login state, and
    # never a Google profile lookup (identity is exposed via /auth/status
    # and /api/me only, §26).
    owner_id = user.id
    # Structured per-user sync state (migration stage 5, §18): the
    # dashboard sees a short status plus the last successful time — never
    # an exception trace (the stored message is already sanitized).
    sync_state = sync.sync_status(db, owner_id)
    return SyncStatus(
        authenticated=_is_authenticated(user),
        last_sync=sync_state.last_success_at if sync_state else None,
        last_sync_error=sync_state.last_error if sync_state else None,
        # A queued job is active from the moment it is requested. The status
        # row remains ``pending`` until the worker claims it, but the UI must
        # already show the spinner and follow it through completion.
        syncing=bool(
            sync_state
            and (sync_state.status == sync.SYNC_RUNNING or sync_state.sync_requested)
        ),
        sync_status=sync_state.status if sync_state else sync.SYNC_PENDING,
        last_sync_started_at=sync_state.last_started_at if sync_state else None,
        last_sync_finished_at=sync_state.last_finished_at if sync_state else None,
        # ADR-0032: the same threshold `?restart=true` enforces, published so
        # the dashboard's stuck verdict is the server's, not a second guess.
        sync_stuck_after_seconds=SYNC_STUCK_SECONDS,
        # Aggregated in SQL, not by loading every table: the frontend polls
        # this endpoint every ~1.5 s while signing in (review §2.1 / §1.3).
        **_student_totals_sql(db, owner_id),
    )


@router.post("/sync", response_model=SyncResult)
def run_sync(
    request: Request,
    restart: bool = Query(
        default=False,
        description="Abandon a stuck sync and start a new one (ADR-0032).",
    ),
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> SyncResult:
    """Queue (hosted) or run (desktop) a sync of the calling user's cache.

    §12: /api/sync must never touch another user's data. Desktop: the local
    owner (token.json) — sync runs inline as before. Hosted: the session
    user's oauth_tokens — the request only flags ``sync_requested`` and
    answers ``{"ok": True, "queued": True, "status": "queued"}`` immediately;
    the worker container performs the actual Classroom fan-out (DDoS plan
    §9: never run the full sync inside the HTTP request).

    Hosted conflict mapping: a sync already in flight for THIS user → 409;
    a manual request inside the per-user cooldown → 429 + Retry-After; the
    background scheduler bypasses the cooldown. Other users sync
    independently. Rate-limit buckets (§39) stay in middleware.

    ``restart=true`` (ADR-0032) is the dashboard's answer to "this sync is
    stuck". It is the ONE case where an in-flight sync does not answer 409: a
    claim older than ``SYNC_STUCK_SECONDS`` is released and a new one queued.
    A younger claim still answers 409 — a long but progressing Classroom
    import must never be interrupted, and the cooldown is skipped only because
    the abandoned claim is by definition older than it.
    """
    if restart and _is_sync_running(db, user.id):
        # Hosted and desktop differ only in who performs the work, so the
        # restart decision is made once, before the branch below.
        if request.app.state.hosted:
            if not sync.restart_stuck_sync(db, user.id):
                raise HTTPException(
                    status_code=409,
                    detail="This synchronization is still running; try again later.",
                )
            return SyncResult(ok=True, queued=True, status="queued", restarted=True)
        return _restart_desktop_sync(user, db)
    # With no claim in flight there is nothing to abandon: `restart=true` falls
    # through to the ordinary request below rather than answering 409 about a
    # sync that does not exist.

    if request.app.state.hosted:
        from config import SYNC_MANUAL_COOLDOWN_SECONDS
        from sync_store import sync_status as _sync_row

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        row = _sync_row(db, user.id)
        if row is not None and row.status == sync.SYNC_RUNNING:
            # A running sync is not an error: 409 tells the client to keep
            # showing its spinner instead of surfacing a failure (§3.9).
            raise HTTPException(
                status_code=409, detail="A synchronization is already running."
            )
        if (
            SYNC_MANUAL_COOLDOWN_SECONDS > 0
            and row is not None
            and row.last_started_at is not None
            and (now - row.last_started_at).total_seconds()
            < SYNC_MANUAL_COOLDOWN_SECONDS
        ):
            raise HTTPException(
                status_code=429,
                detail="A sync just ran for this account; try again shortly.",
                headers={"Retry-After": str(SYNC_MANUAL_COOLDOWN_SECONDS)},
            )
        sync.request_sync(db, user.id)
        return SyncResult(ok=True, queued=True, status="queued")
    result = sync.sync_now(user=user, interactive=True)
    if not result.get("ok"):
        error = str(result.get("error", ""))
        if "already running" in error:
            # A running sync is not an error: 409 tells the client to keep
            # showing its spinner instead of surfacing a failure (§3.9).
            raise HTTPException(
                status_code=409, detail="A synchronization is already running."
            )
        if error == sync.SERVER_BUSY:
            raise HTTPException(status_code=503, detail=error)
    return SyncResult(**result)


def _is_sync_running(db: Session, user_id: int) -> bool:
    """Whether the calling user currently has a claimed sync in flight.

    The gate in front of every restart: a claim is what can be abandoned, and
    without one the request is an ordinary sync no matter which flag it carried.
    """
    row = sync.sync_status(db, user_id)
    return row is not None and row.status == sync.SYNC_RUNNING


def _restart_desktop_sync(user: User, db: Session) -> SyncResult:
    """Restart a stuck sync on desktop, where the sync runs inline (ADR-0032).

    Desktop has no queue and no separate worker: ``sync_now`` claims the row
    itself, so the restart is "release the stale claim, then run". Releasing
    first is what makes the retry possible at all — otherwise the new attempt
    would hit the very claim it is meant to replace.

    When the hung thread still holds the in-process per-user lock, the stale
    claim IS released but no second fan-out can start here; the next attempt
    (the user's click, or the desktop background schedule) proceeds normally.
    That case answers 409 with a message saying so — it is not a failed
    restart, and the dashboard keeps watching the status row either way.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not sync.abandon_claim(db, user.id, now, older_than=SYNC_STUCK_SECONDS):
        metrics.record(metrics.SYNC_RESTART_REJECTED)
        raise HTTPException(
            status_code=409,
            detail="This synchronization is still running; try again later.",
        )
    metrics.record(metrics.SYNC_RESTARTED)
    result = sync.sync_now(user=user, interactive=True)
    if not result.get("ok") and "already running" in str(result.get("error", "")):
        # The claim is free again, but the hung thread still owns the in-process
        # lock. Say so plainly instead of surfacing a generic failure.
        raise HTTPException(
            status_code=409,
            detail="The previous synchronization is still shutting down; "
            "try again in a moment.",
        )
    return SyncResult(**result, restarted=True)


@router.delete("/cache")
def clear_cache(
    confirm: bool = Query(default=False),
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to clear all locally cached data.",
        )
    # Deletes only the calling user's cache rows (stage 3; audit P4/Y4).
    sync.reset_cache(db, owner_id)
    return {"ok": True, "cleared": True}


@router.delete("/me/cache")
def clear_own_cache(
    confirm: bool = Query(default=False),
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    """Explicit alias of ``DELETE /api/cache`` (stage 9, §66).

    Same handler shape, same per-user scope, same ``confirm=true`` gate —
    the path only says what the code already does: delete the CALLER's
    cache, never anyone else's. Kept side by side with ``/api/cache`` so
    existing desktop clients keep working while new clients can use the
    unambiguous name.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to clear all locally cached data.",
        )
    sync.reset_cache(db, owner_id)
    return {"ok": True, "cleared": True}


@router.delete("/me/google")
def disconnect_google_account(
    confirm: bool = Query(default=False),
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Disconnect the caller's Google account, keep the local account (§44).

    Removes the stored OAuth credentials and resets the caller's sync state
    of THIS user only; the application session stays valid (the caller
    stays signed in to the dashboard and its cached data remains visible,
    with its last-sync timestamp). ``confirm=true`` is required because the
    action forces a fresh consent screen on the next sync.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to disconnect the Google account.",
        )
    # Desktop has no application account: this is exactly /api/auth/logout.
    if user.provider != "google":
        import auth

        auth.logout()
        _reset_profile_cache(user.id)
        return {"ok": True, "disconnected": True}
    maintenance.disconnect_google(db, user.id)
    _reset_profile_cache(user.id)
    return {"ok": True, "disconnected": True}


@router.delete("/me")
def delete_own_account(
    request: Request,
    confirm: bool = Query(default=False),
    user: User = Depends(ownership.get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Delete everything stored for the CALLER (§44).

    The explicit "delete my account" path: sessions, OAuth credentials,
    sync state and the whole Classroom cache of this user are removed, and
    the local ``users`` row goes with them. Other users' rows are never
    touched — there is deliberately no global variant of this operation.

    Desktop builds have no server-side account (single local user, data in
    ``%LOCALAPPDATA%``): the endpoint is hosted-only and answers 400 there
    with a pointer to ``DELETE /api/cache`` + logout.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to delete the account and all cached data.",
        )
    if not request.app.state.hosted:
        raise HTTPException(
            status_code=400,
            detail=(
                "Desktop builds have no server-side account; use "
                "DELETE /api/cache and sign out instead."
            ),
        )
    removed = maintenance.delete_user_data(db, user)
    _reset_profile_cache(user.id)
    response = JSONResponse({"ok": True, "deleted": True, **removed})
    # The session no longer exists server-side; drop the cookie too so the
    # browser does not keep presenting a dead token (§37).
    from hosted_auth import SESSION_COOKIE_NAME

    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


# ------------------------------------------------------- teacher-mode views


def _get_course(db: Session, owner_id: int, course_id: str) -> Course:
    """The owner's course by id; ARCHIVED and missing courses are 404."""
    course = db.get(Course, (owner_id, course_id))
    if course is None or course.course_state == "ARCHIVED":
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


def _course_role(db: Session, owner_id: int, course: Course) -> str:
    """Role of the cache owner in this course ("TEACHER"/"STUDENT")."""
    row = db.get(CourseRole, (owner_id, course.id))
    return row.role if row else "STUDENT"


def _require_teacher(db: Session, owner_id: int, course: Course) -> None:
    """Teacher-only endpoints must never be reachable from a student course."""
    if _course_role(db, owner_id, course) != "TEACHER":
        raise HTTPException(
            status_code=403,
            detail="This course is not taught by the signed-in user.",
        )


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
    if _course_role(db, owner_id, course) != "TEACHER":
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


@router.get("/courses/{course_id}", response_model=CourseDetailOut)
def course_detail(
    course_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> CourseDetailOut:
    course = _get_course(db, owner_id, course_id)
    stats = _course_stats_sql(db, owner_id)
    role = _course_role(db, owner_id, course)
    # §21: the roster is teacher-only data. A student course has no roster
    # rows to begin with; gating on the role also keeps rows left over from
    # a former teaching period out of the response.
    students = (
        [_student_out(row) for row in _roster_rows(db, owner_id, course_id)]
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
    _get_course(db, owner_id, course_id)
    return [a for a in _load_assignments(db, owner_id) if a.course_id == course_id]


@router.get("/courses/{course_id}/students", response_model=list[StudentOut])
def course_students(
    course_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> list[StudentOut]:
    course = _get_course(db, owner_id, course_id)
    _require_teacher(db, owner_id, course)
    return [_student_out(row) for row in _roster_rows(db, owner_id, course_id)]


@router.get("/courses/{course_id}/grades", response_model=TeacherGradesOut)
def course_grades(
    course_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> TeacherGradesOut:
    """Spreadsheet-style grade matrix: every student × every assignment."""
    course = _get_course(db, owner_id, course_id)
    _require_teacher(db, owner_id, course)
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
    for student in _roster_rows(db, owner_id, course_id):
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
        last_sync=sync.last_sync_time(db, owner_id),
    )


@router.get(
    "/courses/{course_id}/coursework/{coursework_id}",
    response_model=AssignmentDetailOut,
)
def coursework_detail(
    course_id: str,
    coursework_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> AssignmentDetailOut:
    """Full assignment page: metadata, materials and the submission table."""
    course = _get_course(db, owner_id, course_id)
    work = db.get(CourseWork, (owner_id, coursework_id))
    if work is None or work.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    base = _assignment_by_id(
        db, owner_id, coursework_id
    )  # PK lookup, not a full scan (§2.1)
    if base is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    submissions = _submissions_for_work(db, owner_id, course, work)
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
    course_id: str,
    coursework_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> list[SubmissionOut]:
    course = _get_course(db, owner_id, course_id)
    work = db.get(CourseWork, (owner_id, coursework_id))
    if work is None or work.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    return _submissions_for_work(db, owner_id, course, work)


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
    course = _get_course(db, owner_id, course_id)
    is_teacher = _course_role(db, owner_id, course) == "TEACHER"
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
        _student_out(roster_row, student_id) if is_teacher else StudentOut(id="me")
    )
    works = sorted(
        db.query(CourseWork).filter_by(user_id=owner_id, course_id=course_id).all(),
        key=lambda work: (work.due_at is None, work.due_at or datetime.max),
    )
    sub_map = _grade_submissions(db, owner_id, course_id, student_id, is_teacher)
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
