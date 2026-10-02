# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Teacher-mode sync volume (migration stage 6, В§65).

Teacher mode fans out to more Google requests than the student view, so the
service must bound that volume and make it observable:

- an interactive (user-triggered) sync is capped by a process-global ceiling
  and fails fast with 503 instead of stacking worker pools;
- scheduled/background syncs are already bounded by the scheduler's pool and
  are not affected by the interactive ceiling;
- every Classroom call is counted, and pagination keeps following
  ``nextPageToken`` until the last page.
"""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from db.models.accounts import User
from gapi.classroom import ClassroomClient, RequestStats
from sync.service import _fetch as service


class _FakeExecutable:
    """A prepared request that yields canned pages, one per ``execute``.

    Deliberately holds the caller's list by reference (no copy): an
    ``execute`` must consume the page so the NEXT ``list()`` call sees the
    rest, otherwise the pagination loop never terminates.
    """

    def __init__(self, pages, calls):
        self._pages = pages
        self._calls = calls

    def execute(self, num_retries=0):
        self._calls.append(num_retries)
        return self._pages.pop(0)


class _FakeListResource:
    """Stands in for a paginated ``...list()`` resource."""

    def __init__(self, pages, calls):
        self._pages = pages
        self._calls = calls
        self.kwargs: list[dict] = []

    def list(self, **kwargs):
        self.kwargs.append(kwargs)
        return _FakeExecutable(self._pages, self._calls)


# --------------------------------- В§65 removed ceiling / queued contract

# Stage 10 (queued manual sync): the hosted POST /api/sync no longer runs
# the Classroom fan-out inside the HTTP request, so there is no global
# interactive slot to exhaust and no 503 path. sync_now keeps its
# ``interactive`` kwarg for the DESKTOP inline path; these tests pin that
# the plumbing still accepts it and that scheduled runs are unaffected.


def test_interactive_sync_returns_503_when_the_global_limit_is_reached(
    client, monkeypatch
):
    """Desktop inline path: when the interactive pool is saturated, POST /api/sync
    fails fast with 503 SERVER_BUSY.
    """
    monkeypatch.setattr(service, "SYNC_MAX_CONCURRENT_USERS", 1)
    assert service._acquire_interactive_slot() is True
    try:
        response = client.post("/api/sync")
        assert response.status_code == 503
        assert response.json()["detail"] == service.SERVER_BUSY
    finally:
        service._release_interactive_slot()


def test_sync_now_is_busy_when_no_interactive_slot_exists(db, owner_id, monkeypatch):
    monkeypatch.setattr(service, "SYNC_MAX_CONCURRENT_USERS", 0)
    user = db.get(User, owner_id)
    result = service.sync_now(user=user, interactive=True)
    assert result == {"ok": False, "error": service.SERVER_BUSY}


def test_scheduled_sync_is_not_limited_by_the_interactive_ceiling(
    db, owner_id, monkeypatch
):
    """The scheduler bounds its own pool; the interactive gate must not
    turn a scheduled run into a fake failure."""
    monkeypatch.setattr(service, "SYNC_MAX_CONCURRENT_USERS", 1)
    assert service._acquire_interactive_slot() is True
    try:
        user = db.get(User, owner_id)
        result = service.sync_now(user=user, interactive=False)
        # No Google grant is configured in the test environment; the point
        # is that the call reached the sync body instead of the busy gate.
        assert result["ok"] is False
        assert result["error"] != service.SERVER_BUSY
    finally:
        service._release_interactive_slot()


# ------------------------------------------------- В§65 observability + paging


def test_teacher_roster_is_never_requested_for_a_student_course():
    """``courses.list`` is shared, but the teacher roster is not (В§65).

    A STUDENT course answers HTTP 500 on ``courses.teachers.list`` (not 403),
    and googleapiclient retries every 5xx three times with a backoff before
    degrading to an empty list. Asking anyway cost one doomed request plus its
    retries per student course — on a 23-course account that was the largest
    avoidable share of a sync's runtime, and the result was discarded anyway.
    """
    asked: list[str] = []

    class _Client(ClassroomClient):
        """A stand-in for the real client: the fan-out only calls these five
        methods, and none of them touches ``self._service``, so a dummy
        discovery resource is enough to keep the real ``__init__`` contract."""

        def __init__(self) -> None:
            super().__init__(service=None)

        def list_teachers(self, course_id: str) -> list[dict]:
            asked.append(course_id)
            return [{"fullName": "Teacher"}]

        def list_submissions_for_course(self, course_id: str) -> list[dict]:
            return []

        def list_coursework(
            self, course_id: str, course_work_states: list[str] | None = None
        ) -> list[dict] | None:
            return []

        def list_students(self, course_id: str) -> list[dict] | None:
            return []

        def list_all_submissions(self, course_id: str) -> list[dict] | None:
            return []

    courses = [
        ({"id": "t-course"}, "TEACHER"),
        ({"id": "s-one"}, "STUDENT"),
        ({"id": "s-two"}, "STUDENT"),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        teacher_names, payloads = service._fetch_course_payloads(
            lambda: _Client(), courses, pool
        )

    assert asked == ["t-course"], (
        "the teacher roster must only be fetched for TEACHER courses; "
        f"asked for {asked}"
    )
    # The student courses still get their own payload, just no roster.
    assert teacher_names == {"t-course": ["Teacher"], "s-one": [], "s-two": []}
    assert set(payloads) == {"t-course", "s-one", "s-two"}


def test_course_list_follows_pagination_and_counts_requests():
    calls: list[int] = []
    resource = _FakeListResource(
        [
            {"courses": [{"id": "c1"}], "nextPageToken": "p2"},
            {"courses": [{"id": "c2"}]},
        ],
        calls,
    )
    # Named `discovery`, not `service`: the module `service` is imported in this
    # file (sync.service) and a local of the same name would shadow it.
    discovery = SimpleNamespace(courses=lambda: resource)
    stats = RequestStats()
    client = ClassroomClient(discovery, stats=stats)

    courses = client.list_courses() or []
    assert [course["id"] for course in courses] == ["c1", "c2"]
    assert [kwargs.get("pageToken") for kwargs in resource.kwargs] == [None, "p2"]
    assert stats.requests == 2
    assert calls == [3, 3]  # both calls used the shared retry policy


def test_teacher_submission_sweep_paginates_and_is_counted():
    calls: list[int] = []
    submissions = _FakeListResource(
        [
            {
                "studentSubmissions": [{"courseWorkId": "w1", "userId": "s1"}],
                "nextPageToken": "page-2",
            },
            {"studentSubmissions": [{"courseWorkId": "w1", "userId": "s2"}]},
        ],
        calls,
    )
    # Named `discovery`, not `service`: the module `service` is imported in this
    # file (sync.service) and a local of the same name would shadow it.
    discovery = SimpleNamespace(
        courses=lambda: SimpleNamespace(
            courseWork=lambda: SimpleNamespace(studentSubmissions=lambda: submissions)
        )
    )
    stats = RequestStats()
    client = ClassroomClient(discovery, stats=stats)

    rows = client.list_all_submissions("c1") or []
    assert [row["userId"] for row in rows] == ["s1", "s2"]
    assert [kwargs.get("pageToken") for kwargs in submissions.kwargs] == [
        None,
        "page-2",
    ]
    # The whole sweep is one coursework="-" request per page, and every page
    # is counted — that is the number the sync log reports.
    assert all(kwargs["courseWorkId"] == "-" for kwargs in submissions.kwargs)
    assert stats.requests == 2


def test_request_stats_are_shared_across_threads():
    from concurrent.futures import ThreadPoolExecutor

    stats = RequestStats()

    def record_many(_):
        for _ in range(100):
            stats.record()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(record_many, range(8)))
    assert stats.requests == 800
