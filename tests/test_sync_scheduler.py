# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Per-user synchronization: scheduler, worker and per-user state (stage 5).

The core invariants under test:

- §18: concurrency is per USER — a second call for the same account is
  rejected ("already running") while another account proceeds; one broken
  account never stops the others, and nothing user-visible carries raw
  exception text;
- §19: one sync per account across worker containers (DB claim), bounded
  batch per scan;
- §63: only active users with a stored grant are candidates; a broken
  grant pauses the account until the next sign-in; failures back off;
- §64: never-synced accounts enter the schedule spread over a stagger
  window instead of all at once.
"""

import threading
from datetime import datetime, timedelta, timezone

import google_credentials
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import auth
import sync_scheduler
import sync_service
import sync_store
import sync_worker
from database import SessionLocal
from models import SyncStatus
from models_auth import OAuthToken, User


def _now() -> datetime:
    """Naive UTC — the timestamp convention of the user-scoped tables."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(
    db: Session, subject: str, *, created_at=None, is_active: bool = True
) -> User:
    user = User(
        provider="google",
        provider_subject=subject,
        email=f"{subject}@example.com",
        display_name=subject,
        created_at=created_at or _now(),
        updated_at=_now(),
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def _add_grant(db: Session, user: User) -> None:
    """A stored (not necessarily valid) Google grant for the user."""
    db.add(
        OAuthToken(
            user_id=user.id,
            access_token="enc.v1:test",
            token_uri="https://oauth2.googleapis.com/token",
            scopes=auth.SCOPES,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.commit()


def _select(db: Session, now=None, *, interval=600, limit=None):
    return sync_scheduler.select_due_users(
        db,
        now or _now(),
        interval_seconds=interval,
        startup_stagger_seconds=300,
        limit=limit,
    )


# --------------------------------------------- §18 per-user concurrency


def test_same_user_is_rejected_while_another_user_proceeds(db: Session):
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    lock = sync_service._sync_lock_for(alice.id)
    lock.acquire()
    try:
        alice_result = sync_service.sync_now(user=alice)
        bob_result = sync_service.sync_now(user=bob)
    finally:
        lock.release()
    # The same account: refused, not queued.
    assert alice_result == {"ok": False, "error": sync_service.ALREADY_RUNNING}
    # Another account: a normal (here: signed-out) result, never the
    # process-global "already running" of the pre-migration lock.
    assert bob_result["error"] == sync_service.NOT_SIGNED_IN


def test_lock_registry_is_keyed_by_user():
    assert sync_service._sync_lock_for(1) is sync_service._sync_lock_for(1)
    assert sync_service._sync_lock_for(1) is not sync_service._sync_lock_for(2)


def test_desktop_background_sync_persists_the_local_owner(db: Session):
    """The user=None (desktop) path must survive its own session close.

    The synthetic owner is created by the first background run; if that
    creation were left uncommitted, every run would reload nothing and
    report "Not signed in to Google" forever.
    """
    import ownership

    assert sync_service.sync_now() == {
        "ok": False,
        "error": sync_service.NOT_SIGNED_IN,
    }
    with SessionLocal() as check:
        owner = check.scalars(
            select(User).where(
                User.provider == ownership.LOCAL_PROVIDER,
                User.provider_subject == ownership.LOCAL_SUBJECT,
            )
        ).one_or_none()
        assert owner is not None
    # A second run reuses the SAME owner (idempotent, not a new row).
    sync_service.sync_now()
    with SessionLocal() as check:
        owners = check.scalars(
            select(User).where(User.provider == ownership.LOCAL_PROVIDER)
        ).all()
        assert len(owners) == 1


# --------------------------------------------- §18 failure isolation + §18 errors


def test_run_user_never_propagates_a_crash(monkeypatch):
    def boom(user_id):
        raise RuntimeError("SECRET google payload")

    monkeypatch.setattr(sync_service, "sync_user_id", boom)
    result = sync_scheduler.run_user(42)
    assert result["ok"] is False
    assert "SECRET" not in str(result)


def test_public_error_never_carries_exception_text():
    class _Response:
        status = 403

    class _HttpError(Exception):
        resp = _Response()

    assert (
        sync_service._public_error(_HttpError())
        == "Google denied access to Classroom data; please sign in again."
    )
    assert (
        sync_service._public_error(ValueError("refresh_token=abc"))
        == "Sync failed; see the server log for details."
    )


def test_failed_sync_records_a_sanitized_error(db: Session, monkeypatch):
    """§18: the frontend sees a short sentence, the log keeps the trace."""
    user = _make_user(db, "sub-broken", created_at=_now())
    _add_grant(db, user)
    monkeypatch.setattr(
        google_credentials, "get_google_credentials", lambda db, user: object()
    )
    monkeypatch.setattr(sync_service, "build_service", lambda creds: object())
    monkeypatch.setattr(sync_service, "ClassroomClient", lambda service: object())

    def raise_secret(_client):
        raise RuntimeError("SECRET classroom response body")

    monkeypatch.setattr(sync_service, "_resolve_courses", raise_secret)

    result = sync_service.sync_user_id(user.id)
    assert result["ok"] is False
    assert result["error"] == "Sync failed; see the server log for details."
    row = db.get(SyncStatus, user.id)
    assert row is not None
    assert row.last_error == result["error"]
    assert "SECRET" not in row.last_error
    assert row.consecutive_failures == 1
    assert row.last_finished_at is not None


# --------------------------------------------- §19 cross-process claim


def test_claim_is_atomic_and_expires(db: Session):
    user = _make_user(db, "sub-claim")
    _add_grant(db, user)
    now = _now()
    assert sync_store.claim_sync(db, user.id, now, stale_after=3600) is True
    row = db.get(SyncStatus, user.id)
    assert row is not None and row.status == sync_store.SYNC_RUNNING
    # Another worker container scanning seconds later is refused.
    assert (
        sync_store.claim_sync(db, user.id, now + timedelta(seconds=5), stale_after=3600)
        is False
    )
    # A crashed worker's claim is taken over after the stale window.
    assert (
        sync_store.claim_sync(
            db, user.id, now + timedelta(seconds=3601), stale_after=3600
        )
        is True
    )


# --------------------------------------------- §63 candidate selection


def test_selection_skips_unusable_accounts(db: Session):
    past = _now() - timedelta(days=1)
    fresh = _now()

    due = _make_user(db, "sub-due", created_at=past)
    _add_grant(db, due)

    fresh_user = _make_user(db, "sub-fresh", created_at=past)
    _add_grant(db, fresh_user)
    sync_store.mark_sync_succeeded(db, fresh_user.id, fresh)

    inactive = _make_user(db, "sub-inactive", created_at=past, is_active=False)
    _add_grant(db, inactive)

    paused = _make_user(db, "sub-paused", created_at=past)
    _add_grant(db, paused)
    sync_store.mark_sync_needs_reauth(db, paused.id, "needs reauth", fresh)

    _make_user(db, "sub-no-grant", created_at=past)  # never signed in to Google

    assert _select(db) == [due.id]


def test_sync_request_makes_a_user_due_and_lifts_the_pause(db: Session):
    user = _make_user(db, "sub-requested", created_at=_now() - timedelta(days=1))
    _add_grant(db, user)
    sync_store.mark_sync_succeeded(db, user.id, _now())
    # Freshly synced: not due.
    assert _select(db) == []
    # An explicit request (e.g. right after sign-in) is due immediately.
    sync_store.request_sync(db, user.id)
    assert _select(db) == [user.id]

    # A paused account is skipped — until the next sign-in requests a sync.
    sync_store.mark_sync_needs_reauth(db, user.id, "needs reauth", _now())
    assert _select(db) == []
    sync_store.request_sync(db, user.id)
    row = db.get(SyncStatus, user.id)
    assert row is not None
    assert row.status == sync_store.SYNC_PENDING
    assert row.sync_requested is True
    assert _select(db) == [user.id]


def test_selection_orders_by_due_time_and_respects_the_limit(db: Session):
    old = _now() - timedelta(days=3)
    newer = _now() - timedelta(days=1)
    first = _make_user(db, "sub-first", created_at=old)
    _add_grant(db, first)
    second = _make_user(db, "sub-second", created_at=newer)
    _add_grant(db, second)
    third = _make_user(db, "sub-third", created_at=old)
    _add_grant(db, third)

    # Zero interval/stagger → due time equals account creation, so the
    # order is fully deterministic: oldest due first, ties broken by id.
    selected = _select(db, interval=0, limit=2)
    assert selected == [first.id, third.id]
    assert second.id not in selected
    assert _select(db, interval=0, limit=None) == [first.id, third.id, second.id]


# --------------------------------------------- §63 backoff / §64 stagger


def test_retry_backoff_is_exponential_and_capped():
    assert sync_scheduler.retry_delay_seconds(600, 0) == 600
    assert sync_scheduler.retry_delay_seconds(600, 1) == 1200
    assert sync_scheduler.retry_delay_seconds(600, 2) == 2400
    assert sync_scheduler.retry_delay_seconds(600, 3) == 4800
    # A permanently failing account never goes past the cap.
    assert sync_scheduler.retry_delay_seconds(600, 9) == 4800


def test_next_sync_at_applies_backoff_and_stagger(db: Session):
    user = _make_user(db, "sub-backoff")
    finished_at = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    row = SyncStatus(
        user_id=user.id,
        status=sync_store.SYNC_ERROR,
        last_finished_at=finished_at,
        consecutive_failures=1,
    )
    due = sync_scheduler.next_sync_at(
        user, row, interval_seconds=600, startup_stagger_seconds=300
    )
    expected = finished_at + timedelta(
        seconds=1200 + sync_scheduler.stagger_offset_seconds(user.id, 600)
    )
    assert due == expected


def test_stagger_offsets_are_deterministic_and_spread():
    assert sync_scheduler.stagger_offset_seconds(7, 600) == (
        sync_scheduler.stagger_offset_seconds(7, 600)
    )
    assert 0 <= sync_scheduler.stagger_offset_seconds(7, 600) < 600
    assert sync_scheduler.stagger_offset_seconds(7, 0) == 0
    # 40 accounts do not land on the same instant (§64 thundering herd).
    offsets = {
        sync_scheduler.stagger_offset_seconds(user_id, 600) for user_id in range(1, 41)
    }
    assert len(offsets) >= 10


# --------------------------------------------- §19 bounded batch / queue


def test_scheduler_submits_at_most_the_free_slots(db: Session, monkeypatch):
    users = [
        _make_user(db, f"sub-{i}", created_at=_now() - timedelta(days=1))
        for i in range(4)
    ]
    for user in users:
        _add_grant(db, user)

    done: list[int] = []

    def fake_run(user_id: int) -> dict:
        # Simulate what a real job does: mark the run finished, so the
        # account leaves the queue instead of being picked again.
        with SessionLocal() as session:
            sync_store.mark_sync_succeeded(session, user_id, _now() + timedelta(days=1))
        done.append(user_id)
        return {"user_id": user_id, "ok": True}

    monkeypatch.setattr(sync_scheduler, "run_user", fake_run)
    scheduler = sync_scheduler.SyncScheduler(
        max_concurrent=2, interval_seconds=600, scan_interval_seconds=60
    )
    try:
        first = scheduler.scan_once(now=_now())
        assert len(first) == 2
        scheduler.wait(timeout=5)
        second = scheduler.scan_once(now=_now())
        # The queue drains account by account instead of fan-out to all.
        assert len(second) == 2
        assert set(first).isdisjoint(second)
        assert sorted(first + second) == sorted(user.id for user in users)
    finally:
        scheduler.stop()


def test_scheduler_does_not_resubmit_a_running_job(db: Session, monkeypatch):
    user = _make_user(db, "sub-running", created_at=_now() - timedelta(days=1))
    _add_grant(db, user)
    started = threading.Event()
    release = threading.Event()

    def fake_run(user_id: int) -> dict:
        started.set()
        release.wait(timeout=5)
        return {"user_id": user_id, "ok": True}

    monkeypatch.setattr(sync_scheduler, "run_user", fake_run)
    scheduler = sync_scheduler.SyncScheduler(
        max_concurrent=1, interval_seconds=600, scan_interval_seconds=60
    )
    try:
        assert scheduler.scan_once(now=_now()) == [user.id]
        assert started.wait(timeout=5)
        # The job is still in flight: a concurrent scan must not re-queue it.
        assert scheduler.scan_once(now=_now()) == []
        release.set()
        scheduler.wait(timeout=5)
    finally:
        scheduler.stop()


def test_sync_users_is_bounded_and_ordered(monkeypatch):
    active: set[int] = set()
    guard = threading.Lock()

    def fake_run(user_id: int) -> dict:
        with guard:
            active.add(user_id)
            assert len(active) <= 2
        with guard:
            active.discard(user_id)
        return {"user_id": user_id, "ok": True}

    monkeypatch.setattr(sync_scheduler, "run_user", fake_run)
    results = sync_scheduler.sync_users([11, 12, 13, 14], max_concurrent=2)
    assert [result["user_id"] for result in results] == [11, 12, 13, 14]


# --------------------------------------------- worker wiring


def test_worker_once_runs_one_bounded_scan(monkeypatch):
    monkeypatch.setattr(sync_worker, "select_due_users", lambda *a, **k: [5])
    monkeypatch.setattr(
        sync_worker,
        "sync_users",
        lambda ids, **k: [{"user_id": i, "ok": True} for i in ids],
    )
    monkeypatch.setattr(sync_worker, "init_db", lambda: None)
    assert sync_worker.main(["--once"]) == 0


def test_worker_once_without_due_users_is_a_clean_noop(monkeypatch):
    monkeypatch.setattr(sync_worker, "select_due_users", lambda *a, **k: [])
    monkeypatch.setattr(sync_worker, "init_db", lambda: None)
    assert sync_worker.main(["--once"]) == 0


@pytest.mark.parametrize("stale_after", [0])
def test_zero_stale_window_never_steals_a_running_claim(db: Session, stale_after):
    user = _make_user(db, "sub-stale")
    now = _now()
    assert sync_store.claim_sync(db, user.id, now, stale_after=stale_after) is True
    assert sync_store.claim_sync(db, user.id, now, stale_after=stale_after) is False
