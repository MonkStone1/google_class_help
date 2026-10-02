"""The Google side of one sync: what to ask for, and how to ask it.

Split out of ``sync/service/_fetch.py`` (ADR-0039) because talking to Classroom
is where the quotas, the retries and the fan-out live, and none of that belongs
next to the claim handling that decides WHETHER to sync.

The client is thread-local, not global. A sync runs several Classroom calls in
parallel and ``googleapiclient`` services carry per-request state (the HTTP
adapter, the credential refresh lock); sharing one across threads is how a
credential refresh ends up racing itself. One client per thread, built once.

Every list call is paged here rather than in the caller, so ``RequestStats``
sees the real request count — that number is what the capacity review reads,
and it is only truthful if the pagination lives next to the counter.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from gapi.classroom import ClassroomClient, RequestStats, build_service

logger = logging.getLogger(__name__)

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

    def fetch_teachers(course_id: str, role: str) -> tuple[str, list[str]]:
        # Only a teacher may read the roster of teachers. Asking a STUDENT
        # course answers HTTP 500 (not 403), and googleapiclient treats a 5xx
        # as retryable: every such course burned three backoff retries before
        # finally degrading to an empty list. On a 23-student-course account
        # that was 23 pointless requests and ~20s of the sync, and it is the
        # single largest avoidable cost in the fan-out — the returned list is
        # dropped for these courses anyway.
        if role != "TEACHER":
            return course_id, []
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
        raw["id"]: pool.submit(fetch_teachers, raw["id"], role) for raw, role in courses
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
