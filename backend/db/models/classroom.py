"""Classroom cache schema, user-scoped (migration stage 3).

Every cache row belongs to one local application user (``users.id``,
models_auth.py): two Google accounts can both see the same Classroom course
with the same Google course id, so no cache table may assume global
uniqueness of Google ids (migration prompt §10, audit M1/M2). Every primary
key therefore starts with ``user_id``, and every uniqueness guarantee is
scoped to it:

    (user_id, provider_course_id)                        courses
    (user_id, provider_coursework_id)                    coursework
    (user_id, course_id, coursework_id)                  submissions
    (user_id, course_id, coursework_id, student_id)      coursework_submissions

The Google ids themselves are kept as the remaining key columns (``id`` /
``course_id`` / ``coursework_id``): they are what the Classroom API round
trips and what the API surface speaks, so upserts keep working by primary
key exactly as before (ADR-0003) — only now within one user's scope.

Child tables link to their parents with composite foreign keys
``(user_id, parent_id) → parent(user_id, id)`` with ON DELETE CASCADE:
deleting a course row removes exactly that user's coursework, roles,
roster and submissions with it, and deleting a user removes their whole
cache. ``JSON``/``Boolean``/``DateTime`` are generic SQLAlchemy types so the
same models serve the desktop SQLite build and the hosted PostgreSQL
database (migration stage 3, §69/§71).
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Course(Base):
    """One Classroom course cached for one user.

    The Google course id (``id``) is unique per user, not globally: two
    teachers/students in the same course must never collide or share rows
    (audit M2).
    """

    __tablename__ = "courses"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Google Classroom course id, unique within one user's cache.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    section: Mapped[str | None] = mapped_column(String, nullable=True)
    room: Mapped[str | None] = mapped_column(String, nullable=True)
    enrollment_state: Mapped[str | None] = mapped_column(String, nullable=True)
    course_state: Mapped[str | None] = mapped_column(String, nullable=True)
    teacher_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Set by _do_sync on every sync; no default — a stale value would lie.
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CourseWork(Base):
    __tablename__ = "coursework"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
        # Query pattern: all coursework of one course (api.py, sync_store).
        Index("ix_coursework_user_course", "user_id", "course_id"),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Google Classroom coursework id, unique within one user's cache.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    course_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    work_type: Mapped[str | None] = mapped_column(String, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    max_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    alternate_link: Mapped[str | None] = mapped_column(String, nullable=True)
    materials: Mapped[list] = mapped_column(JSON, default=list)
    topic_id: Mapped[str | None] = mapped_column(String, nullable=True)
    creation_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StudentSubmission(Base):
    """The user's own submission for one coursework item (student route).

    Primary key (user_id, course_id, coursework_id): one submission per
    assignment per user — another user's row for the same Google ids is
    their own fact, never shared (audit M3).
    """

    __tablename__ = "submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "coursework_id"],
            ["coursework.user_id", "coursework.id"],
            ondelete="CASCADE",
        ),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[str] = mapped_column(String, primary_key=True)
    coursework_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    draft_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CourseRole(Base):
    """Role of the cache owner in a course: "TEACHER" or "STUDENT".

    Per course, because one account can teach some courses and study in
    others (ADR-0017). Scoped by ``user_id`` like every cache table; the
    row belongs to the user whose role it describes.
    """

    __tablename__ = "course_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[str] = mapped_column(String, primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="STUDENT")


class CourseStudent(Base):
    """Roster of a teacher's course (courses.students.list).

    Only populated for courses where the cache owner is a teacher; the
    student route never needs a roster. ``student_id`` is the Google user
    id of the enrolled student (renamed from ``user_id`` in stage 3: the
    owner column is ``user_id`` everywhere, audit M5).
    """

    __tablename__ = "course_students"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[str] = mapped_column(String, primary_key=True)
    student_id: Mapped[str] = mapped_column(String, primary_key=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)


class CourseWorkSubmission(Base):
    """One student's submission for one coursework item.

    Separate from :class:`StudentSubmission` (the cache owner's own
    submission, discovered through the student route). Teacher courses have
    many submissions per assignment, so the primary key includes the
    student. All four key columns are user-scoped: the same Google
    (course, coursework, student) ids may appear for several cache owners.
    """

    __tablename__ = "coursework_submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "coursework_id"],
            ["coursework.user_id", "coursework.id"],
            ondelete="CASCADE",
        ),
        # Query pattern: all submissions of one course (api.py grade views).
        Index("ix_cw_submission_user_course", "user_id", "course_id"),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[str] = mapped_column(String, primary_key=True)
    coursework_id: Mapped[str] = mapped_column(String, primary_key=True)
    student_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    draft_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attachments: Mapped[list] = mapped_column(JSON, default=list)


class SyncStatus(Base):
    """Structured synchronization state of one user (migration stage 5, §18).

    Replaces the key/value ``sync_state`` table (audit M4) with one row per
    user holding the fields the scheduler actually needs:

        pending  — never synced, or not signed in to Google;
        running  — a sync job currently holds this user;
        ok       — the last finished run succeeded;
        error    — the last run failed (retryable; backoff is applied);
        needs_reauth — the Google grant is unusable, scheduling is paused
                   until the next sign-in.

    The ``running`` value doubles as the cross-process claim: a conditional
    UPDATE flips it only when the previous run is not still in flight, so
    several worker containers can scan simultaneously without submitting
    the same user twice (stale rows older than the configured claim window
    are treated as a crashed worker and may be re-claimed).

    ``last_error`` holds a SHORT, user-facing sentence only — never an
    exception trace, an HTTP response body or token material (§18); the
    full stack trace stays in the server log.

    Timestamps are naive UTC, the convention of every user-scoped table in
    this schema (users/sessions/oauth_tokens), so the scheduler's due
    arithmetic never mixes clocks.
    """

    __tablename__ = "sync_status"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # One of "pending"/"running"/"ok"/"error"/"needs_reauth".
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Set only by a successful run; what the dashboard shows as "last sync".
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Drives the retry backoff and stops a permanently broken grant from
    # being retried on every scan ("avoid retry storms", §63).
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # "Sync this user as soon as possible": set right after a successful
    # sign-in, cleared when the job claims the user. A flag (not a
    # timestamp) precisely because the sign-in happens in the web process
    # and the job in the worker container — a flag needs no shared clock.
    sync_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
