# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""User-scoped cache schema (migration stage 3, §10).

The core invariant under test: a Google course/coursework id is unique only
WITHIN one user's cache (audit M1/M2/M3/M4). Two users must be able to hold
identical Google ids at the same time, and no read/write/purge/reset path
may mix their rows.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from auth import ownership
from db.models.accounts import User
from db.models.classroom import (
    Course,
    CourseRole,
    CourseWork,
    StudentSubmission,
)
from db.session import _build_engine
from sync import store
from sync.store import cache


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc(year: int, month: int, day: int) -> datetime:
    """Naive UTC timestamp — the convention of the user-scoped tables.

    The sync_status columns are naive (DateTime without tz), so tests
    compare them against naive values; the tzinfo here only keeps the
    datetime constructor explicit about which clock is meant.
    """
    return datetime(year, month, day, tzinfo=timezone.utc).replace(tzinfo=None)


def _make_user(db: Session, subject: str) -> User:
    user = User(
        provider="google",
        provider_subject=subject,
        email=f"{subject}@example.com",
        display_name=subject,
        created_at=_now(),
        updated_at=_now(),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _seed_course(db: Session, user_id: int, name: str) -> None:
    db.add(Course(user_id=user_id, id="c1", name=name, course_state="ACTIVE"))
    db.add(CourseRole(user_id=user_id, course_id="c1", role="STUDENT"))
    db.add(
        CourseWork(
            user_id=user_id,
            id="w1",
            course_id="c1",
            title=name,
            state="PUBLISHED",
        )
    )
    db.add(
        StudentSubmission(
            user_id=user_id,
            course_id="c1",
            coursework_id="w1",
            state="RETURNED",
            assigned_points=70,
        )
    )
    # Structured per-user sync state (stage 5) instead of the key/value row.
    store.mark_sync_succeeded(db, user_id, _utc(2026, 9, 19))
    db.commit()


# ------------------------------------------------------------ §10 uniqueness


def test_same_google_course_id_for_two_users(db: Session):
    """The audit M2 fix: Google ids collide only across users, never within."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice's view")
    _seed_course(db, bob.id, "Bob's view")

    names = {
        user_id: name
        for user_id, name in db.execute(select(Course.user_id, Course.name)).all()
    }
    assert names[alice.id] == "Alice's view"
    assert names[bob.id] == "Bob's view"
    # Role and submission rows exist per user too, same Google ids.
    roles = {
        user_id: role
        for user_id, role in db.execute(
            select(CourseRole.user_id, CourseRole.role)
        ).all()
    }
    assert roles == {alice.id: "STUDENT", bob.id: "STUDENT"}


def test_get_submission_respects_the_owner(db: Session):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice")
    _seed_course(db, bob.id, "Bob")

    a = store.get_submission(db, alice.id, "c1", "w1", "me", is_teacher=False)
    b = store.get_submission(db, bob.id, "c1", "w1", "me", is_teacher=False)
    assert a is not None and b is not None
    assert a.user_id == alice.id
    assert b.user_id == bob.id
    # A third user has no row even though the Google ids all match.
    carol = _make_user(db, "sub-carol")
    assert (
        store.get_submission(db, carol.id, "c1", "w1", "me", is_teacher=False)
        is None
    )


def test_sync_status_is_per_user(db: Session):
    """Stage 5 (§18): one structured row per user, never shared."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    early = _utc(2026, 9, 19)
    later = _utc(2026, 9, 20)
    store.mark_sync_succeeded(db, alice.id, early)
    store.mark_sync_succeeded(db, bob.id, later)
    assert store.last_sync_time(db, alice.id) == early
    assert store.last_sync_time(db, bob.id) == later

    # A failure is recorded against ITS user only, with a sanitized message.
    message = "Google API error (HTTP 500); the next sync will retry."
    store.mark_sync_failed(db, alice.id, message, later)
    assert store.last_sync_error(db, alice.id) == message
    assert store.last_sync_error(db, bob.id) is None
    alice_row = store.sync_status(db, alice.id)
    bob_row = store.sync_status(db, bob.id)
    assert alice_row is not None and alice_row.status == store.SYNC_ERROR
    assert alice_row.consecutive_failures == 1
    assert bob_row is not None and bob_row.status == store.SYNC_OK
    assert bob_row.consecutive_failures == 0


def test_purge_stale_courses_keeps_other_users(db: Session):
    """The audit Y3 invariant: a purge scoped to one owner never touches
    another user's identical course id."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice")
    _seed_course(db, bob.id, "Bob")

    # The API no longer returns c1 for alice, but still does for bob.
    cache._purge_stale_courses(db, alice.id, set())
    remaining = {user_id for (user_id,) in db.execute(select(Course.user_id)).all()}
    assert remaining == {bob.id}


def test_reset_cache_only_deletes_the_caller_rows(db: Session):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice")
    _seed_course(db, bob.id, "Bob")

    store.reset_cache(db, alice.id)
    assert db.query(Course).filter_by(user_id=alice.id).count() == 0
    assert db.query(Course).filter_by(user_id=bob.id).count() == 1
    assert db.query(StudentSubmission).filter_by(user_id=bob.id).count() == 1
    # The sync state of the caller is gone, the other user's is intact.
    assert store.last_sync_time(db, alice.id) is None
    assert store.last_sync_time(db, bob.id) == _utc(2026, 9, 19)


def test_deleting_a_user_cascades_their_cache(db: Session):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice")
    _seed_course(db, bob.id, "Bob")

    db.delete(alice)
    db.commit()
    assert db.query(Course).count() == 1
    assert db.query(Course).one().user_id == bob.id


def test_cascade_from_course_removal(db: Session):
    alice = _make_user(db, "sub-alice")
    _seed_course(db, alice.id, "Alice")
    db.execute(delete(Course).where(Course.user_id == alice.id, Course.id == "c1"))
    db.commit()
    assert db.query(CourseWork).count() == 0
    assert db.query(StudentSubmission).count() == 0
    assert db.query(CourseRole).count() == 0


# ----------------------------------------------------------- ownership seam


def test_local_owner_is_created_once(db: Session):
    first = ownership.local_owner_id(db)
    second = ownership.local_owner_id(db)
    assert first == second
    locals_count = (
        db.query(func.count(User.id))
        .filter(User.provider == ownership.LOCAL_PROVIDER)
        .scalar()
    )
    assert locals_count == 1


# ------------------------------------------------------- engine selection


def test_database_url_selects_the_postgres_dialect(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:pw@localhost:5432/gch")
    engine = _build_engine()
    assert engine.dialect.name == "postgresql"
    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.database == "gch"


def test_hosted_mode_without_database_url_fails_closed(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from db import session as database

    monkeypatch.setattr(database, "HOSTED_MODE", True)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database._build_engine()


# -------------------------------------------------- hosted end-to-end scope


def _add_session(db: Session, user: User, raw_token: str) -> None:
    """A valid session row without the OAuth dance (identity is stage-2 code)."""
    from auth import hosted
    from db.models.accounts import UserSession

    now = _now()
    db.add(
        UserSession(
            session_token_hash=hosted._sha256_hex(raw_token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(days=1),
            last_seen_at=now,
        )
    )
    db.commit()


def test_two_hosted_sessions_see_only_their_own_cache(hosted_client, db):
    """The gate → request.state.user_id → _owner_id → scoped read path."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _seed_course(db, alice.id, "Alice's course")
    _seed_course(db, bob.id, "Bob's course")
    _add_session(db, alice, "raw-alice-token")
    _add_session(db, bob, "raw-bob-token")

    hosted_client.cookies.set("gch_session", "raw-alice-token")
    body = hosted_client.get("/api/courses")
    assert body.status_code == 200
    courses = body.json()
    assert [c["name"] for c in courses] == ["Alice's course"]

    hosted_client.cookies.set("gch_session", "raw-bob-token")
    courses = hosted_client.get("/api/courses").json()
    assert [c["name"] for c in courses] == ["Bob's course"]

    # The status endpoint's sync state is per user as well.
    hosted_client.cookies.set("gch_session", "raw-alice-token")
    status = hosted_client.get("/api/status").json()
    assert status["last_sync"] == "2026-09-19T00:00:00"
