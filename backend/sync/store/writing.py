"""The upsert layer: the shapes Google sends become cache rows (ADR-0039 split).

This is the only module that knows both dialects. ``upsert_submission`` builds
``INSERT ... ON CONFLICT DO UPDATE`` per dialect instead of a read-modify-write,
because a read-modify-write under the hosted concurrency target loses writes
whenever two jobs touch the same submission.

The private ``_write_*_course`` functions are the two entry points the sync
service calls; everything above them translates a Google payload, and
everything below them is SQL. Keeping the translation separate from the SQL is
what makes a new field a change to one function rather than to three.
"""

import logging
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from db.models.classroom import (
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
    StudentSubmission,
)
from gapi.classroom import parse_date_time, parse_rfc3339

logger = logging.getLogger(__name__)

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
    """Insert/update one coursework row from a raw Classroom object.

    A conditional write for the same reason as :func:`upsert_submission`: two
    runs of the same user's sync overlap inside the write phase, and plain
    get-then-add let both of them INSERT the same coursework id.
    """
    work_id = raw_work.get("id")
    if not work_id:
        return
    upsert_submission(
        db,
        CourseWork,
        {"user_id": user_id, "id": work_id},
        {
            "course_id": course_id,
            "title": raw_work.get("title", "Untitled assignment"),
            "description": raw_work.get("description"),
            "state": raw_work.get("state"),
            "work_type": raw_work.get("workType"),
            "due_at": parse_date_time(raw_work.get("dueDate"), raw_work.get("dueTime")),
            "max_points": raw_work.get("maxPoints"),
            "alternate_link": raw_work.get("alternateLink"),
            "topic_id": raw_work.get("topicId"),
            "creation_time": parse_rfc3339(raw_work.get("creationTime")),
            "updated_time": parse_rfc3339(raw_work.get("updateTime")),
            "materials": _materials_to_json(raw_work.get("materials", [])),
        },
    )


def _upsert_insert(dialect_name: str):
    """The ``INSERT`` construct for a dialect, with conflict support.

    ``INSERT ... ON CONFLICT DO UPDATE`` is spelled per backend and the app runs
    on both (SQLite for the desktop cache, PostgreSQL for the hosted service,
    database.py §69), so the construct is picked from the live connection rather
    than hardcoded. Both dialects have supported the clause for years
    (SQLite 3.24, 2018), so no minimum-version gate is needed.
    """
    if dialect_name == "postgresql":
        return pg_insert
    return sqlite_insert


def upsert_submission(db: Session, model, key: dict, values: dict) -> None:
    """Insert one cache row, or update it when that primary key already exists.

    The idempotent write every sync needs, and the fix for the teacher-sync
    ``UniqueViolation`` on ``coursework_submissions_pkey``: a submission that is
    already cached must be UPDATED with its current state, not re-INSERTed.

    Why the old ``db.get(...) is None`` dance was not enough, even though it
    looks idempotent: it is only idempotent while ONE writer touches the cache.
    ADR-0032 lets a second run take a stale claim over, and a restart releases
    the claim while the superseded run is still inside its write phase — that
    run is fenced once, before a per-course commit loop that can run for
    minutes on a teacher account. In that window both runs hold the same
    (user_id, course_id, coursework_id, student_id), both ``get`` calls return
    None, both INSERT, and the loser aborts the whole transaction with a unique
    violation the user sees as "Sync failed". The conditional write makes the
    loser's statement an UPDATE, so the overlap costs nothing and the
    cache-write stays idempotent no matter how many runs touch it.

    ``model`` is any of the user-scoped cache tables; ``key`` must name the
    full primary key and ``values`` the columns to write. JSON columns take
    their values as Python objects — the bind processor serializes them, the
    same way the ORM path did.
    """
    stmt = _upsert_insert(db.get_bind().dialect.name)(model).values(**key, **values)
    excluded = stmt.excluded
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=list(key),
            set_={name: getattr(excluded, name) for name in values},
        )
    )


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

        upsert_submission(
            db,
            StudentSubmission,
            {"user_id": user_id, "course_id": course_id, "coursework_id": work_id},
            {
                "state": raw_sub.get("state"),
                "late": bool(raw_sub.get("late")),
                "assigned_points": _parse_points(raw_sub.get("assignedGrade")),
                "draft_points": _parse_points(raw_sub.get("draftGrade")),
                "updated_time": parse_rfc3339(raw_sub.get("updateTime")),
            },
        )
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
            upsert_submission(
                db,
                CourseStudent,
                {
                    "user_id": user_id,
                    "course_id": course_id,
                    "student_id": student_id,
                },
                {
                    "full_name": raw_student.get("fullName") or student_id,
                    "email": raw_student.get("emailAddress"),
                    "photo_url": raw_student.get("photoUrl"),
                },
            )
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
            # The conditional write is the fix for the teacher-sync
            # "duplicate key value violates unique constraint
            # coursework_submissions_pkey" failure: a submission that is already
            # cached is updated with its current state instead of being inserted
            # a second time, so a repeated sync of the same course and students
            # stays conflict-free (see upsert_submission for the race).
            upsert_submission(
                db,
                CourseWorkSubmission,
                {
                    "user_id": user_id,
                    "course_id": course_id,
                    "coursework_id": work_id,
                    "student_id": student_id,
                },
                {
                    "state": raw_sub.get("state"),
                    "late": bool(raw_sub.get("late")),
                    "assigned_points": _parse_points(raw_sub.get("assignedGrade")),
                    "draft_points": _parse_points(raw_sub.get("draftGrade")),
                    "submitted_at": _submitted_at(raw_sub),
                    "updated_time": parse_rfc3339(raw_sub.get("updateTime")),
                    "attachments": _submission_attachments(raw_sub),
                },
            )
        for stale in (
            db.query(CourseWorkSubmission)
            .filter_by(user_id=user_id, course_id=course_id)
            .all()
        ):
            if (stale.coursework_id, stale.student_id) not in seen:
                db.delete(stale)
    return count
