"""Thin wrapper around the official Google Classroom API client.

Everything specific to talking to Google lives here: pagination, response
shapes, and date parsing. The rest of the application never imports the
googleapiclient package directly.
"""

from datetime import datetime
from threading import Lock
from typing import Any

import httplib2
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

REQUEST_TIMEOUT_SECONDS = 30

# Retries for transient errors: 429/RESOURCE_EXHAUSTED, 5xx, rate-limit 403
# and socket errors. googleapiclient backs off exponentially with jitter,
# which also self-throttles us under the per-user quota (20 QPS) when many
# workers run in parallel.
NUM_RETRIES = 3


class RequestStats:
    """Thread-safe counter of the Google requests one sync performs (§65).

    Teacher mode fans out to far more requests than the student view (every
    course's coursework, roster and all submissions). The counter makes that
    volume observable in the sync log without putting anything into the
    cached data or the API response. Clients are built per worker thread, so
    the counter is shared across them and guards its own state.

    Stage 9 (§60): quota-relevant failures get their own counters — 429
    (per-user and per-project quota) and 5xx (Classroom-side) — so the
    capacity review (ADR-0027) can tell "we hit the quota" apart from
    "Google was down" without grepping tracebacks.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self.requests = 0
        self.quota_errors = 0
        self.server_errors = 0

    def record(self) -> None:
        with self._lock:
            self.requests += 1

    def record_quota_error(self) -> None:
        with self._lock:
            self.quota_errors += 1

    def record_server_error(self) -> None:
        with self._lock:
            self.server_errors += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "requests": self.requests,
                "quota_errors": self.quota_errors,
                "server_errors": self.server_errors,
            }


def _classify_http_status(status: int | None) -> str | None:
    """Map an HttpError status to the stats bucket that owns it (§60)."""
    if status == 429:
        return "quota"
    if status is not None and 500 <= status <= 599:
        return "server"
    # Quota-exhaustion 403s carry one of these reasons in the payload.
    return None


def _is_quota_403(error: HttpError) -> bool:
    """Whether a 403 is really quota exhaustion (retryable, §40)."""
    try:
        content = error.content
        text = content.decode("utf-8", "ignore") if isinstance(content, bytes) else ""
    except Exception:  # noqa: BLE001 - classification must never raise
        return False
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "ratelimitexceeded",
            "quotaexceeded",
            "userratelimitexceeded",
            "resource_exhausted",
        )
    )


def build_service(credentials) -> Any:
    """Build the Classroom discovery client with a socket timeout.

    google-api-python-client 2.x removed the ``timeout`` argument from
    ``HttpRequest.execute()``, so the timeout is configured on the HTTP
    transport instead (a hung socket must not freeze a sync forever).
    """
    http = AuthorizedHttp(
        credentials, http=httplib2.Http(timeout=REQUEST_TIMEOUT_SECONDS)
    )
    return build("classroom", "v1", http=http, cache_discovery=False)


def parse_date(raw: dict | None) -> datetime | None:
    """Parse a Classroom API ``Date`` object into a naive datetime."""
    if not raw:
        return None
    try:
        return datetime(  # noqa: DTZ001 - naive local dates: the whole cache stores naive datetimes
            raw["year"], raw["month"], raw["day"]
        )
    except (KeyError, TypeError, ValueError):
        return None


def parse_date_time(date_raw: dict | None, time_raw: dict | None) -> datetime | None:
    """Parse ``dueDate`` + ``dueTime`` into a naive local datetime.

    Classroom returns dates without a timezone; for a personal local
    application the due moment is interpreted in local time.
    """
    date_part = parse_date(date_raw)
    if not date_part:
        return None
    hours = 23
    minutes = 59
    if time_raw:
        try:
            hours = int(time_raw.get("hours", 23))
            minutes = int(time_raw.get("minutes", 59))
        except (TypeError, ValueError):
            pass
    return date_part.replace(hour=hours, minute=minutes)


def parse_rfc3339(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


class ClassroomClient:
    """All Google Classroom API access used by the dashboard.

    The discovery ``Resource`` exposes endpoints dynamically, so it is typed
    as ``Any``.
    """

    def __init__(self, service: Any, stats: RequestStats | None = None) -> None:
        self._service = service
        # Optional observability counter shared by one sync's worker threads
        # (§65); None keeps the client usable without instrumentation.
        self._stats = stats

    def _execute(self, request: Any) -> dict:
        """Execute one prepared request with the shared retry policy (§65).

        The single choke point for every Classroom call: it applies
        googleapiclient's exponential backoff (``num_retries``) and, when a
        :class:`RequestStats` was supplied, counts the request so a sync can
        log its real API volume. Stage 9 (§60): HttpError statuses are also
        classified into quota/server counters before propagating, so the
        log line tells quota pressure apart from Classroom outages.
        """
        if self._stats is not None:
            self._stats.record()
        try:
            return request.execute(num_retries=NUM_RETRIES)
        except HttpError as exc:
            if self._stats is not None:
                status = getattr(getattr(exc, "resp", None), "status", None)
                bucket = _classify_http_status(status)
                if bucket == "quota" or (status == 403 and _is_quota_403(exc)):
                    self._stats.record_quota_error()
                elif bucket == "server":
                    self._stats.record_server_error()
            raise

    def list_courses(
        self,
        student_id: str | None = None,
        teacher_id: str | None = None,
    ) -> list[dict] | None:
        """List courses, optionally restricted to a role for the user.

        ``student_id="me"`` returns the courses where the authenticated user
        is a student, ``teacher_id="me"`` those where they teach. Both are
        paginated; the two filters are mutually exclusive on the API side,
        so callers must pass at most one of them.

        Returns ``None`` on an HTTP error so the caller keeps the cache,
        symmetric with the other list methods (review §1.7).
        """
        items: list[dict] = []
        page_token: str | None = None
        while True:
            kwargs: dict = {"pageSize": 100, "pageToken": page_token}
            if student_id:
                kwargs["studentId"] = student_id
            if teacher_id:
                kwargs["teacherId"] = teacher_id
            try:
                request = self._service.courses().list(**kwargs)
                response = self._execute(request)
            except HttpError:
                return None
            items.extend(response.get("courses", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    def list_coursework(
        self, course_id: str, course_work_states: list[str] | None = None
    ) -> list[dict] | None:
        """List every coursework item of a course (teacher view).

        Teachers see all states; students may only call this for PUBLISHED
        work (and the API returns 403 for them entirely — see ADR-0010), so
        this method is only used for teacher courses. Paginated.

        Returns ``None`` on a permission/HTTP error so callers can tell
        "could not load" apart from "no coursework" and keep cached data.
        """
        items: list[dict] = []
        page_token: str | None = None
        while True:
            kwargs: dict = {"courseId": course_id, "pageSize": 100}
            if page_token:
                kwargs["pageToken"] = page_token
            if course_work_states:
                kwargs["courseWorkStates"] = course_work_states
            try:
                request = self._service.courses().courseWork().list(**kwargs)
                response = self._execute(request)
            except HttpError:
                return None
            items.extend(response.get("courseWork", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    def list_teachers(self, course_id: str) -> list[dict]:
        """List the teachers of a course (paginated).

        Returns ``[{"userId": ..., "fullName": ...}, ...]``; the requester
        may only view teachers of courses they belong to (ADR-0010).
        """
        items: list[dict] = []
        page_token: str | None = None
        while True:
            try:
                request = (
                    self._service.courses()
                    .teachers()
                    .list(courseId=course_id, pageSize=100, pageToken=page_token)
                )
                response = self._execute(request)
            except HttpError:
                return items
            for teacher in response.get("teachers", []):
                profile = teacher.get("profile", {}) or {}
                items.append(
                    {
                        "userId": teacher.get("userId") or profile.get("id"),
                        "fullName": (profile.get("name") or {}).get("fullName", ""),
                    }
                )
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    def list_students(self, course_id: str) -> list[dict] | None:
        """List the students enrolled in a course (teacher view, paginated).

        Returns ``[{"userId", "fullName", "emailAddress", "photoUrl"}, ...]``.
        Email addresses are only present when the optional profile.emails
        scope was granted; the app never asks for it (see ADR-0017), so it is
        normally absent and the UI hides it.

        Returns ``None`` on a permission/HTTP error (see
        :meth:`list_coursework`).
        """
        items: list[dict] = []
        page_token: str | None = None
        while True:
            try:
                request = (
                    self._service.courses()
                    .students()
                    .list(courseId=course_id, pageSize=100, pageToken=page_token)
                )
                response = self._execute(request)
            except HttpError:
                return None
            for student in response.get("students", []):
                profile = student.get("profile", {}) or {}
                name = profile.get("name") or {}
                items.append(
                    {
                        "userId": student.get("userId") or profile.get("id"),
                        "fullName": name.get("fullName") or "",
                        "emailAddress": profile.get("emailAddress"),
                        "photoUrl": profile.get("photoUrl"),
                    }
                )
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    def list_all_submissions(self, course_id: str) -> list[dict] | None:
        """List every student's submissions for all coursework of a course.

        Teacher-only view; ``courseWorkId="-"`` fetches submissions for all
        coursework in one paginated sweep instead of one request per item.

        Returns ``None`` on a permission/HTTP error (see
        :meth:`list_coursework`).
        """
        items: list[dict] = []
        page_token: str | None = None
        while True:
            try:
                request = (
                    self._service.courses()
                    .courseWork()
                    .studentSubmissions()
                    .list(
                        courseId=course_id,
                        courseWorkId="-",
                        pageSize=100,
                        pageToken=page_token,
                    )
                )
                response = self._execute(request)
            except HttpError:
                return None
            items.extend(response.get("studentSubmissions", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    def list_submissions_for_course(self, course_id: str) -> list[dict]:
        """List the user's own submissions for every assignment in a course.

        courses.courseWork.list is teacher-only, so students must discover
        coursework through their submissions: courseWorkId="-" returns
        submissions for ALL course work in the course, and each item carries
        the courseWorkId needed for the point courseWork.get lookup.
        """
        items: list[dict] = []
        page_token: str | None = None
        while True:
            try:
                request = (
                    self._service.courses()
                    .courseWork()
                    .studentSubmissions()
                    .list(
                        courseId=course_id,
                        courseWorkId="-",
                        userId="me",
                        pageSize=100,
                        pageToken=page_token,
                    )
                )
                response = self._execute(request)
            except HttpError:
                return items
            items.extend(response.get("studentSubmissions", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    def get_coursework(self, course_id: str, course_work_id: str) -> dict:
        """Point lookup of one assignment (allowed for students)."""
        try:
            request = (
                self._service.courses()
                .courseWork()
                .get(courseId=course_id, id=course_work_id)
            )
            return self._execute(request)
        except HttpError:
            return {}

    def get_user_profile(self) -> dict:
        try:
            request = self._service.userProfiles().get(userId="me")
            return self._execute(request)
        except HttpError:
            return {}
