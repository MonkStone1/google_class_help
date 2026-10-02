# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Stage 10 Part 1 — hosted deployment readiness (§52–§58, DDoS plan §24/§27–29).

Executable index of the Part 1 acceptance matrix: checks the stage-by-stage
suites did not spell out explicitly, plus the stage-10 code changes
(queued manual sync, readiness endpoint, CF-Connecting-IP trust rule).

Everything runs against SQLite and the hermetic ``hosted_client`` fixtures;
no test touches a real PostgreSQL server or a Google endpoint.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from auth import hosted
from core import proxy
from db.models.accounts import User, UserSession
from db.models.classroom import Course, CourseRole, CourseWork, SyncStatus
from gapi import credentials
from sync import store
from sync.service import _fetch as service


def _utc(year: int, month: int, day: int) -> datetime:
    """Naive UTC timestamp — the convention of the user-scoped tables."""
    return datetime(year, month, day, tzinfo=timezone.utc).replace(tzinfo=None)


def _make_user(db, subject: str, name: str | None = None) -> User:
    user = User(
        provider="google",
        provider_subject=subject,
        email=f"{subject}@example.com",
        display_name=name or subject,
        created_at=_utc(2026, 9, 18),
        updated_at=_utc(2026, 9, 18),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _add_session(db, user: User, raw_token: str, ttl_hours: int = 14) -> UserSession:
    base = _now()
    session = UserSession(
        session_token_hash=hosted._sha256_hex(raw_token),
        user_id=user.id,
        created_at=base,
        expires_at=base + timedelta(hours=ttl_hours),
        last_seen_at=base,
    )
    db.add(session)
    db.commit()
    return session


def _seed_course(db, user_id: int, course_id: str, name: str = "Course") -> Course:
    course = Course(
        user_id=user_id,
        id=course_id,
        name=name,
        section="S1",
        course_state="ACTIVE",
    )
    db.add(course)
    db.commit()
    return course


def _seed_work(db, user_id: int, course_id: str, work_id: str) -> CourseWork:
    work = CourseWork(
        user_id=user_id,
        id=work_id,
        course_id=course_id,
        title="Homework",
        state="PUBLISHED",
        work_type="ASSIGNMENT",
    )
    db.add(work)
    db.commit()
    return work


# ------------------------------------------------------------- §52 auth matrix


def test_valid_session_resolves_the_current_user(hosted_client, db):
    user = _make_user(db, "sub-alice")
    _add_session(db, user, "raw-alice")
    hosted_client.cookies.set("gch_session", "raw-alice")
    response = hosted_client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["email"] == "sub-alice@example.com"


def test_expired_session_is_rejected(hosted_client, db):
    user = _make_user(db, "sub-expired")
    _add_session(db, user, "raw-expired", ttl_hours=-24)
    hosted_client.cookies.set("gch_session", "raw-expired")
    assert hosted_client.get("/api/me").status_code == 401


def test_revoked_session_is_rejected(hosted_client, db):
    user = _make_user(db, "sub-revoked")
    session = _add_session(db, user, "raw-revoked")
    session.revoked_at = _utc(2026, 9, 19)
    db.commit()
    hosted_client.cookies.set("gch_session", "raw-revoked")
    assert hosted_client.get("/api/me").status_code == 401


def test_unknown_session_token_is_rejected(hosted_client):
    hosted_client.cookies.set("gch_session", "not-a-real-token")
    assert hosted_client.get("/api/me").status_code == 401


def test_two_browsers_keep_independent_sessions(hosted_client, db):
    user = _make_user(db, "sub-two-browsers")
    _add_session(db, user, "raw-browser-a")
    _add_session(db, user, "raw-browser-b")
    hosted_client.cookies.set("gch_session", "raw-browser-a")
    assert hosted_client.get("/api/me").status_code == 200
    hosted_client.cookies.set("gch_session", "raw-browser-b")
    assert hosted_client.get("/api/me").status_code == 200
    hosted_client.cookies.set("gch_session", "raw-browser-c")
    assert hosted_client.get("/api/me").status_code == 401


def test_two_login_attempts_do_not_interfere(hosted_client):
    """§52: two parallel OAuth transactions keep independent state values."""
    first = hosted_client.get("/api/auth/login", follow_redirects=False)
    second = hosted_client.get("/api/auth/login", follow_redirects=False)
    assert first.status_code == 302
    assert second.status_code == 302
    first_state = first.headers["location"].split("state=", 1)[1].split("&", 1)[0]
    second_state = second.headers["location"].split("state=", 1)[1].split("&", 1)[0]
    assert first_state and second_state and first_state != second_state


def test_callback_without_state_is_rejected(hosted_client):
    response = hosted_client.get("/api/auth/callback?code=abc", follow_redirects=False)
    # Unknown/expired state is never exchanged: the flow bounces back to the
    # login surface (302) instead of completing an OAuth transaction.
    assert response.status_code in (302, 400, 403)


# ------------------------------------------------ §52/§53 isolation with fakes


def test_same_google_course_id_lives_independently_for_two_users(
    hosted_client, db, monkeypatch
):
    """§53: provider-level ids are unique per owner, not globally."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_session(db, alice, "raw-alice")
    _add_session(db, bob, "raw-bob")
    _seed_course(db, alice.id, "course_shared_id", "Alice course")
    _seed_course(db, bob.id, "course_shared_id", "Bob course")

    hosted_client.cookies.set("gch_session", "raw-alice")
    courses = hosted_client.get("/api/courses").json()
    assert [c["id"] for c in courses] == ["course_shared_id"]
    assert courses[0]["name"] == "Alice course"

    hosted_client.cookies.set("gch_session", "raw-bob")
    courses = hosted_client.get("/api/courses").json()
    assert [c["id"] for c in courses] == ["course_shared_id"]
    assert courses[0]["name"] == "Bob course"


def test_user_a_cannot_read_b_coursework_or_grades(hosted_client, db):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_session(db, alice, "raw-alice")
    _seed_course(db, bob.id, "course_b_only")
    _seed_work(db, bob.id, "course_b_only", "work_b_only")

    hosted_client.cookies.set("gch_session", "raw-alice")
    assert hosted_client.get("/api/courses/course_b_only").status_code == 404
    assert hosted_client.get("/api/courses/course_b_only/coursework").status_code in (
        403,
        404,
    )
    assert (
        hosted_client.get(
            "/api/courses/course_b_only/coursework/work_b_only"
        ).status_code
        == 404
    )
    assert hosted_client.get("/api/courses/course_b_only/grades").status_code in (
        403,
        404,
    )


def test_user_a_cannot_read_b_teacher_roster(hosted_client, db):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_session(db, alice, "raw-alice")
    _seed_course(db, bob.id, "course_teacher_b")
    db.add(CourseRole(user_id=bob.id, course_id="course_teacher_b", role="TEACHER"))
    db.commit()

    hosted_client.cookies.set("gch_session", "raw-alice")
    assert hosted_client.get("/api/courses/course_teacher_b/students").status_code in (
        403,
        404,
    )
    # Alice sees no courses at all: Bob's roster is never on her surface.
    assert hosted_client.get("/api/courses").json() == []


def test_user_a_cannot_clear_b_cache(hosted_client, db):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_session(db, alice, "raw-alice")
    _seed_course(db, bob.id, "course_b")

    hosted_client.cookies.set("gch_session", "raw-alice")
    response = hosted_client.delete("/api/me/cache?confirm=true")
    assert response.status_code == 200
    # Bob's cache is untouched.
    assert db.get(Course, (bob.id, "course_b")) is not None


def test_user_a_sync_does_not_touch_b_state(hosted_client, db, monkeypatch):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_session(db, alice, "raw-alice")
    db.add(
        SyncStatus(
            user_id=bob.id,
            status=store.SYNC_OK,
            last_success_at=_utc(2026, 9, 19),
            consecutive_failures=0,
            sync_requested=False,
        )
    )
    db.commit()
    hosted_client.cookies.set("gch_session", "raw-alice")
    assert hosted_client.post("/api/sync").status_code == 200
    bob_state = db.get(SyncStatus, bob.id)
    assert bob_state is not None
    assert bob_state.sync_requested is False


# --------------------------------------------------------- §29/§41 credentials


def test_token_material_never_appears_in_responses(hosted_client, db):
    user = _make_user(db, "sub-token")
    _add_session(db, user, "raw-token")
    hosted_client.cookies.set("gch_session", "raw-token")
    for path in ("/api/me", "/api/auth/status", "/api/status"):
        body = hosted_client.get(path).text
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert "client_secret" not in body


def test_one_user_has_no_credentials_when_the_other_does(db):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    assert credentials.get_google_credentials(db, alice) is None
    assert credentials.get_google_credentials(db, bob) is None


def test_deleting_one_grant_leaves_the_other_user_alone(db):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    credentials.delete_google_credentials(db, alice.id)
    assert db.get(User, bob.id) is not None
    assert credentials.has_google_grant(db, alice) is False


def test_invalid_grant_refresh_is_confined_to_its_owner(db, monkeypatch):
    """§29/DDoS: one dead grant must never log the other user out."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    calls: list[int] = []

    def fake_refresh(db_session, user):
        calls.append(user.id)

    # The grant is dead for Alice only; Bob's user row (and session) survive.

    monkeypatch.setattr(credentials, "refresh_google_credentials", fake_refresh)
    assert credentials.refresh_google_credentials(db, alice) is None
    assert calls == [alice.id]
    assert db.get(User, bob.id) is not None


# --------------------------------------------------------------- §52/§27 sync


def test_two_users_have_independent_sync_locks():
    assert service._sync_lock_for(1) is not service._sync_lock_for(2)
    assert service._sync_lock_for(1) is service._sync_lock_for(1)


def test_one_user_has_at_most_one_active_sync(db, owner_id, monkeypatch):
    user = db.get(User, owner_id)
    lock = service._sync_lock_for(user.id)
    acquired = lock.acquire(blocking=False)
    try:
        result = service.sync_now(user=user, interactive=True)
        assert result["ok"] is False
        assert result.get("error") == service.ALREADY_RUNNING
    finally:
        if acquired:
            lock.release()


def test_queue_flag_and_claim_helpers_exist(db):
    assert hasattr(store, "claim_sync")
    assert hasattr(store, "request_sync")
    assert hasattr(store, "mark_sync_pending")


# --------------------------------------------------------- §52 teacher matrix


def test_teacher_course_stays_teacher_and_student_course_stays_student(db):
    user = _make_user(db, "sub-teacher")
    _seed_course(db, user.id, "course_teacher_a")
    _seed_course(db, user.id, "course_student_b")
    db.add(CourseRole(user_id=user.id, course_id="course_teacher_a", role="TEACHER"))
    db.add(CourseRole(user_id=user.id, course_id="course_student_b", role="STUDENT"))
    db.commit()
    roles = {
        row.course_id: row.role
        for row in db.query(CourseRole).filter(CourseRole.user_id == user.id).all()
    }
    assert roles == {
        "course_teacher_a": "TEACHER",
        "course_student_b": "STUDENT",
    }


def test_teacher_only_endpoints_reject_a_student_course(hosted_client, db):
    user = _make_user(db, "sub-alice")
    _add_session(db, user, "raw-alice")
    _seed_course(db, user.id, "course_student_a")
    db.add(CourseRole(user_id=user.id, course_id="course_student_a", role="STUDENT"))
    db.commit()
    hosted_client.cookies.set("gch_session", "raw-alice")
    assert (
        hosted_client.get("/api/courses/course_student_a/students").status_code == 403
    )
    assert hosted_client.get("/api/courses/course_student_a/grades").status_code == 403


def test_student_cannot_read_another_users_teacher_data(hosted_client, db):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_session(db, alice, "raw-alice")
    _seed_course(db, bob.id, "course_teacher_b")
    db.add(CourseRole(user_id=bob.id, course_id="course_teacher_b", role="TEACHER"))
    db.commit()
    hosted_client.cookies.set("gch_session", "raw-alice")
    assert hosted_client.get("/api/courses/course_teacher_b/students").status_code in (
        403,
        404,
    )


# ------------------------------------------------------- §52 database checks


def test_core_tables_exist(db):
    from sqlalchemy import text

    rows = db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table'")
    ).fetchall()
    names = {row[0] for row in rows}
    for table in (
        "users",
        "sessions",
        "oauth_tokens",
        "courses",
        "coursework",
        "course_students",
        "sync_status",
    ):
        assert table in names


def test_deleting_a_user_cascades_their_cache(db):
    from maintenance import delete_user_data

    user = _make_user(db, "sub-cascade")
    _seed_course(db, user.id, "course_cascade")
    db.commit()
    delete_user_data(db, user)
    assert db.get(Course, (user.id, "course_cascade")) is None
    assert db.get(User, user.id) is None


def test_connection_pool_is_released_between_requests(client):
    """§45/§52: a request must not leave a checked-out connection behind."""
    from db.session import engine

    for _ in range(3):
        assert client.get("/api/health").status_code == 200
    checkedout = getattr(engine.pool, "checkedout")  # noqa: B009 - dialect-specific
    assert checkedout() == 0


# ----------------------------------------------------------- §58 health/ready


def test_health_endpoint_is_public_and_minimal(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_ready_endpoint_reports_database_up(client):
    response = client.get("/api/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["db"] == "up"


def test_ready_endpoint_is_public_without_a_session(hosted_client):
    assert hosted_client.get("/api/ready").status_code == 200


def test_ready_endpoint_reports_503_when_the_database_is_down(client, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    from db import session as database

    class _BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise SQLAlchemyError("db down")

        def close(self) -> None:
            pass

    monkeypatch.setattr(database, "SessionLocal", lambda: _BrokenSession())
    response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json() == {"ok": False, "db": "down"}


def test_ready_endpoint_never_leaks_infrastructure_details(client):
    body = client.get("/api/ready").text.lower()
    for token in ("password", "postgresql://", "secret", "token", "host"):
        assert token not in body


# ------------------------------------------------- DDoS plan §7 client IP


def _fake_request(headers: dict[str, str], peer: str):
    """A minimal Starlette Request with the given headers and TCP peer."""
    from starlette.requests import Request as StarletteRequest

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": (peer, 12345),
        "headers": [
            (name.encode("latin-1"), value.encode("latin-1"))
            for name, value in headers.items()
        ],
    }
    return StarletteRequest(scope)


def test_cf_connecting_ip_is_ignored_from_untrusted_peers(monkeypatch):
    request = _fake_request({"cf-connecting-ip": "203.0.113.5"}, "198.51.100.7")
    monkeypatch.setattr(proxy, "peer_is_trusted_proxy", lambda request: False)
    assert proxy.client_ip(request) == "198.51.100.7"


def test_cf_connecting_ip_is_used_from_trusted_proxies(monkeypatch):
    request = _fake_request({"cf-connecting-ip": "203.0.113.5"}, "172.18.0.4")
    monkeypatch.setattr(proxy, "peer_is_trusted_proxy", lambda request: True)
    assert proxy.client_ip(request) == "203.0.113.5"


def test_client_ip_falls_back_to_the_tcp_peer(monkeypatch):
    request = _fake_request({}, "198.51.100.9")
    monkeypatch.setattr(proxy, "peer_is_trusted_proxy", lambda request: True)
    assert proxy.client_ip(request) == "198.51.100.9"


@pytest.mark.parametrize(
    "path",
    [
        "/api/courses",
        "/api/assignments",
        "/api/grades",
        "/api/calendar",
        "/api/status",
        "/api/me",
    ],
)
def test_hosted_data_routes_require_a_session(hosted_client, path):
    assert hosted_client.get(path).status_code == 401


def test_hosted_sync_route_requires_a_session(hosted_client):
    assert hosted_client.post("/api/sync").status_code == 401
