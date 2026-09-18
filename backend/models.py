from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Course(Base):
    __tablename__ = "courses"

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

    id: Mapped[str] = mapped_column(String, primary_key=True)
    course_id: Mapped[str] = mapped_column(
        String, ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
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
    __tablename__ = "submissions"

    course_id: Mapped[str] = mapped_column(
        String, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    coursework_id: Mapped[str] = mapped_column(
        String, ForeignKey("coursework.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    draft_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CourseRole(Base):
    """Role of the authenticated user in a course: "TEACHER" or "STUDENT".

    Per course, because one account can teach some courses and study in
    others. Kept in its own table rather than a column on ``courses`` so an
    existing cache file keeps working without a manual SQLite migration:
    new tables are created by ``create_all``, new columns are not (ADR-0003).
    """

    __tablename__ = "course_roles"

    course_id: Mapped[str] = mapped_column(
        String, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False, default="STUDENT")


class CourseStudent(Base):
    """Roster of a teacher's course (courses.students.list).

    Only populated for courses where the authenticated user is a teacher;
    the student route never needs a roster.
    """

    __tablename__ = "course_students"

    course_id: Mapped[str] = mapped_column(
        String, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)


class CourseWorkSubmission(Base):
    """One student's submission for one coursework item.

    Separate from :class:`StudentSubmission` (the authenticated user's own
    submission, discovered through the student route). Teacher courses have
    many submissions per assignment, so the primary key includes the student.
    """

    __tablename__ = "coursework_submissions"

    course_id: Mapped[str] = mapped_column(
        String, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    coursework_id: Mapped[str] = mapped_column(
        String, ForeignKey("coursework.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    draft_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attachments: Mapped[list] = mapped_column(JSON, default=list)


class SyncState(Base):
    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(String, nullable=True)
