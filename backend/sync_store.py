"""Cache write layer: everything that writes Classroom data into the
Classroom cache (review §2.2). Reads happen in api.py, orchestration in
sync_service.py; this module knows the tables and the shapes Google sends,
nothing else.

Every function takes the ``user_id`` of the cache owner (migration stage
3, §10): rows of different users live side by side in the same tables, and
every key lookup, delete and mirror-cleanup is scoped to one owner's rows.
"""

from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, delete, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from classroom_api import parse_date_time, parse_rfc3339
from models import (
    Course,
    CourseRole,
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
    StudentSubmission,
    SyncStatus,
)

SubmissionRow = CourseWorkSubmission | StudentSubmission


# ------------------------------------------------------------- sync status
#
# One structured row per user (migration stage 5, §18) replaces the former
# key/value sync_state table. The scheduler reads it to decide who is due;
# the sync itself writes every transition through the functions below, so
# there is exactly one source of truth for "when did this user last sync,
# did it work, and may it be scheduled again".

SYNC_PENDING = "pending"
SYNC_RUNNING = "running"
SYNC_OK = "ok"
SYNC_ERROR = "error"
SYNC_NEEDS_REAUTH = "needs_reauth"

# Safety net for the VARCHAR(500) of sync_status.last_error: the message is
# ours, but truncating here keeps a future longer sentence from aborting an
# INSERT on PostgreSQL.
_MAX_ERROR_LENGTH = 500


def sync_status(db: Session, user_id: int) -> SyncStatus | None:
    """The user's sync-status row, or None if the user never touched sync."""
    return db.get(SyncStatus, user_id)


def _status_row(db: Session, user_id: int) -> SyncStatus:
    """The user's sync-status row, created on first use.

    Creation is idempotent under concurrency: if another process inserted
    the same PK between our SELECT and flush, the unique violation is
    rolled back and the existing row is read instead. No other pending
    change exists in this session at that point (the row is created before
    the sync starts its work).
    """
    row = db.get(SyncStatus, user_id)
    if row is not None:
        return row
    db.add(SyncStatus(user_id=user_id, status=SYNC_PENDING))
    try:
        db.flush()
    except IntegrityError:  # pragma: no cover - concurrent first touch
        db.rollback()
        row = db.get(SyncStatus, user_id)
        if row is None:
            raise
        return row
    row = db.get(SyncStatus, user_id)
    if row is None:  # pragma: no cover - only if the row vanished again
        raise RuntimeError(f"sync_status row for user {user_id} disappeared")
    return row


def claim_sync(db: Session, user_id: int, now: datetime, *, stale_after: int) -> bool:
    """Atomically claim the user's sync slot; False when one is in flight.

    The conditional UPDATE is what makes the scheduler safe across worker
    containers (migration stage 5, §19): a scan in container B cannot start
    a job for a user a scan in container A already claimed. A ``running``
    row whose ``last_started_at`` is older than ``stale_after`` seconds is
    assumed to belong to a crashed worker and may be taken over, so a hard
    kill cannot park a user forever.
    """
    _status_row(db, user_id)
    cutoff = now - timedelta(seconds=stale_after)
    result = cast(
        CursorResult,
        db.execute(
            update(SyncStatus)
            .where(SyncStatus.user_id == user_id)
            .where(
                or_(
                    SyncStatus.status != SYNC_RUNNING,
                    SyncStatus.last_started_at.is_(None),
                    SyncStatus.last_started_at < cutoff,
                )
            )
            .values(status=SYNC_RUNNING, last_started_at=now, sync_requested=False)
        ),
    )
    db.commit()
    return bool(result.rowcount)


def request_sync(db: Session, user_id: int) -> None:
    """Queue an immediate sync for one user, lifting ``needs_reauth`` (§63).

    Called after a successful sign-in: the user just granted Google access
    again, so a paused account becomes schedulable and should not wait out
    the regular interval. The worker picks the flag up on its next scan and
    the job clears it when it claims the user. A flag, not a timestamp, on
    purpose: the sign-in happens in the web process and the job runs in the
    worker container, so no shared clock is required.
    """
    row = _status_row(db, user_id)
    row.sync_requested = True
    if row.status == SYNC_NEEDS_REAUTH:
        row.status = SYNC_PENDING
        row.last_error = None
        row.consecutive_failures = 0
    db.commit()


def mark_sync_succeeded(db: Session, user_id: int, now: datetime) -> None:
    """Record a finished, successful run: this is "last sync" for the UI."""
    row = _status_row(db, user_id)
    row.status = SYNC_OK
    row.last_finished_at = now
    row.last_success_at = now
    row.last_error = None
    row.consecutive_failures = 0
    db.commit()


def mark_sync_failed(db: Session, user_id: int, message: str, now: datetime) -> None:
    """Record a retryable failure; ``message`` must be user-safe (§18)."""
    row = _status_row(db, user_id)
    row.status = SYNC_ERROR
    row.last_finished_at = now
    row.last_error = message[:_MAX_ERROR_LENGTH]
    row.last_error_at = now
    row.consecutive_failures = (row.consecutive_failures or 0) + 1
    db.commit()


def mark_sync_needs_reauth(
    db: Session, user_id: int, message: str, now: datetime
) -> None:
    """Pause scheduled sync for a user until they sign in again (§63)."""
    row = _status_row(db, user_id)
    row.status = SYNC_NEEDS_REAUTH
    row.last_finished_at = now
    row.last_error = message[:_MAX_ERROR_LENGTH]
    row.last_error_at = now
    row.consecutive_failures = (row.consecutive_failures or 0) + 1
    db.commit()


def mark_sync_pending(db: Session, user_id: int, now: datetime) -> None:
    """Release a claim without reporting an error (no Google grant yet)."""
    row = _status_row(db, user_id)
    row.status = SYNC_PENDING
    row.last_finished_at = now
    db.commit()


def release_claim(db: Session, user_id: int, now: datetime) -> bool:
    """Release one user's claim without an error, if it is still ours.

    Used on SIGTERM (sync_worker.run_forever) so a graceful stop hands the
    account back to the schedule instead of parking it in ``running`` until
    the claim's stale window expires. The conditional guard is the same idea
    as :func:`claim_sync` in reverse: only a row that is still ``running``
    AND was started at or before ``now`` is released, so a shutdown in one
    worker can never cancel a job another process has already re-claimed.

    Returns True when a row was actually released. Releasing is best effort —
    a caller shutting down treats ``False`` as "nothing of mine to undo".
    """
    result = cast(
        CursorResult,
        db.execute(
            update(SyncStatus)
            .where(SyncStatus.user_id == user_id)
            .where(SyncStatus.status == SYNC_RUNNING)
            .where(
                or_(
                    SyncStatus.last_started_at.is_(None),
                    SyncStatus.last_started_at <= now,
                )
            )
            .values(status=SYNC_PENDING)
        ),
    )
    db.commit()
    return bool(result.rowcount)


def last_sync_time(db: Session, user_id: int) -> datetime | None:
    """When this user's cache was last filled successfully."""
    row = db.get(SyncStatus, user_id)
    return row.last_success_at if row else None


def last_sync_error(db: Session, user_id: int) -> str | None:
    """The user-facing description of the last failed run, if any."""
    row = db.get(SyncStatus, user_id)
    return row.last_error if row else None


# ------------------------------------------------------- unified access §2.3


def get_submission(
    db: Session,
    user_id: int,
    course_id: str,
    coursework_id: str,
    student_id: str,
    *,
    is_teacher: bool,
) -> SubmissionRow | None:
    """One access point to a student's submission (review §2.3).

    The same fact lives in two tables (ADR-0003 cache compatibility): a
    teacher course keeps per-student rows in CourseWorkSubmission, the
    student route keeps the user's own row in StudentSubmission. The role
    picks the table here, so callers never branch on it themselves. Both
    lookups are scoped to the cache owner (user_id) — stage 3.
    """
    if is_teacher:
        return db.get(
            CourseWorkSubmission, (user_id, course_id, coursework_id, student_id)
        )
    return db.get(StudentSubmission, (user_id, course_id, coursework_id))


# ------------------------------------------------------------------ purging


def _purge_course(db: Session, user_id: int, course_id: str) -> None:
    """Remove one owner's course and its cached rows (archived/gone courses).

    SQLite runs with PRAGMA foreign_keys=ON (database.py) and PostgreSQL
    always enforces FKs, so the ondelete=CASCADE rules on every child table
    do the work — one delete instead of five hand-written ones (review
    §1.6). The composite key (user_id, course_id) keeps the delete inside
    one user's cache (audit Y3).
    """
    stale = db.get(Course, (user_id, course_id))
    if stale is None:
        return
    # A parameterized delete() statement, not an ORM instance delete: with
    # enforced foreign keys the DB cascades every child row itself.
    db.execute(delete(Course).where(Course.user_id == user_id, Course.id == course_id))
    db.commit()


def _purge_stale_courses(db: Session, user_id: int, active_ids: set[str]) -> None:
    """Remove THIS owner's cached courses the Classroom API no longer returns.

    Covers ARCHIVED courses as well as courses the user left (unenrolled) or
    that were deleted in Google. The API list call has already succeeded at
    this point, so a missing id is authoritative rather than an error. The
    user_id scope is essential (audit Y3): another user's identical course
    id must survive this purge untouched.
    """
    cached_ids = [
        row[0] for row in db.query(Course.id).filter(Course.user_id == user_id).all()
    ]
    for course_id in cached_ids:
        if course_id not in active_ids:
            _purge_course(db, user_id, course_id)


def reset_cache(db: Session, user_id: int) -> None:
    """Delete all cached Classroom data of one user (destructive, confirmed).

    Scoped to the calling user (migration stage 3 groundwork for §10/§12):
    deleting every table's rows regardless of owner would erase other
    users' caches. Explicit statements per table (no loop variable passed
    to delete()): the table set is fixed at compile time.
    """
    db.execute(
        delete(CourseWorkSubmission).where(CourseWorkSubmission.user_id == user_id)
    )
    db.execute(delete(CourseStudent).where(CourseStudent.user_id == user_id))
    db.execute(delete(CourseRole).where(CourseRole.user_id == user_id))
    db.execute(delete(StudentSubmission).where(StudentSubmission.user_id == user_id))
    db.execute(delete(CourseWork).where(CourseWork.user_id == user_id))
    db.execute(delete(Course).where(Course.user_id == user_id))
    db.execute(delete(SyncStatus).where(SyncStatus.user_id == user_id))
    db.commit()


# ------------------------------------------------------------------ writing


def _parse_points(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _submitted_at(raw_sub: dict) -> datetime | None:
    """Timestamp of the most recent TURNED_IN event, if the student turned in."""
    latest = None
    for entry in raw_sub.get("submissionHistory") or []:
        state_history = entry.get("stateHistory") or {}
        if state_history.get("state") == "TURNED_IN":
            latest = parse_rfc3339(state_history.get("stateTimestamp")) or latest
    return latest


def _submission_attachments(raw_sub: dict) -> list[dict]:
    """Reduce a submission's attachments to the fields the UI shows.

    Mirrors :func:`_materials_to_json` for assignment materials. Only the
    file/link metadata Google returns is stored — no attempt is made to read
    Drive contents the app has no permission for.
    """
    submission = raw_sub.get("assignmentSubmission") or {}
    out: list[dict] = []
    for attachment in submission.get("attachments") or []:
        drive = attachment.get("driveFile") or {}
        link = attachment.get("link") or {}
        form = attachment.get("form") or {}
        video = attachment.get("youTubeVideo") or attachment.get("youtubeVideo") or {}
        if drive:
            out.append(
                {
                    "type": "drive",
                    "title": drive.get("title"),
                    "url": drive.get("alternateLink"),
                }
            )
        elif link:
            out.append(
                {"type": "link", "title": link.get("title"), "url": link.get("url")}
            )
        elif form:
            out.append(
                {"type": "form", "title": form.get("title"), "url": form.get("formUrl")}
            )
        elif video:
            out.append(
                {
                    "type": "youtube",
                    "title": video.get("title"),
                    "url": video.get("alternateLink"),
                }
            )
    return out


def _materials_to_json(raw_materials: list[dict]) -> list[dict]:
    """Reduce raw Classroom materials to the fields the UI needs."""
    out: list[dict] = []
    for material in raw_materials:
        drive = material.get("driveFile", {}).get("driveFile", {})
        link = material.get("link", {})
        form = material.get("form", {})
        youtube = material.get("youtubeVideo", {})
        if drive:
            out.append(
                {
                    "type": "drive",
                    "title": drive.get("title"),
                    "url": drive.get("alternateLink"),
                }
            )
        elif link:
            out.append(
                {"type": "link", "title": link.get("title"), "url": link.get("url")}
            )
        elif form:
            out.append(
                {
                    "type": "form",
                    "title": form.get("title"),
                    "url": form.get("formUrl"),
                }
            )
        elif youtube:
            out.append(
                {
                    "type": "youtube",
                    "title": youtube.get("title"),
                    "url": youtube.get("alternateLink"),
                }
            )
    return out


def _upsert_work(db: Session, user_id: int, course_id: str, raw_work: dict) -> None:
    """Insert/update one coursework row from a raw Classroom object."""
    work_id = raw_work.get("id")
    if not work_id:
        return
    work = db.get(CourseWork, (user_id, work_id))
    if work is None:
        work = CourseWork(user_id=user_id, id=work_id, course_id=course_id)
        db.add(work)
    work.course_id = course_id
    work.title = raw_work.get("title", "Untitled assignment")
    work.description = raw_work.get("description")
    work.state = raw_work.get("state")
    work.work_type = raw_work.get("workType")
    work.due_at = parse_date_time(raw_work.get("dueDate"), raw_work.get("dueTime"))
    work.max_points = raw_work.get("maxPoints")
    work.alternate_link = raw_work.get("alternateLink")
    work.topic_id = raw_work.get("topicId")
    work.creation_time = parse_rfc3339(raw_work.get("creationTime"))
    work.updated_time = parse_rfc3339(raw_work.get("updateTime"))
    work.materials = _materials_to_json(raw_work.get("materials", []))


def _write_student_course(
    db: Session,
    user_id: int,
    course_id: str,
    submissions: list[dict],
    work_cache: dict[tuple[str, str], dict],
) -> int:
    """Cache a student's own coursework/submissions (existing route).

    courseWork.list is teacher-only for a student, so coursework is
    discovered through their submissions and each item is fetched by id
    (ADR-0010). Returns the number of coursework rows written.
    """
    count = 0
    for raw_sub in submissions:
        work_id = raw_sub.get("courseWorkId")
        if not work_id:
            continue
        raw_work = work_cache.get((course_id, work_id))
        if not raw_work:
            # courseWork.get may 403 (e.g. hidden/draft work) — skip.
            continue
        _upsert_work(db, user_id, course_id, raw_work)
        count += 1

        sub = db.get(StudentSubmission, (user_id, course_id, work_id))
        if sub is None:
            sub = StudentSubmission(
                user_id=user_id, course_id=course_id, coursework_id=work_id
            )
            db.add(sub)
        sub.state = raw_sub.get("state")
        sub.late = bool(raw_sub.get("late"))
        sub.assigned_points = _parse_points(raw_sub.get("assignedGrade"))
        sub.draft_points = _parse_points(raw_sub.get("draftGrade"))
        sub.updated_time = parse_rfc3339(raw_sub.get("updateTime"))
    return count


def _write_teacher_course(
    db: Session, user_id: int, course_id: str, payload: dict
) -> int:
    """Cache a teacher course: ALL coursework, the roster and every submission.

    The teacher's own account is not a student in the course, so nothing here
    touches :class:`StudentSubmission`. Each list is mirrored: rows the API
    no longer returns are removed, but a list that could not be loaded
    (``None``) leaves the cached rows untouched instead of wiping them.
    """
    count = 0
    coursework = payload.get("coursework")
    if coursework is not None:
        work_ids = set()
        for raw_work in coursework:
            work_id = raw_work.get("id")
            if not work_id:
                continue
            work_ids.add(work_id)
            _upsert_work(db, user_id, course_id, raw_work)
            count += 1
        for stale in (
            db.query(CourseWork).filter_by(user_id=user_id, course_id=course_id).all()
        ):
            if stale.id not in work_ids:
                db.execute(
                    delete(CourseWorkSubmission).where(
                        CourseWorkSubmission.user_id == user_id,
                        CourseWorkSubmission.course_id == course_id,
                        CourseWorkSubmission.coursework_id == stale.id,
                    )
                )
                db.delete(stale)

    students = payload.get("students")
    if students is not None:
        student_ids = set()
        for raw_student in students:
            student_id = raw_student.get("userId")
            if not student_id:
                continue
            student_ids.add(student_id)
            row = db.get(CourseStudent, (user_id, course_id, student_id))
            if row is None:
                row = CourseStudent(
                    user_id=user_id, course_id=course_id, student_id=student_id
                )
                db.add(row)
            row.full_name = raw_student.get("fullName") or row.full_name or student_id
            row.email = raw_student.get("emailAddress")
            row.photo_url = raw_student.get("photoUrl")
        for stale in (
            db.query(CourseStudent)
            .filter_by(user_id=user_id, course_id=course_id)
            .all()
        ):
            if stale.student_id not in student_ids:
                db.delete(stale)

    submissions = payload.get("submissions")
    if submissions is not None:
        seen: set[tuple[str, str]] = set()
        for raw_sub in submissions:
            work_id = raw_sub.get("courseWorkId")
            student_id = raw_sub.get("userId")
            if not work_id or not student_id:
                continue
            seen.add((work_id, student_id))
            row = db.get(
                CourseWorkSubmission, (user_id, course_id, work_id, student_id)
            )
            if row is None:
                row = CourseWorkSubmission(
                    user_id=user_id,
                    course_id=course_id,
                    coursework_id=work_id,
                    student_id=student_id,
                )
                db.add(row)
            row.state = raw_sub.get("state")
            row.late = bool(raw_sub.get("late"))
            row.assigned_points = _parse_points(raw_sub.get("assignedGrade"))
            row.draft_points = _parse_points(raw_sub.get("draftGrade"))
            row.submitted_at = _submitted_at(raw_sub)
            row.updated_time = parse_rfc3339(raw_sub.get("updateTime"))
            row.attachments = _submission_attachments(raw_sub)
        for stale in (
            db.query(CourseWorkSubmission)
            .filter_by(user_id=user_id, course_id=course_id)
            .all()
        ):
            if (stale.coursework_id, stale.student_id) not in seen:
                db.delete(stale)
    return count
