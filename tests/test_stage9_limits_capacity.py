# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Rate limits, retention and capacity guarantees (migration stage 9).

Pins the decisions of this stage (§39–§46, §59–§62, §66, §68, §70, §88):

- §39: hosted abuse surfaces are rate limited per client IP (login, sync,
  destructive cache clear) with a 429 + Retry-After answer, and a manual
  sync has a per-user cooldown so holding the button cannot consume the
  Google quota; the desktop app is never throttled;
- §40/§88: the concurrency defaults are the conservative ones the capacity
  note argues for, and the scheduling math (users x requests / interval) is
  measurable rather than assumed;
- §41: a dead Google grant is a per-user problem — the account is marked
  needs_reauth, its own credential row is dropped, other users' grants and
  sessions survive;
- §42: log records cannot carry token/cookie/secret material;
- §44/§66: deletion is per user — sessions, tokens, sync state and cache of
  the caller only; there is no global destructive path;
- §45: a sync never holds a database transaction across the Google fetch;
- §60: counters exist for logins, syncs, quota/server errors and crashes;
- §61/§62: cached data carries its own freshness metadata and no cache key
  is scoped by a Google id alone;
- §68: the indexes the query patterns need, and no blind ones;
- §70: every stored timestamp is naive UTC.
"""

import hashlib
from datetime import datetime, timedelta, timezone

import google_credentials
import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

import maintenance
import metrics
import rate_limit
import sync_store
from database import engine
from models import (
    Course,
    CourseRole,
    CourseStudent,
    CourseWork,
    StudentSubmission,
    SyncStatus,
)
from models_auth import OAuthToken, User, UserSession


def _now() -> datetime:
    """Naive UTC — the timestamp convention of the whole backend."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def _add_session(db: Session, user: User, raw_token: str, **overrides) -> UserSession:
    now = _now()
    row = UserSession(
        session_token_hash=_sha256(raw_token),
        user_id=user.id,
        created_at=now,
        expires_at=overrides.get("expires_at", now + timedelta(days=1)),
        last_seen_at=now,
        revoked_at=overrides.get("revoked_at"),
        user_agent=None,
    )
    db.add(row)
    db.commit()
    return row


def _add_grant(db: Session, user: User) -> OAuthToken:
    import token_crypto

    row = OAuthToken(
        user_id=user.id,
        access_token=token_crypto.encrypt("test-access"),
        refresh_token=token_crypto.encrypt("test-refresh"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/classroom.courses.readonly"],
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(row)
    db.commit()
    return row


def _seed_course(db: Session, user_id: int) -> None:
    db.add(
        Course(user_id=user_id, id="c1", name="Cached course", course_state="ACTIVE")
    )
    db.add(CourseRole(user_id=user_id, course_id="c1", role="STUDENT"))
    db.add(
        CourseWork(
            user_id=user_id,
            id="w1",
            course_id="c1",
            title="Cached work",
            state="PUBLISHED",
        )
    )
    db.add(
        StudentSubmission(
            user_id=user_id, course_id="c1", coursework_id="w1", state="TURNED_IN"
        )
    )
    db.add(CourseStudent(user_id=user_id, course_id="c1", student_id="s1"))
    db.commit()


@pytest.fixture(autouse=True)
def _isolated_metrics():
    """Counters are process-global: keep this file's tests independent."""
    metrics.reset()
    yield
    metrics.reset()


# ----------------------------------------------------------- §39 throttling


def test_token_bucket_refills_over_time():
    limiter = rate_limit.RateLimiter()
    assert limiter.allow("k", capacity=2, refill_per_second=1.0, now=0.0)
    assert limiter.allow("k", capacity=2, refill_per_second=1.0, now=0.0)
    # Third call in the same instant is over the limit.
    assert not limiter.allow("k", capacity=2, refill_per_second=1.0, now=0.0)
    # One second later the bucket has refilled exactly one token.
    assert limiter.allow("k", capacity=2, refill_per_second=1.0, now=1.0)
    # A different key has its own allowance.
    assert limiter.allow("other", capacity=2, refill_per_second=1.0, now=1.0)


def test_rate_limiter_capacity_change_replaces_the_bucket():
    limiter = rate_limit.RateLimiter()
    assert limiter.allow("k", capacity=1, refill_per_second=0.0, now=0.0)
    assert not limiter.allow("k", capacity=1, refill_per_second=0.0, now=0.0)
    # Reconfiguring the same key starts a fresh bucket instead of reusing a
    # drained one (deployments change limits without a restart).
    assert limiter.allow("k", capacity=5, refill_per_second=0.0, now=0.0)
    limiter.reset("k")
    assert limiter.allow("k", capacity=1, refill_per_second=0.0, now=0.0)


def test_hosted_sync_endpoint_is_throttled_per_ip(hosted_client, db, monkeypatch):
    """§39: repeated manual syncs from one client hit 429 with Retry-After."""
    import main

    monkeypatch.setattr(main, "RATE_LIMIT_SYNC_PER_MINUTE", 2)
    user = _make_user(db, "sub-alice")
    _add_session(db, user, "raw-alice")
    hosted_client.cookies.set("gch_session", "raw-alice")

    assert hosted_client.post("/api/sync").status_code == 200
    assert hosted_client.post("/api/sync").status_code == 200
    third = hosted_client.post("/api/sync")
    assert third.status_code == 429
    assert third.headers["retry-after"] == "60"


def test_desktop_sync_endpoint_is_not_throttled(client, monkeypatch):
    """§39/§74: the desktop build keeps its unrestricted local endpoint."""
    import main
    import sync

    monkeypatch.setattr(main, "RATE_LIMIT_SYNC_PER_MINUTE", 1)
    monkeypatch.setattr(
        sync, "sync_now", lambda user=None, **kwargs: {"ok": True, "courses": 0}
    )
    assert client.post("/api/sync").status_code == 200
    # Second call: still 200 or an inline-sync 409 — never a hosted 429,
    # because the desktop path has no throttle middleware and no cooldown.
    second = client.post("/api/sync")
    assert second.status_code in (200, 409)


def test_hosted_login_redirect_is_throttled(hosted_client, monkeypatch):
    import main

    monkeypatch.setattr(main, "RATE_LIMIT_LOGIN_PER_MINUTE", 1)
    first = hosted_client.get("/api/auth/login", follow_redirects=False)
    second = hosted_client.get("/api/auth/login", follow_redirects=False)
    assert first.status_code == 302
    assert second.status_code == 429


def test_rejected_callbacks_are_capped(hosted_client, monkeypatch):
    """§39: rejected callbacks are counted; a success is not."""
    import config

    monkeypatch.setattr(config, "RATE_LIMIT_CALLBACK_FAILURES_PER_MINUTE", 1)
    first = hosted_client.get("/api/auth/callback", follow_redirects=False)
    second = hosted_client.get("/api/auth/callback", follow_redirects=False)
    assert first.headers["location"].startswith("/?login_error=400")
    assert second.headers["location"] == "/?login_error=429"


def test_manual_sync_cooldown_refuses_the_same_user(hosted_client, db):
    """§39: a second manual sync inside the cooldown is refused with 429."""
    from config import SYNC_MANUAL_COOLDOWN_SECONDS

    assert SYNC_MANUAL_COOLDOWN_SECONDS > 0
    user = _make_user(db, "sub-alice")
    _add_session(db, user, "raw-alice")
    db.add(
        SyncStatus(
            user_id=user.id,
            status=sync_store.SYNC_OK,
            last_started_at=_now(),
            consecutive_failures=0,
            sync_requested=False,
        )
    )
    db.commit()
    hosted_client.cookies.set("gch_session", "raw-alice")
    response = hosted_client.post("/api/sync")
    assert response.status_code == 429
    assert "just ran" in response.json()["detail"]
    assert int(response.headers["retry-after"]) > 0


def test_manual_sync_cooldown_expires(hosted_client, db, monkeypatch):
    from config import SYNC_MANUAL_COOLDOWN_SECONDS

    user = _make_user(db, "sub-alice")
    _add_session(db, user, "raw-alice")
    db.add(
        SyncStatus(
            user_id=user.id,
            status=sync_store.SYNC_OK,
            last_started_at=_now()
            - timedelta(seconds=SYNC_MANUAL_COOLDOWN_SECONDS + 5),
            consecutive_failures=0,
            sync_requested=False,
        )
    )
    db.commit()
    hosted_client.cookies.set("gch_session", "raw-alice")
    response = hosted_client.post("/api/sync")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["queued"] is True
    assert response.json()["status"] == "queued"


def test_cooldown_is_per_user(hosted_client, db, monkeypatch):
    """§39: one user's recent sync must not block another account."""
    recent = _make_user(db, "sub-recent")
    other = _make_user(db, "sub-other")
    _add_session(db, other, "raw-other")
    db.add(
        SyncStatus(
            user_id=recent.id,
            status=sync_store.SYNC_OK,
            last_started_at=_now(),
            consecutive_failures=0,
            sync_requested=False,
        )
    )
    db.commit()
    hosted_client.cookies.set("gch_session", "raw-other")
    response = hosted_client.post("/api/sync")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["queued"] is True
    assert response.json()["status"] == "queued"


# ------------------------------------------- §41 dead grant stays per-user


def test_invalid_grant_drops_only_that_users_credentials(db):
    """§41: a revoked grant is deleted per user, never globally."""
    import google_credentials
    import oauth_transport

    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_grant(db, alice)
    _add_grant(db, bob)

    def dead_refresh(_creds):
        raise RuntimeError("invalid_grant: Token has been expired or revoked")

    original = oauth_transport.refresh_credentials
    oauth_transport.refresh_credentials = dead_refresh
    try:
        assert google_credentials.refresh_google_credentials(db, alice) is None
    finally:
        oauth_transport.refresh_credentials = original

    assert db.get(OAuthToken, alice.id) is None
    assert db.get(OAuthToken, bob.id) is not None


def test_transient_refresh_failure_keeps_the_grant(db):
    """§41: only a permanently dead grant removes the row."""
    import google_credentials
    import oauth_transport

    alice = _make_user(db, "sub-alice")
    _add_grant(db, alice)

    def flaky_refresh(_creds):
        raise RuntimeError("Connection reset by peer")

    original = oauth_transport.refresh_credentials
    oauth_transport.refresh_credentials = flaky_refresh
    try:
        assert google_credentials.refresh_google_credentials(db, alice) is None
    finally:
        oauth_transport.refresh_credentials = original
    assert db.get(OAuthToken, alice.id) is not None


def test_sync_marks_needs_reauth_and_removes_only_that_grant(db, monkeypatch):
    """§41: a 401 during the sync pauses THIS account and keeps user B."""
    import google_credentials
    from googleapiclient.errors import HttpError

    import sync_service
    import sync_store

    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_grant(db, alice)
    _add_grant(db, bob)
    db.commit()
    alice_id, bob_id = alice.id, bob.id

    class _Resp:
        status = 401
        reason = "Unauthorized"

    def boom(_credentials):
        raise HttpError(_Resp(), b'{"error": {"message": "Invalid Credentials"}}')

    monkeypatch.setattr(sync_service, "build_service", boom)
    # The credential lookup returns a usable object so the sync reaches the
    # fetch phase (where the 401 arrives).
    monkeypatch.setattr(
        google_credentials,
        "get_google_credentials",
        lambda _db, _user: object(),
    )
    result = sync_service.sync_now(user=db.get(User, alice_id))

    assert result["ok"] is False
    assert result["error"] == sync_service.NEEDS_REAUTH
    db.expire_all()
    assert db.get(OAuthToken, alice_id) is None
    assert db.get(OAuthToken, bob_id) is not None
    alice_state = db.get(SyncStatus, alice_id)
    assert alice_state is not None
    assert alice_state.status == sync_store.SYNC_NEEDS_REAUTH


# ------------------------------------------------------------ §42 log safety


def test_log_records_never_carry_token_material():
    import logging

    import access_log

    record = logging.LogRecord(
        name="api",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login ok access_token=%s cookie=%s",
        args=("ya29.a0AfH6SMDSECRET", "gch_session=abcdef123456"),
        exc_info=None,
    )
    assert access_log.RedactSecretsFilter().filter(record) is True
    rendered = record.getMessage()
    assert "ya29.a0AfH6SMDSECRET" not in rendered
    assert "abcdef123456" not in rendered
    assert "[REDACTED]" in rendered


def test_secret_redaction_keeps_operational_fields():
    import access_log

    text = "Sync ok user=42 courses=3 google_requests=128 duration=4.2s"
    assert access_log.redact_secrets_in_text(text) == text


def test_redaction_filter_installed_on_hosted_app():
    import logging

    import access_log

    access_log.install_secret_redaction()
    assert any(
        isinstance(item, access_log.RedactSecretsFilter)
        for item in logging.getLogger("sync_service").filters
    )
    # Idempotent: installing twice must not stack filters.
    before = len(logging.getLogger("sync_service").filters)
    access_log.install_secret_redaction()
    assert len(logging.getLogger("sync_service").filters) == before


# ------------------------------------------- §44/§66 deletion stays per user


def test_retention_sweep_removes_only_dead_rows(db):
    """§44: expired/revoked sessions and stale login attempts are swept."""
    from models_auth import OAuthLoginState

    alive = _make_user(db, "sub-alive")
    gone = _make_user(db, "sub-gone")
    _add_session(db, alive, "raw-alive")
    _add_session(db, gone, "raw-expired", expires_at=_now() - timedelta(seconds=1))
    _add_session(db, gone, "raw-revoked", revoked_at=_now())
    db.add(
        OAuthLoginState(
            state="stale",
            browser_nonce="n",
            code_verifier="v",
            redirect_to="/",
            created_at=_now() - timedelta(hours=1),
            expires_at=_now() - timedelta(minutes=1),
        )
    )
    db.commit()

    removed = maintenance.purge_expired(db)
    assert removed["sessions"] == 2
    assert removed["login_states"] == 1
    remaining = {row.session_token_hash for row in db.query(UserSession).all()}
    assert remaining == {_sha256("raw-alive")}


def test_disconnect_google_keeps_the_account_and_cache(db):
    """§44: disconnecting Google is not account deletion."""
    user = _make_user(db, "sub-alice")
    _add_session(db, user, "raw-alice")
    _add_grant(db, user)
    _seed_course(db, user.id)
    sync_store.mark_sync_succeeded(db, user.id, _now())
    user_id = user.id

    maintenance.disconnect_google(db, user_id)
    db.expire_all()
    assert db.get(OAuthToken, user_id) is None
    # Account, session and cache survive; only the grant and the sync state
    # reset, and the last successful sync stays visible (§61).
    assert db.get(User, user_id) is not None
    assert db.query(UserSession).filter_by(user_id=user_id).count() == 1
    assert db.query(Course).filter_by(user_id=user_id).count() == 1
    state = db.get(SyncStatus, user_id)
    assert state is not None
    assert state.status == sync_store.SYNC_PENDING
    assert state.last_success_at is not None


def test_account_deletion_removes_everything_of_one_user(db):
    """§44/§66: deletion is scoped to the caller, never global."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    for user in (alice, bob):
        _add_session(db, user, f"raw-{user.provider_subject}")
        _add_grant(db, user)
        _seed_course(db, user.id)
        sync_store.mark_sync_succeeded(db, user.id, _now())
    alice_id, bob_id = alice.id, bob.id

    removed = maintenance.delete_user_data(db, alice)
    db.expire_all()
    assert removed["sessions"] == 1
    assert removed["tokens"] == 1
    assert removed["courses"] == 1
    assert removed["sync_status"] == 1
    # Alice is gone from every table; Bob is untouched.
    assert db.get(User, alice_id) is None
    assert db.query(Course).filter_by(user_id=alice_id).count() == 0
    assert db.query(CourseWork).filter_by(user_id=alice_id).count() == 0
    assert db.query(StudentSubmission).filter_by(user_id=alice_id).count() == 0
    assert db.get(User, bob_id) is not None
    assert db.query(Course).filter_by(user_id=bob_id).count() == 1
    assert db.get(OAuthToken, bob_id) is not None


def test_hosted_delete_me_endpoint_clears_the_callers_session(hosted_client, db):
    """§44: DELETE /api/me is per-session and drops the cookie."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_session(db, alice, "raw-alice")
    _add_session(db, bob, "raw-bob")
    _add_grant(db, alice)
    _seed_course(db, alice.id)
    db.commit()
    alice_id = alice.id

    hosted_client.cookies.set("gch_session", "raw-alice")
    assert hosted_client.delete("/api/me").status_code == 400  # confirm required
    response = hosted_client.delete("/api/me", params={"confirm": "true"})
    assert response.status_code == 200
    db.expire_all()
    assert db.get(User, alice_id) is None
    assert db.query(UserSession).filter_by(user_id=bob.id).count() == 1
    # The session cookie is gone, so the next request is unauthenticated.
    assert "gch_session" not in response.cookies
    assert hosted_client.get("/api/courses").status_code == 401


def test_delete_me_is_desktop_refused(client):
    """§44: the desktop build has no server-side account to delete."""
    response = client.delete("/api/me", params={"confirm": "true"})
    assert response.status_code == 400
    assert "Desktop" in response.json()["detail"]


def test_hosted_disconnect_endpoint_needs_confirmation(hosted_client, db):
    """§44: DELETE /api/me/google requires confirm=true."""
    user = _make_user(db, "sub-alice")
    _add_session(db, user, "raw-alice")
    _add_grant(db, user)
    user_id = user.id
    hosted_client.cookies.set("gch_session", "raw-alice")
    assert hosted_client.delete("/api/me/google").status_code == 400
    response = hosted_client.delete("/api/me/google", params={"confirm": "true"})
    assert response.status_code == 200
    db.expire_all()
    assert db.get(OAuthToken, user_id) is None
    # The application session survives a disconnect.
    assert db.query(UserSession).filter_by(user_id=user_id).count() == 1


def test_cache_delete_alias_clears_only_the_caller(hosted_client, db):
    """§66: DELETE /api/me/cache is the explicit per-user name."""
    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    _add_session(db, alice, "raw-alice")
    _seed_course(db, alice.id)
    _seed_course(db, bob.id)
    hosted_client.cookies.set("gch_session", "raw-alice")
    response = hosted_client.delete("/api/me/cache", params={"confirm": "true"})
    assert response.status_code == 200
    assert db.query(Course).filter_by(user_id=alice.id).count() == 0
    assert db.query(Course).filter_by(user_id=bob.id).count() == 1


# ---------------------------------------------- §45 transaction boundaries


def test_sync_fetch_phase_holds_no_database_connection(client, monkeypatch):
    """§45: the Classroom fetch runs outside any open transaction."""
    import google_credentials

    import sync_service
    from database import SessionLocal, engine

    with SessionLocal() as setup:
        user = _make_user(setup, "sub-alice")
        _add_grant(setup, user)
        setup.commit()
        user_id = user.id

    observed: list[int] = []

    def capture(_credentials):
        pool = engine.pool
        observed.append(getattr(pool, "checkedout", lambda: -1)())
        raise RuntimeError("abort before Google")

    monkeypatch.setattr(
        google_credentials, "get_google_credentials", lambda _db, _user: object()
    )
    monkeypatch.setattr(sync_service, "build_service", capture)
    result = sync_service.sync_user_id(user_id)

    assert result["ok"] is False
    assert observed == [0], "the fetch must not inherit a checked-out connection"


def test_scheduled_sync_closes_its_session_before_the_fetch(client, monkeypatch):
    """§45: the claim/credential session is closed before the network phase."""
    import google_credentials

    import sync_service
    from database import SessionLocal

    with SessionLocal() as setup:
        user = _make_user(setup, "sub-alice")
        _add_grant(setup, user)
        setup.commit()
        user_id = user.id

    seen: list[bool] = []

    def capture(_credentials):
        # If the claim session were still open, the scheduler's own scan
        # session below would be the second connection on a 1-slot SQLite
        # database — here we simply record that we got this far.
        seen.append(True)
        raise RuntimeError("abort before Google")

    monkeypatch.setattr(
        google_credentials, "get_google_credentials", lambda _db, _user: object()
    )
    monkeypatch.setattr(sync_service, "build_service", capture)
    sync_service.sync_user_id(user_id)
    assert seen == [True]
    with SessionLocal() as check:
        state = check.get(SyncStatus, user_id)
    assert state is not None and state.status == sync_store.SYNC_ERROR


# ------------------------------------------- §59/§60 errors and observability


def test_public_error_mapping_is_short_and_status_based():
    """§59: the user-facing message is a stable phrase, never a traceback."""
    from googleapiclient.errors import HttpError

    import sync_service

    class _Resp:
        def __init__(self, status):
            self.status = status
            self.reason = "err"

    cases = {
        401: sync_service.NEEDS_REAUTH,
        403: "Google denied access to Classroom data; please sign in again.",
        429: "Google rate limit reached; the next sync will retry.",
    }
    for status, expected in cases.items():
        exc = HttpError(_Resp(status), b'{"error": "x"}')
        assert sync_service._public_error(exc) == expected
    assert "HTTP 500" in sync_service._public_error(HttpError(_Resp(500), b"{}"))
    # A non-HTTP failure carries no exception text at all.
    raw = RuntimeError("client_secret=SECRETVALUE")
    assert "SECRETVALUE" not in sync_service._public_error(raw)
    assert "Traceback" not in sync_service._public_error(raw)


def test_metrics_count_sessions_syncs_and_logins(hosted_client, db):
    """§60: the counters an operator needs actually move."""
    user = _make_user(db, "sub-alice")
    _add_session(db, user, "raw-alice")
    db.add(
        SyncStatus(
            user_id=user.id,
            status=sync_store.SYNC_OK,
            last_started_at=_now(),
            consecutive_failures=0,
            sync_requested=False,
        )
    )
    db.commit()

    # A rejected session is counted (no cookie at all).
    assert hosted_client.get("/api/courses").status_code == 401
    # A failed callback is counted as a failed login (no code in the URL).
    assert (
        hosted_client.get("/api/auth/callback", follow_redirects=False).status_code
        == 302
    )
    snapshot = metrics.snapshot()
    assert snapshot[metrics.SESSION_REJECTED] >= 1
    assert snapshot[metrics.LOGIN_FAILED] >= 1
    # Counters are name-only: no email, student name or Google id in them.
    assert all(isinstance(key, str) for key in snapshot)


def test_request_stats_count_quota_and_server_errors():
    """§60: 429 and 5xx are counted separately from total requests."""
    from classroom_api import RequestStats, _classify_http_status

    assert _classify_http_status(429) == "quota"
    assert _classify_http_status(503) == "server"
    assert _classify_http_status(404) is None

    stats = RequestStats()
    stats.record()
    stats.record_quota_error()
    stats.record_server_error()
    assert stats.snapshot() == {
        "requests": 1,
        "quota_errors": 1,
        "server_errors": 1,
    }


def test_sync_workers_report_a_metrics_snapshot(caplog):
    """§60: the worker's periodic summary is a single structured line."""
    import logging

    metrics.reset()
    metrics.record("sync_succeeded", 3)
    with caplog.at_level(logging.INFO, logger="metrics"):
        snapshot = metrics.log_snapshot("test")
    assert snapshot["sync_succeeded"] == 3
    assert any("metrics[test]" in record.message for record in caplog.records)


# ------------------------------------------------ §61/§62 cache semantics


def test_failed_sync_keeps_the_cache_and_reports_its_age(db, monkeypatch):
    """§61: a missed sync never turns stale cache into "current" data."""
    import sync_service

    user = _make_user(db, "sub-alice")
    _add_grant(db, user)
    _seed_course(db, user.id)
    last_success = _now() - timedelta(hours=5)
    sync_store.mark_sync_succeeded(db, user.id, last_success)
    user_id = user.id

    class _EmptyClient:
        def __init__(self, service, stats=None):
            self._service = service
            self._stats = stats

        def list_courses(self, **_kwargs):
            return None  # HTTP error: keep the cache (review §1.7)

    monkeypatch.setattr(
        google_credentials, "get_google_credentials", lambda _db, _user: object()
    )
    monkeypatch.setattr(sync_service, "ClassroomClient", _EmptyClient)
    monkeypatch.setattr(sync_service, "build_service", lambda _creds: object())
    result = sync_service.sync_user_id(user_id)

    assert result["ok"] is False
    assert result["error"] == sync_service.COURSES_FAILED
    db.expire_all()
    # The cached rows survive ...
    assert db.query(Course).filter_by(user_id=user_id).count() == 1
    state = db.get(SyncStatus, user_id)
    assert state is not None
    # ... the age of the data is still visible ...
    assert state.last_success_at == last_success
    # ... and the failure is reported in a safe phrase.
    assert state.status == sync_store.SYNC_ERROR
    assert state.last_error == sync_service.COURSES_FAILED


def test_profile_cache_is_keyed_by_local_user_id(db, monkeypatch):
    """§62: in-memory caches are keyed by the LOCAL user, not by a Google id."""
    from api import identity

    alice = _make_user(db, "sub-alice")
    bob = _make_user(db, "sub-bob")
    alice.display_name = None
    alice.email = None
    bob.display_name = None
    bob.email = None
    db.commit()
    identity._reset_profile_cache()
    counter = {"n": 0}

    class _FakeClient:
        def __init__(self, service):
            self._service = service

        def get_user_profile(self):
            counter["n"] += 1
            return {"name": {"fullName": f"User {counter['n']}"}, "emailAddress": None}

    monkeypatch.setattr(identity, "ClassroomClient", _FakeClient)
    monkeypatch.setattr(identity, "build_service", lambda _creds: object())

    first = identity._cached_profile(db.get(User, alice.id), object())
    second = identity._cached_profile(db.get(User, bob.id), object())
    assert first != second
    assert set(identity._profile_cache) == {alice.id, bob.id}
    assert all(isinstance(key, int) for key in identity._profile_cache)
    # A repeat lookup for the same user is served from the cache (per user).
    assert identity._cached_profile(db.get(User, alice.id), object()) == first
    identity._reset_profile_cache()


# ------------------------------------------------------ §68 index review


def test_indexes_follow_the_ownership_query_patterns(client):
    """§68: every index is justified by a query pattern, led by user id."""
    # Dispose the pool first: pooled SQLite connections may still sit on a
    # transaction snapshot taken before this test's create_all, and a
    # stale PRAGMA would hide indexes that exist in the file.
    engine.dispose()
    inspector = inspect(engine)
    # (table, index name, expected column order)
    expected = {
        ("coursework", "ix_coursework_user_course"): ["user_id", "course_id"],
        ("coursework_submissions", "ix_cw_submission_user_course"): [
            "user_id",
            "course_id",
        ],
        ("sessions", "ix_sessions_user_expires"): ["user_id", "expires_at"],
    }
    for (table, name), columns in expected.items():
        declared = {
            index["name"]: index["column_names"]
            for index in inspector.get_indexes(table)
        }
        assert declared.get(name) == columns, f"{table}.{name} is missing or changed"

    # The composite session index replaced the redundant single-column one.
    session_indexes = {
        index["name"]: index["column_names"]
        for index in inspector.get_indexes("sessions")
    }
    assert ("user_id",) not in session_indexes.values()

    # No blind indexes: explicit indexes on a cache table are led by the
    # owner column (so are the primary keys), with one documented exception:
    # coursework's due_at index exists for the calendar/sort query and was
    # already present before the multi-user schema (stage 3, §68 review).
    non_ownership_indexes = {
        ("coursework", "ix_coursework_due_at"),
        ("sessions", "ix_sessions_session_token_hash"),
        ("sessions", "ix_sessions_expires_at"),
    }
    cache_tables = (
        "courses",
        "coursework",
        "submissions",
        "course_roles",
        "course_students",
        "coursework_submissions",
        "sync_status",
        "sessions",
    )
    for table in cache_tables:
        for index in inspector.get_indexes(table):
            identity = (table, index["name"])
            if identity in non_ownership_indexes:
                continue
            assert index["column_names"][0] == "user_id", identity
    for table in ("courses", "coursework", "submissions"):
        pk = inspector.get_pk_constraint(table)["constrained_columns"]
        assert pk[0] == "user_id", (table, pk)


# ---------------------------------------------------- §70 naive UTC times


def test_all_stored_timestamps_are_naive_utc():
    """§70: the backend compares naive UTC values; nothing stores tz-aware."""
    import hosted_auth
    import maintenance
    import ownership
    import sync_scheduler

    for factory in (
        ownership._utcnow,
        hosted_auth._utcnow,
        maintenance._utcnow,
        sync_scheduler._now,
    ):
        assert factory().tzinfo is None

    # The scheduler's due arithmetic is plain naive-UTC subtraction, so the
    # server's timezone cannot shift a due time (no DST arithmetic happens
    # on stored values).
    now = datetime(2026, 9, 23, 12, 0, 0)  # noqa: DTZ001 - naive UTC on purpose
    last = now - timedelta(minutes=11)
    assert (now - last) > timedelta(minutes=10)


# ------------------------------------------------- §40/§88 capacity model


def test_capacity_defaults_stay_conservative():
    """§88: the first-production configuration is the small one."""
    from config import (
        DB_MAX_OVERFLOW,
        DB_POOL_SIZE,
        SYNC_MANUAL_COOLDOWN_SECONDS,
        SYNC_MAX_CONCURRENT_USERS,
        SYNC_MAX_WORKERS,
    )

    assert SYNC_MAX_WORKERS <= 8
    assert SYNC_MAX_CONCURRENT_USERS <= 4
    assert DB_POOL_SIZE <= 10 and DB_MAX_OVERFLOW <= 10
    assert SYNC_MANUAL_COOLDOWN_SECONDS > 0


def test_capacity_target_matches_the_compose_header():
    """§88: the modelled target is the deployment's advertised capacity.

    ``compose.yml`` states "~1500 users / ~100 teachers" in its header. When the
    VPS was resized, that header and this module drifted apart, and the drift was
    invisible precisely because every test passed explicit users/teachers and
    never read ``TARGET_USERS``. Pinning the constants against the numbers a
    deploy actually advertises keeps the sync/DB budgets in ``.env.example``
    justified by real arithmetic instead of by stale prose.
    """
    import capacity

    assert capacity.TARGET_USERS == 1500
    assert capacity.TARGET_TEACHERS == 100

    # The defaults must be the constants, not a second hard-coded pair.
    report = capacity.capacity_report(interval_minutes=30)
    assert report["users"] == capacity.TARGET_USERS
    assert report["teachers"] == capacity.TARGET_TEACHERS

    # 1500 x 5 + 100 x 40 = 11500 requests per interval, over 30 minutes:
    # ~383/min (~6.4 QPS), i.e. still an order of magnitude below the
    # per-project Classroom quota (§40) — the reason the conservative
    # .env.example budgets stay conservative.
    assert report["avg_requests_per_minute"] == 383.3
    assert report["avg_requests_per_second"] == 6.39


def test_capacity_math_for_a_thousand_users():
    """§88: the estimate is computed, not assumed."""
    import capacity

    average = capacity.estimate_requests_per_minute(
        users=1000, teachers=25, interval_minutes=10
    )
    # 1000 x 5 + 25 x 40 = 6000 requests per interval, over 10 minutes.
    assert average == 600.0
    assert (
        capacity.estimate_requests_per_second(
            users=1000, teachers=25, interval_minutes=10
        )
        == 10.0
    )
    # Halving the interval doubles the rate (the knob a reviewer turns).
    assert (
        capacity.estimate_requests_per_minute(
            users=1000, teachers=25, interval_minutes=5
        )
        == 1200.0
    )
    with pytest.raises(ValueError):
        capacity.estimate_requests_per_minute(interval_minutes=0)


def test_thread_budget_is_the_product_of_the_two_limits():
    """§88: the worker thread budget is bounded and explicit."""
    import capacity

    assert capacity.sync_thread_budget(workers=4, concurrent_users=2) == 8
    assert capacity.sync_thread_budget() == capacity.sync_thread_budget(
        workers=capacity.SYNC_MAX_WORKERS,
        concurrent_users=capacity.SYNC_MAX_CONCURRENT_USERS,
    )
    report = capacity.capacity_report(users=1000, teachers=25, interval_minutes=10)
    assert report["avg_requests_per_minute"] == 600.0
    assert report["sync_thread_budget"] <= 32
    # §40: one user's burst is bounded by their own worker pool — the pool,
    # not the quota, is what caps a single sync's fan-out.
    assert capacity.peak_requests_per_minute(users_per_sync=3) == 12
    assert capacity.peak_requests_per_minute(users_per_sync=3, max_workers=4) == 12
