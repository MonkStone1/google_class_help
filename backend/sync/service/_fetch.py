"""Sync orchestration: pull data from Google, hand it to the cache layer.

The fetch half of one sync. The write half is ``sync/service/results.py``: the
split is not cosmetic, because the two halves fail differently — this one is
slow and network-bound and may be retried, the other is a short transaction
that must verify its claim before it writes.

Every sync belongs to ONE user (migration stage 4, §12): the owner is resolved
from the authenticated user, and the Google credentials come from the
user-scoped credential layer (gapi/credentials.py, §15) — never from a
process-global token state.

Multi-user scheduling (migration stage 5, §18): concurrency is controlled PER
USER, not per process. Two different users may sync at the same time; the same
user may not — an in-process per-user lock serializes threads of this process,
and a conditional UPDATE on ``sync_status`` (sync/store/status.claim_sync)
serializes whole worker containers. Every run records its start/finish/success
/error into that user's ``sync_status`` row, and the error text kept there is a
short user-facing sentence — raw exception text and stack traces stay in the
server log (§18).
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from auth import ownership
from core import metrics
from core.config import (
    SYNC_CLAIM_STALE_SECONDS,
    SYNC_MAX_CONCURRENT_USERS,
    SYNC_MAX_WORKERS,
    SYNC_STUCK_SECONDS,
)
from db.models.accounts import User
from db.session import SessionLocal
from gapi import credentials
from gapi.classroom import ClassroomClient, RequestStats, build_service
from sync.service import results
from sync.service.common import (
    ALREADY_RUNNING,
    COURSES_FAILED,
    NEEDS_REAUTH,
    NOT_SIGNED_IN,
    SUPERSEDED,
    now,
    public_error,
)
from sync.store import (
    abandon_claim,
    claim_is_own,
    claim_sync,
    mark_sync_failed,
    mark_sync_needs_reauth,
    mark_sync_pending,
    request_sync,
)

# The cache purge and the two course writers are the private halves of the
# cache layer, so they are named from the modules that DEFINE them rather than
# through the facade. They are underscore-named because nothing outside the
# write path should call them; this module is that path.

logger = logging.getLogger(__name__)

# Returned when this user already has a sync in flight. The exact wording
# is part of the API contract: api.py maps it to HTTP 409 (review §3.9).
# Returned when every global sync slot is taken (§65). api.py maps it to 503.
SERVER_BUSY = "The server is busy synchronizing other accounts; try again shortly."
# Returned by a run that lost its claim while fetching (ADR-0032): its data was
# fetched but must NOT be written, because another run now owns the cache. It
# is not a failure of the account — the run that superseded it reports the
# outcome — so the message stays neutral and the caller only logs it.

# Per-user sync mutexes (stage 5, §18). A process-global lock would
# serialize every user; keying by owner id lets independent accounts sync
# in parallel while the same account is still protected from running
# twice. The registry itself is guarded; entries are tiny and survive for
# the process lifetime, which also keeps a lock object stable for callers.
_sync_locks_guard = threading.Lock()
_sync_locks: dict[int, threading.Lock] = {}


# Global concurrency of INTERACTIVE (user-triggered) syncs (§65). The
# per-user pool bounds one account's request fan-out (SYNC_MAX_WORKERS);
# this bounds how many accounts run at once so a burst of "Sync now" clicks
# after a deploy cannot open N pools of workers. Scheduled/background syncs
# are already bounded by the scheduler's own pool (stage 5) and are not
# counted here. The counter is per process; the supported deployment runs a
# single worker plus the web replicas, each with this ceiling.
_slots_lock = threading.Lock()
_active_interactive = 0


def _acquire_interactive_slot() -> bool:
    """Take one global interactive slot, or fail immediately (§65)."""
    global _active_interactive
    with _slots_lock:
        if _active_interactive >= SYNC_MAX_CONCURRENT_USERS:
            return False
        _active_interactive += 1
        return True


def _release_interactive_slot() -> None:
    global _active_interactive
    with _slots_lock:
        _active_interactive -= 1


def _sync_lock_for(user_id: int) -> threading.Lock:
    with _sync_locks_guard:
        return _sync_locks.setdefault(user_id, threading.Lock())


def sync_now(user: User | None = None, *, interactive: bool = False) -> dict:
    """Pull a user's Classroom data into that user's cache scope (§12/§18).

    ``user`` is the authenticated user whose cache to refresh — the
    session user on the hosted service, the local owner on desktop
    (``None`` keeps the desktop background path unchanged). Safe to call
    concurrently: the same user's second caller is told a sync is already
    running instead of duplicating requests, while another user's caller
    proceeds independently.

    ``interactive=True`` (the user-triggered ``POST /api/sync``) also takes
    one of the process's global slots (§65): when ``SYNC_MAX_CONCURRENT_USERS``
    interactive syncs are already running the call returns SERVER_BUSY
    instead of stacking another pool of workers. Scheduled and background
    syncs pass the default — the scheduler already bounds them.
    """
    if interactive and not _acquire_interactive_slot():
        return {"ok": False, "error": SERVER_BUSY}
    try:
        if user is not None:
            owner_id = user.id
        else:
            with SessionLocal() as db:
                owner = ownership.ensure_local_owner(db)
                owner_id = owner.id
                # The synthetic owner is created by this very call on the first
                # desktop run; committing here is what makes it survive the
                # session close — otherwise _do_sync would reload nothing and
                # every background run would report "Not signed in to Google".
                db.commit()
        lock = _sync_lock_for(owner_id)
        if not lock.acquire(blocking=False):
            return {"ok": False, "error": ALREADY_RUNNING}
        try:
            return _do_sync(owner_id)
        finally:
            lock.release()
    finally:
        if interactive:
            _release_interactive_slot()


def sync_user_id(user_id: int) -> dict:
    """Sync one user by id — the scheduler/worker entry point (stage 5).

    The scheduler selects users from the database without loading their ORM
    objects; this resolves the row for :func:`sync_now`, which then applies
    the same per-user locking and state transitions as a manual sync.
    """
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return {"ok": False, "error": NOT_SIGNED_IN}
        # Detach before the session closes: sync_now only reads ``id``.
        db.expunge(user)
    return sync_now(user=user)

def _do_sync(owner_id: int) -> dict:
    # Stage 9 (§45): short transactions, one session per phase — never hold a
    # transaction open across the Google fetch. Each block below opens its
    # own SessionLocal scope and closes it before the next phase starts: a
    # stalled Classroom round-trip pins no pooled PostgreSQL connection,
    # and worker threads never share a Session (they never touch one —
    # threads only call Google, all DB work stays on this thread).
    from db.models.accounts import User as _User

    pool = ThreadPoolExecutor(max_workers=SYNC_MAX_WORKERS)
    # One per-run counter shared by every worker thread's client (§65): it
    # makes the real Google request volume of a sync (much higher for a
    # teacher account) visible in the log for capacity planning (stage 9).
    stats = RequestStats()
    started_monotonic = time.monotonic()
    with SessionLocal() as db:
        user = db.get(_User, owner_id)
        if user is None or not user.is_active:
            return {"ok": False, "error": NOT_SIGNED_IN}
        # Claim this user's sync slot before any network work (stage 5, §18):
        # the conditional UPDATE also excludes a job another worker container
        # already started for the same account.
        started_at = now()
        if not claim_sync(
            db, owner_id, started_at, stale_after=SYNC_CLAIM_STALE_SECONDS
        ):
            return {"ok": False, "error": ALREADY_RUNNING}
        # The cache rows written by this sync belong to this user (§10);
        # the credentials are that same user's (§15) — hosted users read
        # their own oauth_tokens row, desktop its single token.json.
        # NOTE: get_google_credentials may refresh the token over the
        # network; the surrounding transaction only holds the claim row and
        # the token row, and commits (inside save_google_credentials)
        # before the Classroom fetch starts.
        creds = credentials.get_google_credentials(db, user)
        if creds is None:
            # Distinguish "never signed in" from "the stored grant is
            # unusable": only the latter pauses scheduled sync (§63).
            if credentials.has_google_grant(db, user):
                mark_sync_needs_reauth(db, owner_id, NEEDS_REAUTH, now())
                return {"ok": False, "error": NEEDS_REAUTH}
            mark_sync_pending(db, owner_id, now())
            return {"ok": False, "error": NOT_SIGNED_IN}
    # The db session above is closed here: everything below until the write
    # phase is pure Google I/O on ``creds`` (a detached Credentials object),
    # holding no database transaction at all (§45).
    try:
        service = build_service(creds)
        client = ClassroomClient(service, stats=stats)

        # One shared pool for every network stage (per-course lists and the
        # point courseWork.get lookups): threads and their per-thread API
        # clients are built once and reused instead of once per course. All
        # database work stays on this thread — SQLAlchemy sessions are not
        # thread-safe. 429s are absorbed by execute(num_retries) backoff,
        # so exceeding the per-user quota briefly only slows down, never
        # fails the sync.
        courses = _resolve_courses(client)
        if courses is None:
            # courses.list failed (HTTP error): keep the cache and record the
            # error instead of purging every course as "gone" (review §1.7).
            logger.warning(COURSES_FAILED)
            with SessionLocal() as db:
                mark_sync_failed(db, owner_id, COURSES_FAILED, now())
            return {"ok": False, "error": COURSES_FAILED}
        active_ids = {raw["id"] for raw, _ in courses}

        get_client = _thread_local_client(creds, stats)
        teacher_names, payloads = _fetch_course_payloads(get_client, courses, pool)

        # Student courses discover coursework via their submissions and then
        # fetch each assignment individually (courseWork.list is teacher-only
        # for them — ADR-0010). Teacher courses already got the full list in
        # the payload stage above.
        work_requests: list[tuple[str, str]] = []
        for raw_course, role in courses:
            if role != "STUDENT":
                continue
            course_id = raw_course["id"]
            seen: set[str] = set()
            for raw_sub in payloads[course_id]["submissions"]:
                work_id = raw_sub.get("courseWorkId")
                if work_id and work_id not in seen:
                    seen.add(work_id)
                    work_requests.append((course_id, work_id))
        work_cache = _fetch_coursework(get_client, work_requests, pool)
    except Exception as exc:  # any Google/network error lands in sync_status (§18)
        # Sanitized sentence to the dashboard, full stack to the log — raw
        # exception text never reaches the frontend. The counters show
        # whether this was quota pressure or a Classroom outage (§60).
        counters = stats.snapshot()
        logger.exception(
            "Classroom sync failed after %d Google requests "
            "(quota_errors=%d server_errors=%d)",
            counters["requests"],
            counters["quota_errors"],
            counters["server_errors"],
        )
        message = public_error(exc)
        with SessionLocal() as db:
            # The fence of ADR-0032 comes BEFORE the status write: a run whose
            # claim was taken over must not stamp its failure on the row now
            # owned by the newer run — that would show the user an error for a
            # sync that is still running fine.
            if not claim_is_own(db, owner_id, started_at):
                logger.info(
                    "Sync for user=%s lost its claim while failing; not recording "
                    "the error.",
                    owner_id,
                )
                return {"ok": False, "error": SUPERSEDED}
            if message == NEEDS_REAUTH:
                # Stage 9 (§41): a 401 during the sync means this user's
                # grant died mid-flight (revoked in the Google account).
                # Mark the account for re-authorization, stop retrying, and
                # drop ONLY this user's credential row — other users' grants
                # and sessions are untouched.
                credentials.delete_google_credentials(db, owner_id)
                mark_sync_needs_reauth(db, owner_id, message, now())
                metrics.record(metrics.SYNC_NEEDS_REAUTH)
            else:
                mark_sync_failed(db, owner_id, message, now())
                metrics.record(metrics.SYNC_FAILED)
        return {"ok": False, "error": message}
    finally:
        pool.shutdown(wait=True)
    return _write_sync_results(
        owner_id,
        courses,
        active_ids,
        teacher_names,
        payloads,
        work_cache,
        stats,
        started_monotonic,
        started_at,
    )


def restart_stuck_sync(db: Session, owner_id: int) -> bool:
    """Abandon this user's stuck claim and queue a fresh sync (ADR-0032).

    The hosted counterpart of the ``restart`` flag on ``POST /api/sync``: the web
    process never runs the Classroom fan-out, so it only releases the stale
    claim and raises ``sync_requested`` — the worker picks the account up on its
    next scan. One condition decides the outcome, and it is the same one the
    dashboard shows the user as "stuck": a claim younger than
    ``SYNC_STUCK_SECONDS`` is still a legitimate long sync and is never touched.

    Returns True when a stuck claim was released and a new sync was queued.
    """
    released = abandon_claim(db, owner_id, now(), older_than=SYNC_STUCK_SECONDS)
    if not released:
        metrics.record(metrics.SYNC_RESTART_REJECTED)
        return False
    request_sync(db, owner_id)
    metrics.record(metrics.SYNC_RESTARTED)
    logger.info(
        "Restarted a stuck sync for user=%s (claim older than %d s).",
        owner_id,
        SYNC_STUCK_SECONDS,
    )
    return True


# The write phase lives in ``sync/service/results.py`` (ADR-0039). It is
# re-bound here so the call inside ``_do_sync`` keeps reading naturally and so a
# monkeypatch of ``service._write_sync_results`` still reaches the caller.
_write_sync_results = results.write_sync_results

# The Google fan-out lives in ``sync/service/_fetching.py`` (ADR-0039). These
# names are bound, not copied, so the sync tests replace them on that module and
# this half picks the replacement up.
from sync.service._fetching import (
    _fetch_course_payloads,
    _fetch_coursework,
    _resolve_courses,
    _thread_local_client,
)
