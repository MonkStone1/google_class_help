"""Thin wrapper around the official Google Classroom API client.

Everything specific to talking to Google lives here: pagination, response
shapes, and date parsing. The rest of the application never imports the
googleapiclient package directly.
"""

from datetime import datetime
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

    def __init__(self, service: Any) -> None:
        self._service = service

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
                response = (
                    self._service.courses()
                    .list(**kwargs)
                    .execute(num_retries=NUM_RETRIES)
                )
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
                response = (
                    self._service.courses()
                    .courseWork()
                    .list(**kwargs)
                    .execute(num_retries=NUM_RETRIES)
                )
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
                response = (
                    self._service.courses()
                    .teachers()
                    .list(courseId=course_id, pageSize=100, pageToken=page_token)
                    .execute(num_retries=NUM_RETRIES)
                )
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
                response = (
                    self._service.courses()
                    .students()
                    .list(courseId=course_id, pageSize=100, pageToken=page_token)
                    .execute(num_retries=NUM_RETRIES)
                )
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
                response = (
                    self._service.courses()
                    .courseWork()
                    .studentSubmissions()
                    .list(
                        courseId=course_id,
                        courseWorkId="-",
                        pageSize=100,
                        pageToken=page_token,
                    )
                    .execute(num_retries=NUM_RETRIES)
                )
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
                response = (
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
                    .execute(num_retries=NUM_RETRIES)
                )
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
            return (
                self._service.courses()
                .courseWork()
                .get(courseId=course_id, id=course_work_id)
                .execute(num_retries=NUM_RETRIES)
            )
        except HttpError:
            return {}

    def get_user_profile(self) -> dict:
        try:
            return (
                self._service.userProfiles()
                .get(userId="me")
                .execute(num_retries=NUM_RETRIES)
            )
        except HttpError:
            return {}
