"""Sync orchestration: pull data from Google and hand it to sync_store
(review §2.2). Transport lives in classroom_api.py, cache writing in
sync_store.py, domain rules in grading.py.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.orm import Session

import auth
import ownership
from classroom_api import ClassroomClient, build_service
from config import SYNC_MAX_WORKERS
from database import SessionLocal
from models import Course, CourseRole
from sync_store import (
    _purge_stale_courses,
    _set_state,
    _write_student_course,
    _write_teacher_course,
)

logger = logging.getLogger(__name__)

_SYNC_LOCK = threading.Lock()


def sync_now() -> dict:
    """Pull all courses, coursework and submissions from Google into the cache.

    Safe to call concurrently: a second caller is told a sync is already
    running instead of duplicating requests.
    """
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "A synchronization is already running."}
    try:
        return _do_sync()
    finally:
        _SYNC_LOCK.release()


def _thread_local_client(credentials) -> Callable[[], ClassroomClient]:
    """Return a getter that builds one ClassroomClient per worker thread.

    httplib2 and the discovery service are not thread-safe, so workers must
    never share a client; each thread builds its own on first use and reuses
    it for every task it runs afterwards.
    """
    local = threading.local()

    def get_client() -> ClassroomClient:
        client = getattr(local, "client", None)
        if client is None:
            client = ClassroomClient(build_service(credentials))
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


def _do_sync() -> dict:
    creds = auth.get_valid_credentials()
    if creds is None:
        return {"ok": False, "error": "Not signed in to Google."}

    service = build_service(creds)
    client = ClassroomClient(service)

    db: Session = SessionLocal()
    # The cache rows written by this sync belong to one user (migration
    # stage 3, §10): the desktop build's single local owner. Per-user
    # credentials/jobs for the hosted service arrive with stage 5.
    owner_id = ownership.local_owner_id(db)
    # One shared pool for every network stage (per-course lists and the point
    # courseWork.get lookups): threads and their per-thread API clients are
    # built once and reused instead of once per course. All database work
    # stays on this thread — SQLAlchemy sessions are not thread-safe.
    # 429s are absorbed by execute(num_retries) backoff, so exceeding the
    # per-user quota briefly only slows down, never fails the sync.
    pool = ThreadPoolExecutor(max_workers=SYNC_MAX_WORKERS)
    try:
        courses = _resolve_courses(client)
        if courses is None:
            # courses.list failed (HTTP error): keep the cache and record the
            # error instead of purging every course as "gone" (review §1.7).
            message = "Classroom courses.list failed; cached data kept."
            logger.warning(message)
            db.rollback()
            _set_state(db, owner_id, "last_sync_error", message)
            return {"ok": False, "error": message}
        active_ids = {raw["id"] for raw, _ in courses}

        get_client = _thread_local_client(creds)
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
        now = datetime.now(  # noqa: DTZ005 - naive local time is intentional (cache stores naive datetimes)
        )

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

        _set_state(db, owner_id, "last_sync", now.isoformat())
        _set_state(db, owner_id, "last_sync_error", None)
        return {
            "ok": True,
            "last_sync": now,
            "courses": len(courses),
            "assignments": assignment_count,
        }
    except (
        Exception
    ) as exc:  # any Google/network error must land in sync_state, not crash the API
        # The dashboard gets the short message below; the log keeps the whole
        # stack, which is the only artifact a user can send from a build that
        # fails on a platform we do not have (e.g. the exe under Wine).
        logger.exception("Classroom sync failed")
        db.rollback()
        message = f"{exc.__class__.__name__}: {exc}"
        _set_state(db, ownership.local_owner_id(db), "last_sync_error", message)
        return {"ok": False, "error": message}
    finally:
        pool.shutdown(wait=True)
        db.close()
