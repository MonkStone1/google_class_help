"""Cache write layer: everything that writes Classroom data into SQLite
(review §2.2). Reads happen in api.py, orchestration in sync_service.py;
this module knows the tables and the shapes Google sends, nothing else.
"""

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from classroom_api import parse_date_time, parse_rfc3339
from models import (
    Course,
    CourseRole,
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
    StudentSubmission,
    SyncState,
)

SubmissionRow = CourseWorkSubmission | StudentSubmission


# ------------------------------------------------------------- sync_state


def _set_state(db: Session, key: str, value: str | None) -> None:
    row = db.get(SyncState, key)
    if row is None:
        row = SyncState(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()


def get_state(db: Session, key: str) -> str | None:
    row = db.get(SyncState, key)
    return row.value if row else None


def get_state_datetime(db: Session, key: str) -> datetime | None:
    raw = get_state(db, key)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


# ------------------------------------------------------- unified access §2.3


def get_submission(
    db: Session,
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
    picks the table here, so callers never branch on it themselves.
    """
    if is_teacher:
        return db.get(CourseWorkSubmission, (course_id, coursework_id, student_id))
    return db.get(StudentSubmission, (course_id, coursework_id))


# ------------------------------------------------------------------ purging


def _purge_course(db: Session, course_id: str) -> None:
    """Remove a course and its cached rows (used for archived/gone courses).

    SQLite runs with PRAGMA foreign_keys=ON (database.py), so the
    ondelete=CASCADE rules on every child table do the work — one delete
    instead of five hand-written ones (review §1.6).
    """
    stale = db.get(Course, course_id)
    if stale is None:
        return
    # A parameterized delete() statement, not an ORM instance delete: with
    # PRAGMA foreign_keys=ON the DB cascades every child row itself.
    db.execute(delete(Course).where(Course.id == course_id))
    db.commit()


def _purge_stale_courses(db: Session, active_ids: set[str]) -> None:
    """Remove cached courses the Classroom API no longer returns.

    Covers ARCHIVED courses as well as courses the user left (unenrolled) or
    that were deleted in Google. The API list call has already succeeded at
    this point, so a missing id is authoritative rather than an error.
    """
    cached_ids = [row[0] for row in db.query(Course.id).all()]
    for course_id in cached_ids:
        if course_id not in active_ids:
            _purge_course(db, course_id)


def reset_cache(db: Session) -> None:
    """Delete all cached Classroom data (destructive, user-confirmed)."""
    for table in (
        CourseWorkSubmission,
        CourseStudent,
        CourseRole,
        StudentSubmission,
        CourseWork,
        Course,
        SyncState,
    ):
        db.execute(delete(table))
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


def _upsert_work(db: Session, course_id: str, raw_work: dict) -> None:
    """Insert/update one coursework row from a raw Classroom object."""
    work_id = raw_work.get("id")
    if not work_id:
        return
    work = db.get(CourseWork, work_id)
    if work is None:
        work = CourseWork(id=work_id, course_id=course_id)
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
        _upsert_work(db, course_id, raw_work)
        count += 1

        sub = db.get(StudentSubmission, (course_id, work_id))
        if sub is None:
            sub = StudentSubmission(course_id=course_id, coursework_id=work_id)
            db.add(sub)
        sub.state = raw_sub.get("state")
        sub.late = bool(raw_sub.get("late"))
        sub.assigned_points = _parse_points(raw_sub.get("assignedGrade"))
        sub.draft_points = _parse_points(raw_sub.get("draftGrade"))
        sub.updated_time = parse_rfc3339(raw_sub.get("updateTime"))
    return count


def _write_teacher_course(db: Session, course_id: str, payload: dict) -> int:
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
            _upsert_work(db, course_id, raw_work)
            count += 1
        for stale in db.query(CourseWork).filter_by(course_id=course_id).all():
            if stale.id not in work_ids:
                db.query(CourseWorkSubmission).filter_by(
                    course_id=course_id, coursework_id=stale.id
                ).delete(synchronize_session=False)
                db.delete(stale)

    students = payload.get("students")
    if students is not None:
        student_ids = set()
        for raw_student in students:
            student_id = raw_student.get("userId")
            if not student_id:
                continue
            student_ids.add(student_id)
            row = db.get(CourseStudent, (course_id, student_id))
            if row is None:
                row = CourseStudent(course_id=course_id, user_id=student_id)
                db.add(row)
            row.full_name = raw_student.get("fullName") or row.full_name or student_id
            row.email = raw_student.get("emailAddress")
            row.photo_url = raw_student.get("photoUrl")
        for stale in db.query(CourseStudent).filter_by(course_id=course_id).all():
            if stale.user_id not in student_ids:
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
            row = db.get(CourseWorkSubmission, (course_id, work_id, student_id))
            if row is None:
                row = CourseWorkSubmission(
                    course_id=course_id, coursework_id=work_id, student_id=student_id
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
            db.query(CourseWorkSubmission).filter_by(course_id=course_id).all()
        ):
            if (stale.coursework_id, stale.student_id) not in seen:
                db.delete(stale)
    return count
