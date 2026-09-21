# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Teacher-mode sync volume (migration stage 6, §65).

Teacher mode fans out to more Google requests than the student view, so the
service must bound that volume and make it observable:

- an interactive (user-triggered) sync is capped by a process-global ceiling
  and fails fast with 503 instead of stacking worker pools;
- scheduled/background syncs are already bounded by the scheduler's pool and
  are not affected by the interactive ceiling;
- every Classroom call is counted, and pagination keeps following
  ``nextPageToken`` until the last page.
"""

from types import SimpleNamespace

import sync_service
from classroom_api import ClassroomClient, RequestStats
from models_auth import User


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


# ------------------------------------------------------- §65 global ceiling


def test_interactive_sync_returns_503_when_the_global_limit_is_reached(
    client, monkeypatch
):
    monkeypatch.setattr(sync_service, "SYNC_MAX_CONCURRENT_USERS", 1)
    assert sync_service._acquire_interactive_slot() is True
    try:
        response = client.post("/api/sync")
        assert response.status_code == 503
        assert "busy" in response.json()["detail"].lower()
    finally:
        sync_service._release_interactive_slot()


def test_sync_now_is_busy_when_no_interactive_slot_exists(db, owner_id, monkeypatch):
    monkeypatch.setattr(sync_service, "SYNC_MAX_CONCURRENT_USERS", 0)
    user = db.get(User, owner_id)
    result = sync_service.sync_now(user=user, interactive=True)
    assert result == {"ok": False, "error": sync_service.SERVER_BUSY}


def test_scheduled_sync_is_not_limited_by_the_interactive_ceiling(
    db, owner_id, monkeypatch
):
    """The scheduler bounds its own pool; the interactive gate must not
    turn a scheduled run into a fake failure."""
    monkeypatch.setattr(sync_service, "SYNC_MAX_CONCURRENT_USERS", 1)
    assert sync_service._acquire_interactive_slot() is True
    try:
        user = db.get(User, owner_id)
        result = sync_service.sync_now(user=user, interactive=False)
        # No Google grant is configured in the test environment; the point
        # is that the call reached the sync body instead of the busy gate.
        assert result["ok"] is False
        assert result["error"] != sync_service.SERVER_BUSY
    finally:
        sync_service._release_interactive_slot()


# ------------------------------------------------- §65 observability + paging


def test_course_list_follows_pagination_and_counts_requests():
    calls: list[int] = []
    resource = _FakeListResource(
        [
            {"courses": [{"id": "c1"}], "nextPageToken": "p2"},
            {"courses": [{"id": "c2"}]},
        ],
        calls,
    )
    service = SimpleNamespace(courses=lambda: resource)
    stats = RequestStats()
    client = ClassroomClient(service, stats=stats)

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
    service = SimpleNamespace(
        courses=lambda: SimpleNamespace(
            courseWork=lambda: SimpleNamespace(studentSubmissions=lambda: submissions)
        )
    )
    stats = RequestStats()
    client = ClassroomClient(service, stats=stats)

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
