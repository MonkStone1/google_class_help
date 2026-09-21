"""Sync orchestration: pull data from Google and hand it to sync_store
(review §2.2). Transport lives in classroom_api.py, cache writing in
sync_store.py, domain rules in grading.py.

Every sync belongs to ONE user (migration stage 4, §12): the owner is
resolved from the authenticated user, and the Google credentials come
from the user-scoped credential layer (google_credentials.py, §15) —
never from a process-global token state.

Multi-user scheduling (migration stage 5, §18): concurrency is controlled
PER USER, not per process. Two different users may sync at the same time;
the same user may not — an in-process per-user lock serializes threads of
this process, and a conditional UPDATE on ``sync_status`` (sync_store
.claim_sync) serializes whole worker containers. Every run records its
start/finish/success/error into that user's ``sync_status`` row, and the
error text kept there is a short user-facing sentence — raw exception
text and stack traces stay in the server log (§18).
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import google_credentials
from sqlalchemy.orm import Session

import ownership
from classroom_api import ClassroomClient, RequestStats, build_service
from config import (
    SYNC_CLAIM_STALE_SECONDS,
    SYNC_MAX_CONCURRENT_USERS,
    SYNC_MAX_WORKERS,
)
from database import SessionLocal
from models import Course, CourseRole
from models_auth import User
from sync_store import (
    _purge_stale_courses,
    _write_student_course,
    _write_teacher_course,
    claim_sync,
    mark_sync_failed,
    mark_sync_needs_reauth,
    mark_sync_pending,
    mark_sync_succeeded,
)

logger = logging.getLogger(__name__)

# Returned when this user already has a sync in flight. The exact wording
# is part of the API contract: api.py maps it to HTTP 409 (review §3.9).
ALREADY_RUNNING = "A synchronization is already running."
NOT_SIGNED_IN = "Not signed in to Google."
NEEDS_REAUTH = "Google authorization expired; please sign in again."
COURSES_FAILED = "Classroom courses.list failed; cached data kept."
# Returned when every global sync slot is taken (§65). api.py maps it to 503.
SERVER_BUSY = "The server is busy synchronizing other accounts; try again shortly."

# Per-user sync mutexes (stage 5, §18). A process-global lock would
# serialize every user; keying by owner id lets independent accounts sync
# in parallel while the same account is still protected from running
# twice. The registry itself is guarded; entries are tiny and survive for
# the process lifetime, which also keeps a lock object stable for callers.
_sync_locks_guard = threading.Lock()
_sync_locks: dict[int, threading.Lock] = {}


# Global concurrency of INTERACTIVE (user-triggered) syncs (§65). The
# per-user pool bounds one account's request fan-out (SYNC_MAX_WORKERS);
# this bounds how many accounts run at once so a burst of "Sync now" clicks
# after a deploy cannot open N pools of workers. Scheduled/background syncs
# are already bounded by the scheduler's own pool (stage 5) and are not
# counted here. The counter is per process; the supported deployment runs a
# single worker plus the web replicas, each with this ceiling.
_slots_lock = threading.Lock()
_active_interactive = 0


def _acquire_interactive_slot() -> bool:
    """Take one global interactive slot, or fail immediately (§65)."""
    global _active_interactive
    with _slots_lock:
        if _active_interactive >= SYNC_MAX_CONCURRENT_USERS:
            return False
        _active_interactive += 1
        return True


def _release_interactive_slot() -> None:
    global _active_interactive
    with _slots_lock:
        _active_interactive -= 1


def _sync_lock_for(user_id: int) -> threading.Lock:
    with _sync_locks_guard:
        return _sync_locks.setdefault(user_id, threading.Lock())


def sync_now(user: User | None = None, *, interactive: bool = False) -> dict:
    """Pull a user's Classroom data into that user's cache scope (§12/§18).

    ``user`` is the authenticated user whose cache to refresh — the
    session user on the hosted service, the local owner on desktop
    (``None`` keeps the desktop background path unchanged). Safe to call
    concurrently: the same user's second caller is told a sync is already
    running instead of duplicating requests, while another user's caller
    proceeds independently.

    ``interactive=True`` (the user-triggered ``POST /api/sync``) also takes
    one of the process's global slots (§65): when ``SYNC_MAX_CONCURRENT_USERS``
    interactive syncs are already running the call returns SERVER_BUSY
    instead of stacking another pool of workers. Scheduled and background
    syncs pass the default — the scheduler already bounds them.
    """
    if interactive and not _acquire_interactive_slot():
        return {"ok": False, "error": SERVER_BUSY}
    try:
        if user is not None:
            owner_id = user.id
        else:
            with SessionLocal() as db:
                owner = ownership.ensure_local_owner(db)
                owner_id = owner.id
                # The synthetic owner is created by this very call on the first
                # desktop run; committing here is what makes it survive the
                # session close — otherwise _do_sync would reload nothing and
                # every background run would report "Not signed in to Google".
                db.commit()
        lock = _sync_lock_for(owner_id)
        if not lock.acquire(blocking=False):
            return {"ok": False, "error": ALREADY_RUNNING}
        try:
            return _do_sync(owner_id)
        finally:
            lock.release()
    finally:
        if interactive:
            _release_interactive_slot()


def sync_user_id(user_id: int) -> dict:
    """Sync one user by id — the scheduler/worker entry point (stage 5).

    The scheduler selects users from the database without loading their ORM
    objects; this resolves the row for :func:`sync_now`, which then applies
    the same per-user locking and state transitions as a manual sync.
    """
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return {"ok": False, "error": NOT_SIGNED_IN}
        # Detach before the session closes: sync_now only reads ``id``.
        db.expunge(user)
    return sync_now(user=user)


def _thread_local_client(
    credentials, stats: RequestStats | None = None
) -> Callable[[], ClassroomClient]:
    """Return a getter that builds one ClassroomClient per worker thread.

    httplib2 and the discovery service are not thread-safe, so workers must
    never share a client; each thread builds its own on first use and reuses
    it for every task it runs afterwards.
    """
    local = threading.local()

    def get_client() -> ClassroomClient:
        client = getattr(local, "client", None)
        if client is None:
            client = ClassroomClient(build_service(credentials), stats=stats)
            local.client = client
        return client

    return get_client


def _resolve_courses(
    client: ClassroomClient,
) -> list[tuple[dict, str]] | None:
    """Return ``(raw_course, role)`` for every non-archived course.

    Role is per course, because one Google account can teach some courses and
    study in others (section 2 of the teacher spec). ``courses.list`` is
    filtered by role to find the teacher set; anything else stays on the
    student route, so a course visible through some other membership (e.g. a
    domain admin) behaves exactly as before.

    Returns ``None`` when either list call failed (review §1.7): the caller
    keeps the cache instead of mistaking an error for an empty account and
    purging every course.
    """
    courses = client.list_courses()
    if courses is None:
        return None
    teacher_list = client.list_courses(teacher_id="me")
    if teacher_list is None:
        return None
    teacher_ids = {raw["id"] for raw in teacher_list}
    return [
        (raw, "TEACHER" if raw["id"] in teacher_ids else "STUDENT")
        for raw in courses
        if raw.get("courseState") != "ARCHIVED"
    ]


def _fetch_course_payloads(
    get_client: Callable[[], ClassroomClient],
    courses: list[tuple[dict, str]],
    pool: ThreadPoolExecutor,
) -> tuple[dict[str, list[str]], dict[str, dict]]:
    """Fetch every per-course list in parallel through one shared pool.

    Teacher and student courses hit different endpoints:

    - teacher: ``courseWork.list`` (ALL coursework), ``students.list``
      (roster) and ``studentSubmissions.list`` for all students;
    - student: only their own submissions, later expanded by point
      ``courseWork.get`` calls (ADR-0010).

    Teacher list methods return ``None`` on an HTTP error so the writer can
    keep cached data instead of mistaking an error for an empty course.
    """

    def fetch_teachers(course_id: str) -> tuple[str, list[str]]:
        return course_id, [
            teacher.get("fullName", "")
            for teacher in get_client().list_teachers(course_id)
            if teacher.get("fullName")
        ]

    def fetch_payload(course_id: str, role: str) -> tuple[str, dict]:
        client = get_client()
        if role == "TEACHER":
            return course_id, {
                "role": role,
                "coursework": client.list_coursework(course_id, ["PUBLISHED", "DRAFT"]),
                "students": client.list_students(course_id),
                "submissions": client.list_all_submissions(course_id),
            }
        return course_id, {
            "role": role,
            "submissions": client.list_submissions_for_course(course_id),
        }

    teacher_futures = {
        raw["id"]: pool.submit(fetch_teachers, raw["id"]) for raw, _ in courses
    }
    payload_futures = {
        raw["id"]: pool.submit(fetch_payload, raw["id"], role) for raw, role in courses
    }
    teacher_names = dict(future.result() for future in teacher_futures.values())
    payloads = dict(future.result() for future in payload_futures.values())
    return teacher_names, payloads


def _fetch_coursework(
    get_client: Callable[[], ClassroomClient],
    work_requests: list[tuple[str, str]],
    pool: ThreadPoolExecutor,
) -> dict[tuple[str, str], dict]:
    """Fetch assignment details for many (course, work) pairs in parallel.

    Students can only read coursework one item at a time (courseWork.get),
    so a course with dozens of assignments needs hundreds of small requests.
    All courses share one thread pool here, so the pool never idles at a
    course boundary; workers build their client once per sync, not once per
    course.
    """

    def fetch(pair: tuple[str, str]) -> tuple[tuple[str, str], dict]:
        course_id, work_id = pair
        return pair, get_client().get_coursework(course_id, work_id)

    results: dict[tuple[str, str], dict] = {}
    for pair, raw_work in pool.map(fetch, work_requests):
        if raw_work:
            results[pair] = raw_work
    return results


def _now() -> datetime:
    """Naive UTC — the timestamp convention of every user-scoped table."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _public_error(exc: Exception) -> str:
    """Short, user-safe description of a failed sync (§18).

    Raw exception text (Google's HTTP error body, request URLs, payload
    fragments) stays in the log; the dashboard only needs to know how to
    react. The HTTP status is read defensively: ``googleapiclient`` errors
    expose ``resp.status``, anything else falls back to a generic sentence
    that carries no exception detail at all.
    """
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 401:
        return NEEDS_REAUTH
    if status == 403:
        return "Google denied access to Classroom data; please sign in again."
    if status == 429:
        return "Google rate limit reached; the next sync will retry."
    if isinstance(status, int):
        return f"Google API error (HTTP {status}); the next sync will retry."
    return "Sync failed; see the server log for details."


def _do_sync(owner_id: int) -> dict:
    db: Session = SessionLocal()
    pool = ThreadPoolExecutor(max_workers=SYNC_MAX_WORKERS)
    # One per-run counter shared by every worker thread's client (§65): it
    # makes the real Google request volume of a sync (much higher for a
    # teacher account) visible in the log for capacity planning (stage 9).
    stats = RequestStats()
    started_monotonic = time.monotonic()
    try:
        user = db.get(User, owner_id)
        if user is None or not user.is_active:
            return {"ok": False, "error": NOT_SIGNED_IN}
        # Claim this user's sync slot before any network work (stage 5, §18):
        # the conditional UPDATE also excludes a job another worker container
        # already started for the same account.
        started_at = _now()
        if not claim_sync(
            db, owner_id, started_at, stale_after=SYNC_CLAIM_STALE_SECONDS
        ):
            return {"ok": False, "error": ALREADY_RUNNING}
        # The cache rows written by this sync belong to this user (§10);
        # the credentials are that same user's (§15) — hosted users read
        # their own oauth_tokens row, desktop its single token.json.
        creds = google_credentials.get_google_credentials(db, user)
        if creds is None:
            # Distinguish "never signed in" from "the stored grant is
            # unusable": only the latter pauses scheduled sync (§63).
            if google_credentials.has_google_grant(db, user):
                mark_sync_needs_reauth(db, owner_id, NEEDS_REAUTH, _now())
                return {"ok": False, "error": NEEDS_REAUTH}
            mark_sync_pending(db, owner_id, _now())
            return {"ok": False, "error": NOT_SIGNED_IN}

        service = build_service(creds)
        client = ClassroomClient(service, stats=stats)

        # One shared pool for every network stage (per-course lists and the
        # point courseWork.get lookups): threads and their per-thread API
        # clients are built once and reused instead of once per course. All
        # database work stays on this thread — SQLAlchemy sessions are not
        # thread-safe. 429s are absorbed by execute(num_retries) backoff,
        # so exceeding the per-user quota briefly only slows down, never
        # fails the sync.
        courses = _resolve_courses(client)
        if courses is None:
            # courses.list failed (HTTP error): keep the cache and record the
            # error instead of purging every course as "gone" (review §1.7).
            logger.warning(COURSES_FAILED)
            db.rollback()
            mark_sync_failed(db, owner_id, COURSES_FAILED, _now())
            return {"ok": False, "error": COURSES_FAILED}
        active_ids = {raw["id"] for raw, _ in courses}

        get_client = _thread_local_client(creds, stats)
        teacher_names, payloads = _fetch_course_payloads(get_client, courses, pool)

        # Student courses discover coursework via their submissions and then
        # fetch each assignment individually (courseWork.list is teacher-only
        # for them — ADR-0010). Teacher courses already got the full list in
        # the payload stage above.
        work_requests: list[tuple[str, str]] = []
        for raw_course, role in courses:
            if role != "STUDENT":
                continue
            course_id = raw_course["id"]
            seen: set[str] = set()
            for raw_sub in payloads[course_id]["submissions"]:
                work_id = raw_sub.get("courseWorkId")
                if work_id and work_id not in seen:
                    seen.add(work_id)
                    work_requests.append((course_id, work_id))
        work_cache = _fetch_coursework(get_client, work_requests, pool)

        assignment_count = 0
        now = _now()

        for raw_course, role in courses:
            course_id = raw_course["id"]
            course = db.get(Course, (owner_id, course_id))
            if course is None:
                course = Course(user_id=owner_id, id=course_id)
                db.add(course)
            course.name = raw_course.get("name", "Untitled course")
            course.description = raw_course.get("descriptionHeading") or raw_course.get(
                "description"
            )
            course.section = raw_course.get("section")
            course.room = raw_course.get("room")
            course.enrollment_state = raw_course.get("enrollmentState")
            course.course_state = raw_course.get("courseState")
            course_role = db.get(CourseRole, (owner_id, course_id))
            if course_role is None:
                course_role = CourseRole(user_id=owner_id, course_id=course_id)
                db.add(course_role)
            course_role.role = role
            course.teacher_names = teacher_names.get(course_id, [])
            course.synced_at = now

            payload = payloads[course_id]
            if role == "TEACHER":
                assignment_count += _write_teacher_course(
                    db, owner_id, course_id, payload
                )
            else:
                assignment_count += _write_student_course(
                    db, owner_id, course_id, payload["submissions"], work_cache
                )
            db.commit()

        # Mirror cleanup: archived, deleted and unenrolled courses are no
        # longer part of the student dashboard. Anything the API did not
        # return for THIS owner's cache on this sync is removed from it.
        _purge_stale_courses(db, owner_id, active_ids)

        mark_sync_succeeded(db, owner_id, _now())
        elapsed = time.monotonic() - started_monotonic
        logger.info(
            "Sync ok user=%s courses=%d assignments=%d google_requests=%d "
            "duration=%.1fs",
            owner_id,
            len(courses),
            assignment_count,
            stats.requests,
            elapsed,
        )
        return {
            "ok": True,
            "last_sync": now,
            "courses": len(courses),
            "assignments": assignment_count,
        }
    except (
        Exception
    ) as exc:  # any Google/network error must land in sync_status, not crash the API
        # The dashboard gets the short, sanitized sentence below; the log
        # keeps the whole stack, which is the only artifact a user can send
        # from a build that fails on a platform we do not have (e.g. the exe
        # under Wine). Raw exception text never reaches the frontend (§18).
        logger.exception(
            "Classroom sync failed after %d Google requests", stats.requests
        )
        db.rollback()
        message = _public_error(exc)
        mark_sync_failed(db, owner_id, message, _now())
        return {"ok": False, "error": message}
    finally:
        pool.shutdown(wait=True)
        db.close()
