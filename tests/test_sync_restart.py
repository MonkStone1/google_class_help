# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Restart of a stuck synchronization (ADR-0032).

The dashboard could tell the user "this sync is stuck, try syncing again" and
offer no way to do it: the Sync button is disabled exactly while ``syncing`` is
true, and the server answered 409 to any manual request for a user whose claim
was in flight. These tests pin the replacement:

- ``abandon_claim`` releases ONLY a claim older than the threshold — a long but
  progressing Classroom import is never interrupted, and a second concurrent
  restart cannot release the same claim twice;
- the release leaves ``last_finished_at``/``last_success_at`` alone, because
  ``SyncToaster`` treats a moved finish stamp as a finished run and would
  announce a failure that never happened (ADR-0030);
- the fence: a run whose claim was taken over while it was fetching writes
  nothing — not the cache, not the purge, not the terminal status;
- ``POST /api/sync`` still answers 409 without ``restart=true``, so the ordinary
  double-click protection of §3.9 / ADR-0027 is unchanged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import hosted_auth
import metrics
import sync_service
import sync_store
from config import SYNC_STUCK_SECONDS
from database import SessionLocal
from models import Course, SyncStatus
from models_auth import User, UserSession


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc).replace(tzinfo=None)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(db, subject: str) -> User:
    user = User(
        provider="google",
        provider_subject=subject,
        email=f"{subject}@example.com",
        display_name=subject,
        created_at=_utc(2026, 9, 30),
        updated_at=_utc(2026, 9, 30),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add_session(db, user: User, raw_token: str) -> UserSession:
    base = _now()
    session = UserSession(
        session_token_hash=hosted_auth._sha256_hex(raw_token),
        user_id=user.id,
        created_at=base,
        expires_at=base + timedelta(hours=14),
        last_seen_at=base,
    )
    db.add(session)
    db.commit()
    return session


def _claim(user_id: int, started_at: datetime) -> None:
    """Put the user's row into the state a running sync leaves behind.

    A separate session, exactly like the worker that owns the claim: the test's
    ``db`` fixture holds its own connection and must not stand in for it.
    """
    with SessionLocal() as own:
        own.add(
            SyncStatus(
                user_id=user_id,
                status=sync_store.SYNC_RUNNING,
                last_started_at=started_at,
                sync_requested=False,
            )
        )
        own.commit()


class _FakeStats:
    """Minimal stand-in for RequestStats — the fence must not need counters."""

    def snapshot(self) -> dict[str, int]:
        return {"requests": 3, "quota_errors": 0, "server_errors": 0}
# ------------------------------------------------------- abandon_claim guards


def test_abandon_claim_refuses_a_running_but_young_claim(db):
    """The threshold is the whole point: a slow import is not a stuck one."""
    user = _make_user(db, "sub-young")
    _claim(user.id, _now() - timedelta(seconds=30))

    assert sync_store.abandon_claim(db, user.id, _now(), older_than=300) is False
    row = db.get(SyncStatus, user.id)
    assert row is not None
    assert row.status == sync_store.SYNC_RUNNING


def test_abandon_claim_releases_a_stale_claim(db):
    user = _make_user(db, "sub-stuck")
    _claim(user.id, _now() - timedelta(seconds=3600))

    assert sync_store.abandon_claim(db, user.id, _now(), older_than=300) is True
    row = db.get(SyncStatus, user.id)
    assert row is not None
    assert row.status == sync_store.SYNC_PENDING
    # Released, so the next run claims it without waiting out the
    # SYNC_CLAIM_STALE_SECONDS backstop.
    assert sync_store.claim_sync(db, user.id, _now(), stale_after=3600) is True


def test_abandon_claim_twice_reports_only_the_first_release(db):
    """Two racing restart clicks must not both "succeed" — the claim is one row."""
    user = _make_user(db, "sub-double")
    _claim(user.id, _now() - timedelta(seconds=3600))

    assert sync_store.abandon_claim(db, user.id, _now(), older_than=300) is True
    assert sync_store.abandon_claim(db, user.id, _now(), older_than=300) is False


def test_abandon_claim_leaves_the_timestamps_that_the_toaster_reads(db):
    """ADR-0030: a moved finish stamp would be announced as a failed sync."""
    user = _make_user(db, "sub-stamps")
    finished = _utc(2026, 9, 29)
    succeeded = _utc(2026, 9, 28)
    db.add(
        SyncStatus(
            user_id=user.id,
            status=sync_store.SYNC_RUNNING,
            last_started_at=_now() - timedelta(seconds=3600),
            last_finished_at=finished,
            last_success_at=succeeded,
            consecutive_failures=2,
        )
    )
    db.commit()

    assert sync_store.abandon_claim(db, user.id, _now(), older_than=300) is True
    row = db.get(SyncStatus, user.id)
    assert row is not None
    # Untouched: SyncToaster compares last_sync_finished_at and would fire.
    assert row.last_finished_at == finished
    # ADR-0027 §61: the age of the cache still on screen must stay visible.
    assert row.last_success_at == succeeded
    # An abandoned attempt is not an account failure: the retry backoff must
    # not be inflated by a run that never reported anything.
    assert row.consecutive_failures == 2


def test_abandon_claim_is_confined_to_its_owner(db):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _claim(bob.id, _now() - timedelta(seconds=3600))

    assert sync_store.abandon_claim(db, alice.id, _now(), older_than=300) is False
    assert db.get(SyncStatus, bob.id).status == sync_store.SYNC_RUNNING
# ---------------------------------------------------------------- the fence


def test_claim_is_own_recognises_the_current_holder(db):
    user = _make_user(db, "sub-owner")
    claimed_at = _now() - timedelta(seconds=10)
    _claim(user.id, claimed_at)

    assert sync_store.claim_is_own(db, user.id, claimed_at) is True
    # A different run's timestamp, and a moment that was never claimed.
    assert sync_store.claim_is_own(db, user.id, _now()) is False
    assert (
        sync_store.claim_is_own(db, user.id, claimed_at - timedelta(hours=1)) is False
    )


def test_claim_is_own_is_false_after_the_claim_was_taken_over(db):
    user = _make_user(db, "sub-taken")
    old_claim = _now() - timedelta(seconds=3600)
    _claim(user.id, old_claim)
    assert sync_store.claim_is_own(db, user.id, old_claim) is True

    # The restart releases the claim and the replacement run claims it.
    assert sync_store.abandon_claim(db, user.id, _now(), older_than=300) is True
    new_claim = _now()
    assert sync_store.claim_sync(db, user.id, new_claim, stale_after=3600) is True
    # The zombie run must now see that it lost the row.
    assert sync_store.claim_is_own(db, user.id, old_claim) is False


def test_superseded_run_writes_neither_cache_nor_status(db):
    """The regression that motivated the fence: a replaced run must not write.

    ``_write_sync_results`` is the only place a sync touches the cache. Without
    the fence this run would purge courses from its own older snapshot — and
    then stamp ``ok`` over the replacement run that is still in flight.
    """
    metrics.reset()
    user = _make_user(db, "sub-zombie")
    old_claim = _now() - timedelta(seconds=3600)
    _claim(user.id, old_claim)
    # A course the newer run has already cached: the zombie would purge it if
    # it were allowed to write its own (older) snapshot.
    db.add(Course(user_id=user.id, id="course_new", name="New course"))
    db.commit()

    # The claim moved on: this run is no longer the owner.
    sync_store.claim_sync(db, user.id, _now(), stale_after=3600)

    result = sync_service._write_sync_results(
        user.id,
        courses=[{"id": "course_old", "name": "Old"}],
        active_ids={"course_old"},
        teacher_names={},
        payloads={"course_old": {"submissions": []}},
        work_cache={},
        stats=_FakeStats(),
        started_monotonic=0.0,
        started_at=old_claim,
    )

    assert result == {"ok": False, "error": sync_service.SUPERSEDED}
    # Nothing written, nothing purged, no "ok" recorded.
    assert db.get(Course, (user.id, "course_old")) is None
    assert db.get(Course, (user.id, "course_new")) is not None
    assert db.get(SyncStatus, user.id).status == sync_store.SYNC_RUNNING
    assert metrics.snapshot().get(metrics.SYNC_SUCCEEDED) is None
    metrics.reset()


def test_owning_run_still_writes(db, monkeypatch):
    """The fence must not disable the normal path: an owner writes as before."""
    user = _make_user(db, "sub-owner-writes")
    claimed_at = _now()
    _claim(user.id, claimed_at)
    monkeypatch.setattr(
        sync_service,
        "_write_teacher_course",
        lambda db, user_id, course_id, payload: 0,
    )

    result = sync_service._write_sync_results(
        user.id,
        # ``courses`` is the (raw_course, role) pairs the fetch stages produce.
        courses=[({"id": "course_a", "name": "Course A"}, "TEACHER")],
        active_ids={"course_a"},
        teacher_names={},
        payloads={"course_a": {"coursework": [], "submissions": []}},
        work_cache={},
        stats=_FakeStats(),
        started_monotonic=0.0,
        started_at=claimed_at,
    )

    assert result["ok"] is True
    assert db.get(Course, (user.id, "course_a")) is not None
    row = db.get(SyncStatus, user.id)
    assert row is not None
    assert row.status == sync_store.SYNC_OK
    assert row.last_success_at is not None
# --------------------------------------------------------- the hosted endpoint


def _sign_in(hosted_client, db, subject: str) -> User:
    user = _make_user(db, subject)
    _add_session(db, user, f"raw-{subject}")
    hosted_client.cookies.set("gch_session", f"raw-{subject}")
    return user


def test_restart_replaces_a_stuck_claim(hosted_client, db):
    user = _sign_in(hosted_client, db, "sub-restart")
    _claim(user.id, _now() - timedelta(seconds=3600))

    response = hosted_client.post("/api/sync?restart=true")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    # Hosted still answers immediately: the worker does the fan-out (§9).
    assert body["queued"] is True
    assert body["restarted"] is True

    row = db.get(SyncStatus, user.id)
    assert row is not None
    # Released and re-queued, so the worker's next scan picks it up.
    assert row.status == sync_store.SYNC_PENDING
    assert row.sync_requested is True


def test_restart_is_refused_while_the_sync_is_healthy(hosted_client, db):
    """A progressing import must never be interrupted by an eager restart."""
    user = _sign_in(hosted_client, db, "sub-healthy")
    _claim(user.id, _now() - timedelta(seconds=30))

    response = hosted_client.post("/api/sync?restart=true")
    assert response.status_code == 409
    row = db.get(SyncStatus, user.id)
    assert row is not None
    assert row.status == sync_store.SYNC_RUNNING
    assert row.sync_requested is False


def test_plain_sync_still_answers_409_for_a_stuck_claim(hosted_client, db):
    """The pre-existing double-click guard is untouched by the new flag."""
    user = _sign_in(hosted_client, db, "sub-plain")
    _claim(user.id, _now() - timedelta(seconds=3600))

    assert hosted_client.post("/api/sync").status_code == 409


def test_restart_touches_only_the_calling_user(hosted_client, db):
    alice = _sign_in(hosted_client, db, "sub-alice-restart")
    bob = _make_user(db, "sub-bob-restart")
    _claim(alice.id, _now() - timedelta(seconds=3600))
    _claim(bob.id, _now() - timedelta(seconds=3600))

    assert hosted_client.post("/api/sync?restart=true").status_code == 200

    assert db.get(SyncStatus, alice.id).status == sync_store.SYNC_PENDING
    # Bob's stuck sync is his own business (§12).
    assert db.get(SyncStatus, bob.id).status == sync_store.SYNC_RUNNING


def test_restart_requires_a_session(hosted_client, db):
    _make_user(db, "sub-anonymous")
    assert hosted_client.post("/api/sync?restart=true").status_code == 401


def test_status_publishes_the_threshold_the_restart_uses(hosted_client, db):
    """The UI must not offer a restart the server refuses, nor hide one it allows."""
    _sign_in(hosted_client, db, "sub-threshold")

    published = hosted_client.get("/api/status").json()["sync_stuck_after_seconds"]

    assert published == SYNC_STUCK_SECONDS
    assert published > 0


def test_restart_is_counted_separately_from_a_refusal(hosted_client, db):
    """§60: "people hit stuck syncs" and "the threshold is wrong" are different."""
    metrics.reset()
    try:
        user = _sign_in(hosted_client, db, "sub-metrics")
        _claim(user.id, _now() - timedelta(seconds=30))
        assert hosted_client.post("/api/sync?restart=true").status_code == 409
        assert metrics.snapshot()[metrics.SYNC_RESTART_REJECTED] == 1

        # Now genuinely stuck: the same call succeeds and is counted as such.
        # Age the existing claim rather than re-claiming, so the row keeps its
        # identity (the restart must find a RUNNING row it may release).
        row = db.get(SyncStatus, user.id)
        row.last_started_at = _now() - timedelta(seconds=3600)
        db.commit()
        assert hosted_client.post("/api/sync?restart=true").status_code == 200
        assert metrics.snapshot()[metrics.SYNC_RESTARTED] == 1
    finally:
        metrics.reset()
# ------------------------------------------------------ the desktop endpoint


def test_desktop_restart_releases_a_stale_claim_then_runs(client, db):
    """Desktop has no queue: the restart releases the claim and runs inline."""
    import ownership

    owner = ownership.ensure_local_owner(db)
    db.commit()
    _claim(owner.id, _now() - timedelta(seconds=3600))

    # A signed-out desktop sync is the observable outcome of a claim that WAS
    # taken, i.e. the inline run really started instead of answering 409.
    assert client.post("/api/sync?restart=true").status_code == 200
    assert db.get(SyncStatus, owner.id).status == sync_store.SYNC_PENDING


def test_desktop_restart_is_refused_while_the_sync_is_healthy(client, db):
    import ownership

    owner = ownership.ensure_local_owner(db)
    db.commit()
    _claim(owner.id, _now() - timedelta(seconds=30))

    assert client.post("/api/sync?restart=true").status_code == 409
    assert db.get(SyncStatus, owner.id).status == sync_store.SYNC_RUNNING


def test_desktop_restart_says_so_when_the_hung_thread_holds_the_lock(client, db):
    """The claim is released even when a second fan-out cannot start yet."""
    import ownership

    owner = ownership.ensure_local_owner(db)
    db.commit()
    _claim(owner.id, _now() - timedelta(seconds=3600))
    lock = sync_service._sync_lock_for(owner.id)
    lock.acquire()
    try:
        response = client.post("/api/sync?restart=true")
    finally:
        lock.release()

    assert response.status_code == 409
    assert "shutting down" in response.json()["detail"]
    # The important half: the stale claim is gone, so the next attempt works.
    assert db.get(SyncStatus, owner.id).status == sync_store.SYNC_PENDING


@pytest.mark.parametrize("age_seconds", [0, 60, 299])
def test_no_age_below_the_threshold_is_ever_abandoned(db, age_seconds):
    """Boundary guard: only a claim past the threshold may be released."""
    user = _make_user(db, f"sub-boundary-{age_seconds}")
    _claim(user.id, _now() - timedelta(seconds=age_seconds))

    released = sync_store.abandon_claim(
        db, user.id, _now(), older_than=SYNC_STUCK_SECONDS
    )

    assert released is False
    assert db.get(SyncStatus, user.id).status == sync_store.SYNC_RUNNING