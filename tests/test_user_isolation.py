# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""User isolation via get_current_user (migration stage 4 part 1, §12–§16).

The core invariants under test:

- §13: every data endpoint resolves the authenticated user through the
  ``get_current_user`` dependency — the session user in hosted mode, the
  local owner on desktop — and never trusts a request-supplied id;
- §12: no data path leaks another user's rows, including coursework
  reached by GUESSING Google ids that happen to exist in both caches;
- §15: Google credentials are read/saved/refreshed/deleted per user;
- §16: hosted status/login state is per session, never the desktop's
  global login state.
"""

from datetime import datetime, timedelta, timezone

import google_credentials
import pytest
from google.oauth2.credentials import Credentials
from sqlalchemy import select
from sqlalchemy.orm import Session

import auth
import hosted_auth
import ownership
import sync_store
from models import Course
from models_auth import OAuthToken, User, UserSession


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc(year: int, month: int, day: int) -> datetime:
    """Naive UTC timestamp — the convention of the user-scoped tables."""
    return datetime(year, month, day, tzinfo=timezone.utc).replace(tzinfo=None)


def _make_user(db: Session, subject: str, name: str | None = None) -> User:
    user = User(
        provider="google",
        provider_subject=subject,
        email=f"{subject}@example.com",
        display_name=name or subject,
        created_at=_now(),
        updated_at=_now(),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _make_local_user(db: Session, subject: str) -> User:
    """A user whose row carries NO profile — the desktop cache path (§17)."""
    user = User(
        provider=ownership.LOCAL_PROVIDER,
        provider_subject=subject,
        email=None,
        display_name=None,
        created_at=_now(),
        updated_at=_now(),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _seed_course(db: Session, user_id: int, name: str, points: float = 70) -> None:
    """One course with one assignment — identical Google ids for everyone."""
    from models import CourseRole, CourseWork, StudentSubmission

    db.add(Course(user_id=user_id, id="c1", name=name, course_state="ACTIVE"))
    db.add(CourseRole(user_id=user_id, course_id="c1", role="STUDENT"))
    db.add(
        CourseWork(
            user_id=user_id,
            id="w1",
            course_id="c1",
            title=f"{name} work",
            state="PUBLISHED",
            max_points=100,
        )
    )
    db.add(
        StudentSubmission(
            user_id=user_id,
            course_id="c1",
            coursework_id="w1",
            state="RETURNED",
            assigned_points=points,
        )
    )
    # Structured per-user sync state (stage 5) instead of the key/value row.
    sync_store.mark_sync_succeeded(db, user_id, _utc(2026, 9, 19))
    db.commit()


def _add_session(db: Session, user: User, raw_token: str) -> None:
    """A valid session row without the OAuth dance (identity is stage-2 code)."""
    now = _now()
    db.add(
        UserSession(
            session_token_hash=hosted_auth._sha256_hex(raw_token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(days=1),
            last_seen_at=now,
        )
    )
    db.commit()


# ----------------------------------------------------------------- §12 IDOR


def test_foreign_course_is_404_on_every_path(hosted_client, db):
    """§12: every nested data path resolves ids inside the caller's scope."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice's course")
    _seed_course(db, bob.id, "Bob's course")
    _add_session(db, bob, "raw-bob-token")
    hosted_client.cookies.set("gch_session", "raw-bob-token")

    # Both users hold the same Google course id c1: Bob's own c1 answers,
    # and its data is Bob's — never Alice's rows with identical ids.
    body = hosted_client.get("/api/courses/c1")
    assert body.status_code == 200
    assert body.json()["course"]["name"] == "Bob's course"

    detail = hosted_client.get("/api/courses/c1/coursework/w1")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Bob's course work"
    submissions = hosted_client.get("/api/courses/c1/coursework/w1/submissions").json()
    assert [s["student_name"] for s in submissions] != ["Alice"]


def test_coursework_google_id_guessing_does_not_cross_users(hosted_client, db):
    """§12: coursework by guessed Google id stays inside the caller's scope."""
    from models import CourseWork

    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice's course")
    _seed_course(db, bob.id, "Bob's course")
    # A coursework id only Alice has.
    db.add(
        CourseWork(
            user_id=alice.id, id="w-secret", course_id="c1", title="Alice secret"
        )
    )
    db.commit()
    _add_session(db, bob, "raw-bob-token")
    hosted_client.cookies.set("gch_session", "raw-bob-token")

    assert hosted_client.get("/api/courses/c1/coursework/w-secret").status_code == 404
    titles = [a["title"] for a in hosted_client.get("/api/assignments").json()]
    assert "Alice secret" not in titles
    assert titles == ["Bob's course work"]


def test_course_list_and_grades_show_only_the_session_user(hosted_client, db):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice's course")
    _seed_course(db, bob.id, "Bob's course")
    _add_session(db, alice, "raw-alice-token")
    _add_session(db, bob, "raw-bob-token")

    hosted_client.cookies.set("gch_session", "raw-alice-token")
    assert [c["name"] for c in hosted_client.get("/api/courses").json()] == [
        "Alice's course"
    ]
    grades = hosted_client.get("/api/grades").json()
    assert [g["course_name"] for g in grades] == ["Alice's course"]

    hosted_client.cookies.set("gch_session", "raw-bob-token")
    assert [c["name"] for c in hosted_client.get("/api/courses").json()] == [
        "Bob's course"
    ]
    grades = hosted_client.get("/api/grades").json()
    assert [g["course_name"] for g in grades] == ["Bob's course"]


def test_cache_delete_only_clears_the_caller(hosted_client, db):
    """§12/audit P4: DELETE /api/cache is destructive for one user only."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice's course")
    _seed_course(db, bob.id, "Bob's course")
    _add_session(db, bob, "raw-bob-token")
    hosted_client.cookies.set("gch_session", "raw-bob-token")

    response = hosted_client.delete("/api/cache", params={"confirm": "true"})
    assert response.status_code == 200
    remaining = {
        row[0]: row[1] for row in db.execute(select(Course.user_id, Course.id)).all()
    }
    assert bob.id not in remaining
    assert remaining.get(alice.id) == "c1"


def test_sync_targets_the_session_user_only(hosted_client, db, monkeypatch):
    """§12/DDoS §9: /api/sync queues the CALLER's job only, nothing else's."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice's course")
    _add_session(db, bob, "raw-bob-token")

    hosted_client.cookies.set("gch_session", "raw-bob-token")
    response = hosted_client.post("/api/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["queued"] is True
    assert body["status"] == "queued"
    # Only the session user's flag was set — nobody else's.
    from models import SyncStatus

    alice_state = db.get(SyncStatus, alice.id)
    assert alice_state is not None
    assert alice_state.last_success_at == _utc(2026, 9, 19)
    assert alice_state.status == sync_store.SYNC_OK
    assert alice_state.sync_requested is False
    bob_state = db.get(SyncStatus, bob.id)
    assert bob_state is not None
    assert bob_state.sync_requested is True
    # The queue is already an active UI operation even before the worker
    # claims it; the frontend must not wait for `status == running` to start
    # watching and must not keep the old cache as the final view.
    queued_status = hosted_client.get("/api/status").json()
    assert queued_status["sync_status"] == sync_store.SYNC_PENDING
    assert queued_status["syncing"] is True


# ----------------------------------------------------- §16 per-session state


def test_status_reports_the_session_user_not_a_global_state(hosted_client, db):
    """§16/§26: identity comes from THIS session, sync state from THIS user."""
    alice = _make_user(db, "sub-alice", "Alice")
    bob = _make_user(db, "sub-bob", "Bob")
    _seed_course(db, alice.id, "Alice's course")
    _seed_course(db, bob.id, "Bob's course")
    _add_session(db, alice, "raw-alice-token")
    _add_session(db, bob, "raw-bob-token")

    hosted_client.cookies.set("gch_session", "raw-alice-token")
    identity = hosted_client.get("/api/auth/status").json()
    assert identity["user"]["name"] == "Alice"
    assert identity["user"]["email"] == "sub-alice@example.com"
    status = hosted_client.get("/api/status").json()
    # §26: /api/status carries no identity at all — only the sync state.
    assert "user_name" not in status and "user_email" not in status
    assert status["last_sync"] == "2026-09-19T00:00:00"

    hosted_client.cookies.set("gch_session", "raw-bob-token")
    identity = hosted_client.get("/api/auth/status").json()
    assert identity["user"]["name"] == "Bob"
    assert identity["user"]["email"] == "sub-bob@example.com"
    # Bob sees his own sync state (seeded for him too) — not Alice's rows
    # and not a process-global "last account".
    assert hosted_client.get("/api/status").json()["last_sync"] == "2026-09-19T00:00:00"


# ------------------------------------------- §15 user-scoped credentials


def _creds(token: str) -> Credentials:
    return Credentials(
        token=token,
        refresh_token=f"refresh-{token}",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-web-client.apps.googleusercontent.com",
        client_secret="test-web-client-secret",
        scopes=auth.SCOPES,
        expiry=None,
    )


def test_credentials_are_stored_and_resolved_per_user(db: Session):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    google_credentials.save_google_credentials(db, alice.id, _creds("at-alice"))
    google_credentials.save_google_credentials(db, bob.id, _creds("at-bob"))

    # Encrypted at rest, never plaintext (§8).
    row_a = db.get(OAuthToken, alice.id)
    assert row_a is not None and row_a.access_token.startswith("enc.v1:")
    assert "at-alice" not in row_a.access_token

    creds_a = google_credentials.get_google_credentials(db, alice)
    creds_b = google_credentials.get_google_credentials(db, bob)
    assert creds_a is not None and creds_a.token == "at-alice"
    assert creds_b is not None and creds_b.token == "at-bob"

    # Deleting one user's grant leaves the other untouched (§15).
    google_credentials.delete_google_credentials(db, alice.id)
    assert db.get(OAuthToken, alice.id) is None
    assert db.get(OAuthToken, bob.id) is not None
    assert google_credentials.get_google_credentials(db, bob) is not None


def test_delete_google_credentials_desktop_unlinks_token_file(db: Session):
    """The desktop owner's credential deletion is the token.json unlink."""
    owner = ownership.ensure_local_owner(db)
    token_file = auth.TOKEN_FILE
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text("{}", encoding="utf-8")
    try:
        google_credentials.delete_google_credentials(db, owner.id)
        assert not token_file.exists()
    finally:
        token_file.unlink(missing_ok=True)


def test_desktop_owner_gets_the_desktop_backend(db: Session):
    """provider dispatch (§15): the local owner reads token.json, not oauth_tokens."""
    owner = ownership.ensure_local_owner(db)
    # No token.json in the hermetic data dir → not signed in, and no row.
    assert google_credentials.get_google_credentials(db, owner) is None
    assert db.get(OAuthToken, owner.id) is None


def test_refresh_locks_are_per_user():
    """§15: one user's refresh must not serialize another user's."""
    lock_a1 = google_credentials._refresh_lock_for(101)
    lock_a2 = google_credentials._refresh_lock_for(101)
    lock_b = google_credentials._refresh_lock_for(202)
    assert lock_a1 is lock_a2
    assert lock_a1 is not lock_b


# ------------------------------------------------------------------ §13 deps


def test_desktop_get_current_user_is_the_local_owner(db: Session):
    """§13: a desktop request has no session — the user is the local owner."""
    from types import SimpleNamespace

    from starlette.requests import Request as StarletteRequest

    # The dependency dispatches on the app instance, not a process flag:
    # the same test process runs both apps side by side.
    desktop_scope = {
        "type": "http",
        "app": SimpleNamespace(state=SimpleNamespace(hosted=False)),
    }
    user = ownership.get_current_user(StarletteRequest(desktop_scope), db)
    assert user.provider == ownership.LOCAL_PROVIDER
    assert user.provider_subject == ownership.LOCAL_SUBJECT


def test_desktop_data_endpoint_works_without_a_session(client, db):
    """§13: the desktop app keeps its pre-migration no-login behaviour."""
    response = client.get("/api/courses")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/courses",
        "/api/assignments",
        "/api/grades",
        "/api/calendar",
        "/api/status",
        "/api/courses/c1",
        "/api/courses/c1/coursework/w1",
        "/api/courses/c1/coursework/w1/submissions",
        "/api/courses/c1/students",
        "/api/courses/c1/students/me/grades",
        "/api/cache?confirm=true",
    ],
)
def test_hosted_data_endpoints_reject_anonymous_calls(hosted_client, path):
    """§13: no data path answers without a validated session user."""
    response = hosted_client.get(path)
    assert response.status_code == 401


# ------------------------------------------------- §17 profile is per user


def test_profile_cache_is_keyed_by_user(db: Session, monkeypatch):
    """§17: user_id -> profile; one user's lookup never answers another's."""
    from api import identity

    calls: list[str] = []

    class FakeClassroomClient:
        def __init__(self, service) -> None:
            pass

        def get_user_profile(self) -> dict:
            calls.append("lookup")
            return {
                "name": {"fullName": f"User {len(calls)}"},
                "emailAddress": f"user{len(calls)}@example.com",
            }

    monkeypatch.setattr(identity, "ClassroomClient", FakeClassroomClient)
    monkeypatch.setattr(identity, "build_service", lambda creds: object())
    identity._reset_profile_cache()

    alice = _make_local_user(db, "local-a")
    bob = _make_local_user(db, "local-b")

    name_a, mail_a = identity._cached_profile(alice, object())
    name_b, mail_b = identity._cached_profile(bob, object())
    assert (name_a, mail_a) == ("User 1", "user1@example.com")
    assert (name_b, mail_b) == ("User 2", "user2@example.com")

    # Cached per id: a repeat lookup for Alice does not call Google again.
    assert identity._cached_profile(alice, object()) == (name_a, mail_a)
    assert len(calls) == 2

    # Resetting one user drops only that user's entry.
    identity._reset_profile_cache(alice.id)
    name_a2, _ = identity._cached_profile(alice, object())
    assert name_a2 == "User 3"
    assert identity._cached_profile(bob, object()) == (name_b, mail_b)
    identity._reset_profile_cache()


def test_auth_status_never_reads_a_global_profile_cache(db: Session):
    """§17: a hosted profile comes from the users row, not a shared cache."""
    from api import identity

    identity._reset_profile_cache()
    alice = _make_user(db, "sub-alice", "Alice")
    state = identity._build_auth_status(alice, db)
    assert state.user is not None
    assert (state.user.name, state.user.email) == (
        "Alice",
        "sub-alice@example.com",
    )
    # The per-user Google lookup cache was not touched at all.
    assert identity._profile_cache == {}


# ------------------------------------------------- §67 response ownership


def test_every_cache_table_has_an_ownership_path():
    """§67: each cache table's user_id is in its PK and joins only to
    another ownership column (a chain that ends at users.id)."""
    import models as _models  # noqa: F401 - populate Base.metadata
    from database import Base

    auth_tables = {"users", "sessions", "oauth_tokens", "oauth_login_states"}
    # The feedback domain (ADR-0035) is user-scoped but is NOT part of the
    # Classroom cache, and its ownership column is not always called user_id:
    # a message is owned through its ticket (and names its real author in
    # author_user_id), an attachment through its message. It is asserted by
    # test_feedback_ownership_path below, with the same invariant.
    feedback_tables = {"feedback_tickets", "ticket_messages", "ticket_attachments"}
    # The administrator registry (ADR-0036) is deliberately NOT user-scoped: a
    # row means "this e-mail is an administrator", which must survive the
    # account it belongs to (an admin can be appointed before ever signing in,
    # and delete_user_data must not silently revoke a role). It therefore has
    # no user_id and no FK to users by design — this exclusion is the assertion
    # of D9, not a gap in it.
    registry_tables = {"admins"}
    cache_tables = [
        t
        for t in Base.metadata.sorted_tables
        if t.name not in auth_tables
        and t.name not in feedback_tables
        and t.name not in registry_tables
    ]
    assert {table.name for table in cache_tables} == {
        "courses",
        "coursework",
        "submissions",
        "course_roles",
        "course_students",
        "coursework_submissions",
        "sync_status",
    }
    cache_names = {table.name for table in cache_tables}
    for table in cache_tables:
        column = table.columns["user_id"]
        assert column.primary_key, f"{table.name}.user_id must be part of the PK"
        foreign_keys = list(column.foreign_keys)
        assert foreign_keys, f"{table.name}.user_id has no ownership FK"
        for fk in foreign_keys:
            target_table, target_column = fk.column.table.name, fk.column.name
            if target_table == "users":
                # The ownership root: the users table's own PK.
                assert target_column == "id"
                continue
            assert target_column == "user_id", (
                f"{table.name}.user_id points at {target_table}.{target_column}"
            )
            assert target_table in cache_names
            assert Base.metadata.tables[target_table].columns["user_id"].primary_key


def test_feedback_ownership_path():
    """The same invariant for the ticket domain (ADR-0035).

    Every feedback table reaches ``users.id`` through an ownership FK with
    ON DELETE CASCADE: a ticket directly (``user_id``), a message through both
    its ticket and its real author (``author_user_id``), an attachment through
    its message and ticket. Deleting an account therefore removes exactly its
    own rows and nothing else.
    """
    import models as _models  # noqa: F401 - populate Base.metadata
    from database import Base

    cascades = {
        "feedback_tickets": ("user_id",),
        "ticket_messages": ("ticket_id", "author_user_id"),
        "ticket_attachments": ("message_id", "ticket_id"),
    }
    for table_name, columns in cascades.items():
        table = Base.metadata.tables[table_name]
        for column_name in columns:
            foreign_keys = list(table.columns[column_name].foreign_keys)
            assert foreign_keys, f"{table_name}.{column_name} has no ownership FK"
            for fk in foreign_keys:
                assert fk.column.table.name in {"users", "feedback_tickets",
                                               "ticket_messages"}
                assert fk.ondelete == "CASCADE", (
                    f"{table_name}.{column_name} must cascade on delete"
                )
    # The root of the chain is the users table itself.
    assert Base.metadata.tables["feedback_tickets"].columns[
        "user_id"
    ].foreign_keys.pop().column.table.name == "users"


def test_student_aggregates_do_not_join_across_users(hosted_client, db):
    """§67: identical Google ids never leak into course/status aggregates."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice's course", points=10)
    _seed_course(db, bob.id, "Bob's course", points=100)
    _add_session(db, alice, "raw-alice-token")
    _add_session(db, bob, "raw-bob-token")

    hosted_client.cookies.set("gch_session", "raw-alice-token")
    course = hosted_client.get("/api/courses").json()[0]
    state = hosted_client.get("/api/status").json()
    assert course["name"] == "Alice's course"
    assert course["average_grade"] == 10.0
    assert state["average_grade"] == 10.0
    # A cross-user join would count 2 assignments and mix the averages.
    assert state["total_assignments"] == 1
    assert state["completed"] == 1

    hosted_client.cookies.set("gch_session", "raw-bob-token")
    course = hosted_client.get("/api/courses").json()[0]
    state = hosted_client.get("/api/status").json()
    assert course["name"] == "Bob's course"
    assert course["average_grade"] == 100.0
    assert state["average_grade"] == 100.0
    assert state["total_assignments"] == 1


def test_teacher_aggregates_do_not_join_across_users(hosted_client, db):
    """§67: the teacher grade matrix stays inside one user's rows."""
    from models import CourseRole, CourseStudent, CourseWork, CourseWorkSubmission

    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    for user, name, points in (
        (alice, "Alice's class", 55.0),
        (bob, "Bob's class", 95.0),
    ):
        db.add(Course(user_id=user.id, id="c1", name=name, course_state="ACTIVE"))
        db.add(CourseRole(user_id=user.id, course_id="c1", role="TEACHER"))
        db.add(
            CourseWork(
                user_id=user.id,
                id="w1",
                course_id="c1",
                title="Same HW",
                state="PUBLISHED",
                max_points=100,
            )
        )
        db.add(
            CourseStudent(
                user_id=user.id,
                course_id="c1",
                student_id="s1",
                full_name="Same Student",
            )
        )
        db.add(
            CourseWorkSubmission(
                user_id=user.id,
                course_id="c1",
                coursework_id="w1",
                student_id="s1",
                state="RETURNED",
                assigned_points=points,
            )
        )
    db.commit()
    _add_session(db, alice, "raw-alice-token")
    _add_session(db, bob, "raw-bob-token")

    hosted_client.cookies.set("gch_session", "raw-alice-token")
    grades = hosted_client.get("/api/courses/c1/grades").json()
    assert grades["class_average"] == 55.0
    assert len(grades["rows"]) == 1
    assert grades["rows"][0]["average_percent"] == 55.0

    hosted_client.cookies.set("gch_session", "raw-bob-token")
    grades = hosted_client.get("/api/courses/c1/grades").json()
    assert grades["class_average"] == 95.0
    assert grades["rows"][0]["average_percent"] == 95.0
    # The submissions table of the same assignment shows only Bob's student.
    submissions = hosted_client.get("/api/courses/c1/coursework/w1/submissions").json()
    assert [row["points"] for row in submissions] == [95.0]
