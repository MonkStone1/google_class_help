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
  double-click protection of В§3.9 / ADR-0027 is unchanged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from auth import hosted
from core import metrics
from core.config import SYNC_STUCK_SECONDS
from db.models.accounts import OAuthToken, User, UserSession
from db.models.classroom import Course, SyncStatus
from db.session import SessionLocal
from gapi import oauth_transport
from gapi.classroom import RequestStats
from sync import scheduler, store
from sync.service import _fetch, results


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc).replace(tzinfo=None)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(db, subject: str, *, created_at: datetime | None = None) -> User:
    user = User(
        provider="google",
        provider_subject=subject,
        email=f"{subject}@example.com",
        display_name=subject,
        created_at=created_at or _utc(2026, 9, 30),
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
        session_token_hash=hosted._sha256_hex(raw_token),
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
                status=store.SYNC_RUNNING,
                last_started_at=started_at,
                sync_requested=False,
            )
        )
        own.commit()


def _add_grant(db, user: User) -> None:
    """A stored Google grant, so ``select_due_users`` considers the account.

    The selection joins ``oauth_tokens``: without a grant the user is never a
    candidate, and the test below would pass for the wrong reason.
    """
    now = _now()
    db.add(
        OAuthToken(
            user_id=user.id,
            access_token="enc.v1:test",
            token_uri="https://oauth2.googleapis.com/token",
            scopes=list(oauth_transport.SCOPES),
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


class _FakeStats(RequestStats):
    """Minimal stand-in for RequestStats — the fence must not need counters.

    Subclasses the real class so it satisfies ``_write_sync_results``'s
    ``stats: RequestStats`` parameter by inheritance; only ``snapshot()`` is
    overridden, which is the single method the fence reads.
    """

    def snapshot(self) -> dict[str, int]:
        return {"requests": 3, "quota_errors": 0, "server_errors": 0}


# ------------------------------------------------------- abandon_claim guards


def test_abandon_claim_refuses_a_running_but_young_claim(db):
    """The threshold is the whole point: a slow import is not a stuck one."""
    user = _make_user(db, "sub-young")
    _claim(user.id, _now() - timedelta(seconds=30))

    assert store.abandon_claim(db, user.id, _now(), older_than=300) is False
    row = db.get(SyncStatus, user.id)
    assert row is not None
    assert row.status == store.SYNC_RUNNING


def test_abandon_claim_releases_a_stale_claim(db):
    user = _make_user(db, "sub-stuck")
    _claim(user.id, _now() - timedelta(seconds=3600))

    assert store.abandon_claim(db, user.id, _now(), older_than=300) is True
    row = db.get(SyncStatus, user.id)
    assert row is not None
    assert row.status == store.SYNC_PENDING
    # Released, so the next run claims it without waiting out the
    # SYNC_CLAIM_STALE_SECONDS backstop.
    assert store.claim_sync(db, user.id, _now(), stale_after=3600) is True


def test_abandon_claim_twice_reports_only_the_first_release(db):
    """Two racing restart clicks must not both "succeed" — the claim is one row."""
    user = _make_user(db, "sub-double")
    _claim(user.id, _now() - timedelta(seconds=3600))

    assert store.abandon_claim(db, user.id, _now(), older_than=300) is True
    assert store.abandon_claim(db, user.id, _now(), older_than=300) is False


def test_abandon_claim_leaves_the_timestamps_that_the_toaster_reads(db):
    """ADR-0030: a moved finish stamp would be announced as a failed sync."""
    user = _make_user(db, "sub-stamps")
    finished = _utc(2026, 9, 29)
    succeeded = _utc(2026, 9, 28)
    db.add(
        SyncStatus(
            user_id=user.id,
            status=store.SYNC_RUNNING,
            last_started_at=_now() - timedelta(seconds=3600),
            last_finished_at=finished,
            last_success_at=succeeded,
            consecutive_failures=2,
        )
    )
    db.commit()

    assert store.abandon_claim(db, user.id, _now(), older_than=300) is True
    row = db.get(SyncStatus, user.id)
    assert row is not None
    # Untouched: SyncToaster compares last_sync_finished_at and would fire.
    assert row.last_finished_at == finished
    # ADR-0027 В§61: the age of the cache still on screen must stay visible.
    assert row.last_success_at == succeeded
    # An abandoned attempt is not an account failure: the retry backoff must
    # not be inflated by a run that never reported anything.
    assert row.consecutive_failures == 2


def test_abandon_claim_is_confined_to_its_owner(db):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _claim(bob.id, _now() - timedelta(seconds=3600))

    assert store.abandon_claim(db, alice.id, _now(), older_than=300) is False
    assert db.get(SyncStatus, bob.id).status == store.SYNC_RUNNING
# ---------------------------------------------------------------- the fence


def test_claim_is_own_recognises_the_current_holder(db):
    user = _make_user(db, "sub-owner")
    claimed_at = _now() - timedelta(seconds=10)
    _claim(user.id, claimed_at)

    assert store.claim_is_own(db, user.id, claimed_at) is True
    # A different run's timestamp, and a moment that was never claimed.
    assert store.claim_is_own(db, user.id, _now()) is False
    assert (
        store.claim_is_own(db, user.id, claimed_at - timedelta(hours=1)) is False
    )


def test_claim_is_own_is_false_after_the_claim_was_taken_over(db):
    user = _make_user(db, "sub-taken")
    old_claim = _now() - timedelta(seconds=3600)
    _claim(user.id, old_claim)
    assert store.claim_is_own(db, user.id, old_claim) is True

    # The restart releases the claim and the replacement run claims it.
    assert store.abandon_claim(db, user.id, _now(), older_than=300) is True
    new_claim = _now()
    assert store.claim_sync(db, user.id, new_claim, stale_after=3600) is True
    # The zombie run must now see that it lost the row.
    assert store.claim_is_own(db, user.id, old_claim) is False


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
    store.claim_sync(db, user.id, _now(), stale_after=3600)

    result = results.write_sync_results(
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

    assert result == {"ok": False, "error": results.SUPERSEDED}
    # Nothing written, nothing purged, no "ok" recorded.
    assert db.get(Course, (user.id, "course_old")) is None
    assert db.get(Course, (user.id, "course_new")) is not None
    assert db.get(SyncStatus, user.id).status == store.SYNC_RUNNING
    assert metrics.snapshot().get(metrics.SYNC_SUCCEEDED) is None
    metrics.reset()


# ------------------------------------------- per-course fence (write phase)


def test_claim_lost_mid_write_stops_the_loop_instead_of_colliding(db):
    """The fence must be re-checked INSIDE the per-course write loop.

    The write phase commits after every course, so on a teacher account with
    hundreds of courses it stays open for minutes. A restart releases the claim
    in exactly that window, and the replaced run is still holding its own
    per-course commit loop. With the check only before the loop, both runs wrote
    the same course: two INSERTs of one coursework id, and the loser died on
    ``duplicate key value violates unique constraint
    coursework_submissions_pkey`` — reported to the user as "Sync failed" even
    though Google had delivered everything.
    """
    metrics.reset()
    user = _make_user(db, "sub-midwrite")
    claimed_at = _now()
    _claim(user.id, claimed_at)

    written: list[str] = []
    monkey_calls = {"n": 0}

    def _fake_write(db_, user_id, course_id, payload):
        # The replacement run takes the claim while this run is already inside
        # the loop — the moment the old one-check-per-run fence missed. A restart
        # releases the claim (abandon_claim) and the worker re-claims it, which
        # is what a user clicking "restart the stuck sync" produces.
        #
        # Taken through the SAME session on purpose. A second session cannot
        # write here at all: the run holds an open transaction from the course
        # it just committed, and file-backed SQLite refuses the other writer
        # ("database is locked") — an artifact of the test backend, not of the
        # hosted PostgreSQL deployment this fence is about. Same session is
        # enough to model the takeover: the claim row really does change under
        # the running loop, which is the state the fence has to notice.
        written.append(course_id)
        monkey_calls["n"] += 1
        if monkey_calls["n"] == 2:
            assert store.abandon_claim(db_, user_id, _now(), older_than=0)
            assert store.claim_sync(db_, user_id, _now(), stale_after=3600)
        return 0


    original = results._write_teacher_course
    results._write_teacher_course = _fake_write
    try:
        result = results.write_sync_results(
            user.id,
            courses=[
                ({"id": "c1", "name": "One"}, "TEACHER"),
                ({"id": "c2", "name": "Two"}, "TEACHER"),
                ({"id": "c3", "name": "Three"}, "TEACHER"),
            ],
            active_ids={"c1", "c2", "c3"},
            teacher_names={},
            payloads={
                cid: {"coursework": [], "submissions": []} for cid in ("c1", "c2", "c3")
            },
            work_cache={},
            stats=_FakeStats(),
            started_monotonic=0.0,
            started_at=claimed_at,
        )
    finally:
        results._write_teacher_course = original

    assert result == {"ok": False, "error": results.SUPERSEDED}
    # Stopped at the course where the claim was gone; never reached c3.
    assert written == ["c1", "c2"]
    assert db.get(Course, (user.id, "c3")) is None
    # The run that owns the row now reports the outcome, not the zombie.
    assert db.get(SyncStatus, user.id).status == store.SYNC_RUNNING
    assert metrics.snapshot().get(metrics.SYNC_SUCCEEDED) is None
    metrics.reset()


def test_claim_sync_logs_only_a_stale_takeover(db, caplog):
    """A takeover is the only event that can cause a duplicate key — log it.

    It is also invisible otherwise: the loser of the race is fenced and its
    writes become harmless, so the next occurrence of the reported symptom has
    no trace in the log to correlate with. The line must fire for a takeover
    and NOT for an ordinary claim, or it becomes noise nobody reads.
    """
    user = _make_user(db, "sub-takeover-log")
    now = _now()

    # An ordinary first claim: nothing was running before it.
    with caplog.at_level("WARNING", logger="sync.store"):
        assert store.claim_sync(db, user.id, now, stale_after=600) is True
    assert "stale sync claim" not in caplog.text

    # A second claim inside the window is refused, and must stay quiet too.
    with caplog.at_level("WARNING", logger="sync.store"):
        assert (
            store.claim_sync(db, user.id, now + timedelta(seconds=30), stale_after=600)
            is False
        )
    assert "stale sync claim" not in caplog.text

    # Past the window: the takeover this log line exists for.
    caplog.clear()
    with caplog.at_level("WARNING", logger="sync.store"):
        assert (
            store.claim_sync(
                db, user.id, now + timedelta(seconds=601), stale_after=600
            )
            is True
        )
    assert "stale sync claim" in caplog.text
    assert f"user={user.id}" in caplog.text
    # The age is in the line, so the next occurrence is diagnosable from it.
    assert "601 s ago" in caplog.text


def test_a_running_user_is_due_again_once_the_window_passes(db):
    """The structural half: a ``running`` user is offered to the scheduler.

    ``next_sync_at`` reads ``last_finished_at or last_started_at``, so for a user
    mid-sync that is the PREVIOUS run's finish — hours old — and the account
    looks due immediately. ``claim_sync`` is what stops the second run, and only
    for as long as the claim is younger than ``stale_after``. That is precisely
    how a legitimately slow teacher sync ends up racing a replacement: the window
    is 600 s on compose.local.yml, and a write phase over hundreds of courses
    can outlast it.

    Pinned as documentation of the interaction, not as an endorsement: the
    fence (ADR-0032) and the conditional write (ADR-0033) are what make the
    overlap harmless.
    """
    user = _make_user(db, "sub-running-due", created_at=_now() - timedelta(days=3))
    _add_grant(db, user)
    now = _now()
    # A PREVIOUS run that finished two days ago: this is what
    # ``last_finished_at`` still holds while the current run is in flight, and
    # it is why the account looks due to the very next scan.
    db.add(
        SyncStatus(
            user_id=user.id,
            status=store.SYNC_PENDING,
            last_finished_at=now - timedelta(days=2),
            last_success_at=now - timedelta(days=2),
            consecutive_failures=0,
            sync_requested=False,
        )
    )
    db.commit()

    assert store.claim_sync(db, user.id, now, stale_after=600) is True

    # The scheduler's view: the run is in flight, yet the account looks due
    # because the only finish stamp it can see belongs to the previous run.
    assert user.id in scheduler.select_due_users(
        db,
        now + timedelta(minutes=30),
        interval_seconds=3600,
        startup_stagger_seconds=0,
    )
    # Inside the window the claim still holds, so a scan is harmless.
    assert (
        store.claim_sync(db, user.id, now + timedelta(seconds=30), stale_after=600)
        is False
    )
    # Past the window the same scan would take the claim over.
    assert (
        store.claim_sync(
            db, user.id, now + timedelta(seconds=601), stale_after=600
        )
        is True
    )


def test_owning_run_writes_every_course(db, monkeypatch):
    """The fence must not disable the normal path: an owner writes as before."""
    user = _make_user(db, "sub-owner-writes")
    claimed_at = _now()
    _claim(user.id, claimed_at)
    monkeypatch.setattr(
        results,
        "_write_teacher_course",
        lambda db, user_id, course_id, payload: 0,
    )

    result = results.write_sync_results(
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
    assert row.status == store.SYNC_OK
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
    # Hosted still answers immediately: the worker does the fan-out (В§9).
    assert body["queued"] is True
    assert body["restarted"] is True

    row = db.get(SyncStatus, user.id)
    assert row is not None
    # Released and re-queued, so the worker's next scan picks it up.
    assert row.status == store.SYNC_PENDING
    assert row.sync_requested is True


def test_restart_is_refused_while_the_sync_is_healthy(hosted_client, db):
    """A progressing import must never be interrupted by an eager restart."""
    user = _sign_in(hosted_client, db, "sub-healthy")
    _claim(user.id, _now() - timedelta(seconds=30))

    response = hosted_client.post("/api/sync?restart=true")
    assert response.status_code == 409
    row = db.get(SyncStatus, user.id)
    assert row is not None
    assert row.status == store.SYNC_RUNNING
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

    assert db.get(SyncStatus, alice.id).status == store.SYNC_PENDING
    # Bob's stuck sync is his own business (В§12).
    assert db.get(SyncStatus, bob.id).status == store.SYNC_RUNNING


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
    """В§60: "people hit stuck syncs" and "the threshold is wrong" are different."""
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
    from auth import ownership

    owner = ownership.ensure_local_owner(db)
    db.commit()
    _claim(owner.id, _now() - timedelta(seconds=3600))

    # A signed-out desktop sync is the observable outcome of a claim that WAS
    # taken, i.e. the inline run really started instead of answering 409.
    assert client.post("/api/sync?restart=true").status_code == 200
    assert db.get(SyncStatus, owner.id).status == store.SYNC_PENDING


def test_desktop_restart_is_refused_while_the_sync_is_healthy(client, db):
    from auth import ownership

    owner = ownership.ensure_local_owner(db)
    db.commit()
    _claim(owner.id, _now() - timedelta(seconds=30))

    assert client.post("/api/sync?restart=true").status_code == 409
    assert db.get(SyncStatus, owner.id).status == store.SYNC_RUNNING


def test_desktop_restart_says_so_when_the_hung_thread_holds_the_lock(client, db):
    """The claim is released even when a second fan-out cannot start yet."""
    from auth import ownership

    owner = ownership.ensure_local_owner(db)
    db.commit()
    _claim(owner.id, _now() - timedelta(seconds=3600))
    lock = _fetch._sync_lock_for(owner.id)
    lock.acquire()
    try:
        response = client.post("/api/sync?restart=true")
    finally:
        lock.release()

    assert response.status_code == 409
    assert "shutting down" in response.json()["detail"]
    # The important half: the stale claim is gone, so the next attempt works.
    assert db.get(SyncStatus, owner.id).status == store.SYNC_PENDING


@pytest.mark.parametrize("age_seconds", [0, 60, 299])
def test_no_age_below_the_threshold_is_ever_abandoned(db, age_seconds):
    """Boundary guard: only a claim past the threshold may be released."""
    user = _make_user(db, f"sub-boundary-{age_seconds}")
    _claim(user.id, _now() - timedelta(seconds=age_seconds))

    released = store.abandon_claim(
        db, user.id, _now(), older_than=SYNC_STUCK_SECONDS
    )

    assert released is False
    assert db.get(SyncStatus, user.id).status == store.SYNC_RUNNING