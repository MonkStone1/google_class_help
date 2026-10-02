"""The write phase of one sync: fetch results become cache rows (§45).

Split out of ``service.py`` (ADR-0039) because the fetch and the write are two
different concerns with two different failure stories. The fetch is slow,
network-bound and retryable; the write is short, transactional and must not be
retried the same way. Keeping them in one module made that difference invisible
in a 650-line file.

The rule that shapes everything here: the transaction is opened at the END of
the sync, never across the fetch. A claim can be taken over while a teacher fan-
out runs for minutes (ADR-0032), so the first thing this phase does is confirm
the claim is still ours — otherwise a superseded run would write its stale
results over the fresh ones.
"""

import logging
import time
from datetime import datetime

from core import metrics
from db.models.classroom import Course, CourseRole
from db.session import SessionLocal
from gapi.classroom import RequestStats
from sync.service.common import NOT_SIGNED_IN, SUPERSEDED, now, public_error
from sync.store.cache import _purge_stale_courses
from sync.store.status import claim_is_own, mark_sync_failed, mark_sync_succeeded
from sync.store.writing import (
    _write_student_course,
    _write_teacher_course,
    upsert_submission,
)

logger = logging.getLogger(__name__)

def write_sync_results(
    owner_id: int,
    courses: list,
    active_ids: set[str],
    teacher_names: dict,
    payloads: dict,
    work_cache: dict,
    stats: RequestStats,
    started_monotonic: float,
    started_at: datetime,
) -> dict:
    """Persist one finished fetch into the owner's cache scope (§45).

    Own short transaction at the END of the sync (not across the fetch):
    the write phase commits per course so a 1,000-course teacher cache
    cannot hold one giant transaction, and the Google request counters land
    in the success log line for the capacity review (§60).

    ``started_at`` is the claim timestamp of THIS run, and the first thing the
    write phase does is verify it still holds that claim (ADR-0032). Fetching
    takes minutes, and a claim can be taken over in that window either by the
    scheduled stale-claim re-claim or by the user's own "restart the stuck
    sync". Without this check the superseded run would keep going: it would
    write courses the newer run has already replaced and — worse — run
    ``_purge_stale_courses`` against its own older snapshot, deleting courses
    that were created while it was fetching, and then stamp "ok" over a run
    that is still in flight. Losing the race is normal here (a restart is a
    deliberate second attempt), so it is reported as SUPERSEDED, not as an error.
    """
    from db.models.accounts import User as _User

    assignment_count = 0
    # Stamped on every course row this run writes, so "when did this cache row
    # last come from Google" is answerable per row rather than per process.
    synced_at = now()

    with SessionLocal() as db:
        try:
            owner = db.get(_User, owner_id)
            if owner is None or not owner.is_active:
                return {"ok": False, "error": NOT_SIGNED_IN}
            if not claim_is_own(db, owner_id, started_at):
                # The run that owns the cache now reports the outcome; this one
                # fetched data that is already obsolete and must write nothing.
                counters = stats.snapshot()
                logger.info(
                    "Sync for user=%s lost its claim after %d Google requests; "
                    "discarding the result.",
                    owner_id,
                    counters["requests"],
                )
                return {"ok": False, "error": SUPERSEDED}
            for raw_course, role in courses:
                course_id = raw_course["id"]
                # The fence is re-checked per course, not once before the loop.
                # The write phase commits after every course, so on a teacher
                # account with hundreds of courses it stays open for minutes —
                # long enough for a restart (ADR-0032) or a stale-claim takeover
                # to hand the cache to another run. One check before the loop
                # left that whole window unfenced, and both runs then wrote the
                # same course: two INSERTs of one coursework id, and the loser
                # died on a unique violation the user saw as "Sync failed".
                # Expire first so the fence reads the row, not the copy the
                # check before the loop left in the identity map — ``db.get``
                # would otherwise answer from there, where the claim still looks
                # ours. Safe because nothing is uncommitted at this point (the
                # previous iteration ended with db.commit()), and it costs one
                # round trip per course next to hundreds of Google requests.
                db.expire_all()
                if not claim_is_own(db, owner_id, started_at):
                    counters = stats.snapshot()
                    logger.info(
                        "Sync for user=%s lost its claim while writing course %s "
                        "after %d Google requests; stopping.",
                        owner_id,
                        course_id,
                        counters["requests"],
                    )
                    db.rollback()
                    return {"ok": False, "error": SUPERSEDED}
                upsert_submission(
                    db,
                    Course,
                    {"user_id": owner_id, "id": course_id},
                    {
                        "name": raw_course.get("name", "Untitled course"),
                        "description": raw_course.get("descriptionHeading")
                        or raw_course.get("description"),
                        "section": raw_course.get("section"),
                        "room": raw_course.get("room"),
                        "enrollment_state": raw_course.get("enrollmentState"),
                        "course_state": raw_course.get("courseState"),
                        "teacher_names": teacher_names.get(course_id, []),
                        "synced_at": synced_at,
                    },
                )
                upsert_submission(
                    db,
                    CourseRole,
                    {"user_id": owner_id, "course_id": course_id},
                    {"role": role},
                )

                payload = payloads[course_id]
                if role == "TEACHER":
                    assignment_count += _write_teacher_course(
                        db, owner_id, course_id, payload
                    )
                else:
                    assignment_count += _write_student_course(
                        db, owner_id, course_id, payload["submissions"], work_cache
                    )
                db.commit()

            # Mirror cleanup: archived, deleted and unenrolled courses are no
            # longer part of the student dashboard. Anything the API did not
            # return for THIS owner's cache on this sync is removed from it.
            _purge_stale_courses(db, owner_id, active_ids)

            mark_sync_succeeded(db, owner_id, now())
            elapsed = time.monotonic() - started_monotonic
            counters = stats.snapshot()
            metrics.record(metrics.SYNC_SUCCEEDED)
            logger.info(
                "Sync ok user=%s courses=%d assignments=%d google_requests=%d "
                "quota_errors=%d server_errors=%d duration=%.1fs",
                owner_id,
                len(courses),
                assignment_count,
                counters["requests"],
                counters["quota_errors"],
                counters["server_errors"],
                elapsed,
            )
            return {
                "ok": True,
                "last_sync": now,
                "courses": len(courses),
                "assignments": assignment_count,
            }
        except Exception as exc:  # any write error lands in sync_status, not the API
            # The dashboard gets the short, sanitized sentence below; the log
            # keeps the whole stack. Raw exception text never reaches the
            # frontend (§18). The fetch already finished, so there is no
            # Google/network error left to catch here — only cache writes.
            counters = stats.snapshot()
            logger.exception(
                "Classroom sync write failed after %d Google requests "
                "(quota_errors=%d server_errors=%d)",
                counters["requests"],
                counters["quota_errors"],
                counters["server_errors"],
            )
            db.rollback()
            message = public_error(exc)
            mark_sync_failed(db, owner_id, message, now())
            return {"ok": False, "error": message}
