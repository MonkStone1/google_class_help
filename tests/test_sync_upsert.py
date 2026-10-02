"""Idempotent cache writes for teacher and student courses.

A teacher sync used to abort with ``duplicate key value violates unique
constraint "coursework_submissions_pkey"``: the data arrived from Google
perfectly, and the write phase then tried to INSERT a submission that was
already cached. These tests pin the conditional write that replaced it, and
the surrounding behaviour that must not regress:

- re-running a sync over the same course and students is conflict-free and
  leaves exactly one row per (course, coursework, student);
- the repeated write UPDATES the current facts (state, late, grades,
  submitted_at, updated_time, attachments) instead of keeping stale ones;
- the ordinary STUDENT route keeps working exactly as before;
- the mirror cleanup still removes submissions and roster entries Classroom no
  longer returns, so an upsert never turns into "we keep everything forever".
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, insert, select

from db.models.classroom import (
    Course,
    CourseRole,
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
    StudentSubmission,
)
from db.session import SessionLocal
from sync import store
from sync.store import writing


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_course(db, owner_id: int, course_id: str, role: str = "TEACHER") -> None:
    db.add(Course(user_id=owner_id, id=course_id, name=f"Course {course_id}"))
    db.add(CourseRole(user_id=owner_id, course_id=course_id, role=role))
    db.commit()


def _submission(
    work_id: str,
    student_id: str,
    *,
    state: str = "TURNED_IN",
    late: bool = False,
    assigned: float | None = None,
    draft: float | None = None,
    updated: str = "2026-01-01T10:00:00Z",
    attachment: str | None = None,
) -> dict:
    raw: dict = {
        "courseWorkId": work_id,
        "userId": student_id,
        "state": state,
        "late": late,
        "assignedGrade": assigned,
        "draftGrade": draft,
        "updateTime": updated,
        "submissionHistory": [
            {
                "stateHistory": {
                    "state": "TURNED_IN",
                    "stateTimestamp": "2026-01-01T09:00:00Z",
                }
            }
        ],
    }
    if attachment is not None:
        raw["assignmentSubmission"] = {
            "attachments": [
                {"link": {"title": attachment, "url": "https://example.test/link"}}
            ]
        }
    return raw


def _teacher_payload(
    submissions: list[dict], coursework: list[dict] | None = None
) -> dict:
    return {
        "coursework": coursework
        if coursework is not None
        else [{"id": "w1", "title": "HW"}],
        "students": [{"userId": "s1", "fullName": "Ann", "emailAddress": "ann@x.test"}],
        "submissions": submissions,
    }


def _count(db, model, owner_id: int, course_id: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(model)
        .where(model.user_id == owner_id, model.course_id == course_id)
    ).scalar_one()


# ---------------------------------------------------- the reported failure


def test_repeated_teacher_sync_does_not_raise_and_keeps_one_row(db, owner_id):
    """The reported crash: syncing the same course twice must not conflict."""
    _seed_course(db, owner_id, "t1")
    payload = _teacher_payload([_submission("w1", "s1", assigned=5)])

    for _ in range(3):
        writing._write_teacher_course(db, owner_id, "t1", payload)
        db.commit()

    assert _count(db, CourseWorkSubmission, owner_id, "t1") == 1


def test_existing_submission_is_updated_not_duplicated(db, owner_id):
    """A second sync must refresh the facts the teacher can see change."""
    _seed_course(db, owner_id, "t1")
    first = _teacher_payload(
        [_submission("w1", "s1", state="CREATED", assigned=None, attachment="draft")]
    )
    writing._write_teacher_course(db, owner_id, "t1", first)
    db.commit()

    graded = _teacher_payload(
        [
            _submission(
                "w1",
                "s1",
                state="RETURNED",
                late=True,
                assigned=42.0,
                draft=40.0,
                updated="2026-02-02T11:30:00Z",
                attachment="final",
            )
        ]
    )
    writing._write_teacher_course(db, owner_id, "t1", graded)
    db.commit()

    row = db.get(CourseWorkSubmission, (owner_id, "t1", "w1", "s1"))
    assert row is not None
    assert row.state == "RETURNED"
    assert row.late is True
    assert row.assigned_points == 42.0
    assert row.draft_points == 40.0
    # Timestamps are naive UTC everywhere in this schema (ADR-0004).
    assert row.updated_time == datetime.fromisoformat("2026-02-02T11:30:00")
    assert row.submitted_at == datetime.fromisoformat("2026-01-01T09:00:00")
    assert [a["title"] for a in row.attachments] == ["final"]


def test_many_students_and_courseworks_stay_one_row_each(db, owner_id):
    """The shape that actually blew up: a real teacher roster, synced twice."""
    _seed_course(db, owner_id, "t1")
    works = [{"id": f"w{i}", "title": f"Task {i}"} for i in range(1, 6)]
    roster = [{"userId": f"s{i}", "fullName": f"Student {i}"} for i in range(1, 21)]
    submissions = [
        _submission(f"w{w}", f"s{s}", assigned=float(s))
        for w in range(1, 6)
        for s in range(1, 21)
    ]
    payload = {"coursework": works, "students": roster, "submissions": submissions}

    for _ in range(2):
        writing._write_teacher_course(db, owner_id, "t1", payload)
        db.commit()

    assert _count(db, CourseWorkSubmission, owner_id, "t1") == 5 * 20
    assert _count(db, CourseStudent, owner_id, "t1") == 20
    assert _count(db, CourseWork, owner_id, "t1") == 5


def test_submission_is_rewritten_when_the_key_already_exists(db, owner_id):
    """A submission present in the cache must be rewritten, not duplicated.

    The same-key collision the conditional write makes harmless: whatever wrote
    that row first — an earlier sync, or another run overlapping this one — the
    second write updates the same row and leaves the fresh facts in place.
    """
    _seed_course(db, owner_id, "t1")
    writing._upsert_work(db, owner_id, "t1", {"id": "w1", "title": "HW"})
    # Committed before the second writer: an uncommitted write here would pin the
    # SQLite file lock and the other session would fail with "database is locked".
    db.commit()
    with SessionLocal() as other:
        other.execute(
            insert(CourseWorkSubmission).values(
                user_id=owner_id,
                course_id="t1",
                coursework_id="w1",
                student_id="s1",
                state="CREATED",
                late=False,
                assigned_points=None,
                draft_points=None,
                submitted_at=None,
                updated_time=None,
                attachments=[],
            )
        )
        other.commit()

    writing._write_teacher_course(
        db, owner_id, "t1", _teacher_payload([_submission("w1", "s1", assigned=5)])
    )
    db.commit()

    row = db.get(CourseWorkSubmission, (owner_id, "t1", "w1", "s1"))
    assert row is not None
    assert row.state == "TURNED_IN"
    assert row.assigned_points == 5.0
    assert _count(db, CourseWorkSubmission, owner_id, "t1") == 1


# ------------------------------------------------------- coursework and roster


def test_coursework_and_roster_are_updated_in_place(db, owner_id):
    _seed_course(db, owner_id, "t1")
    writing._write_teacher_course(
        db,
        owner_id,
        "t1",
        _teacher_payload(
            [_submission("w1", "s1")],
            coursework=[{"id": "w1", "title": "Draft title", "state": "DRAFT"}],
        ),
    )
    db.commit()

    writing._write_teacher_course(
        db,
        owner_id,
        "t1",
        _teacher_payload(
            [_submission("w1", "s1")],
            coursework=[{"id": "w1", "title": "Final title", "state": "PUBLISHED"}],
        ),
    )
    db.commit()

    work = db.get(CourseWork, (owner_id, "w1"))
    assert work is not None
    assert work.title == "Final title"
    assert work.state == "PUBLISHED"
    assert _count(db, CourseWork, owner_id, "t1") == 1


def test_roster_entry_is_refreshed(db, owner_id):
    _seed_course(db, owner_id, "t1")
    writing._write_teacher_course(db, owner_id, "t1", _teacher_payload([]))
    db.commit()

    renamed = _teacher_payload([])
    renamed["students"] = [
        {"userId": "s1", "fullName": "Anna Nowak", "emailAddress": "new@x.test"}
    ]
    writing._write_teacher_course(db, owner_id, "t1", renamed)
    db.commit()

    row = db.get(CourseStudent, (owner_id, "t1", "s1"))
    assert row is not None
    assert row.full_name == "Anna Nowak"
    assert row.email == "new@x.test"
    assert _count(db, CourseStudent, owner_id, "t1") == 1


# ------------------------------------------------- mirror cleanup stays intact


def test_submissions_classroom_dropped_are_still_removed(db, owner_id):
    """An upsert must not become "keep everything": the mirror still converges."""
    _seed_course(db, owner_id, "t1")
    writing._write_teacher_course(
        db,
        owner_id,
        "t1",
        _teacher_payload([_submission("w1", "s1"), _submission("w1", "s2")]),
    )
    db.commit()
    assert _count(db, CourseWorkSubmission, owner_id, "t1") == 2

    writing._write_teacher_course(
        db, owner_id, "t1", _teacher_payload([_submission("w1", "s1")])
    )
    db.commit()

    assert _count(db, CourseWorkSubmission, owner_id, "t1") == 1
    assert db.get(CourseWorkSubmission, (owner_id, "t1", "w1", "s2")) is None


def test_students_unenrolled_are_still_removed(db, owner_id):
    _seed_course(db, owner_id, "t1")
    both = _teacher_payload([])
    both["students"] = [
        {"userId": "s1", "fullName": "A"},
        {"userId": "s2", "fullName": "B"},
    ]
    writing._write_teacher_course(db, owner_id, "t1", both)
    db.commit()

    one = _teacher_payload([])
    one["students"] = [{"userId": "s1", "fullName": "A"}]
    writing._write_teacher_course(db, owner_id, "t1", one)
    db.commit()

    assert _count(db, CourseStudent, owner_id, "t1") == 1


# ---------------------------------------------------- the student route intact


def test_student_course_sync_is_idempotent(db, owner_id):
    """The ordinary student path must keep working — same rows, no duplicates."""
    _seed_course(db, owner_id, "s-course", role="STUDENT")
    raw_work = {"id": "w1", "title": "Problem set", "state": "PUBLISHED"}
    submissions = [
        {
            "courseWorkId": "w1",
            "state": "TURNED_IN",
            "late": False,
            "assignedGrade": 7.5,
            "draftGrade": 7.0,
            "updateTime": "2026-01-01T10:00:00Z",
        }
    ]
    work_cache = {("s-course", "w1"): raw_work}

    for _ in range(2):
        count = writing._write_student_course(
            db, owner_id, "s-course", submissions, work_cache
        )
        db.commit()
        assert count == 1

    assert _count(db, StudentSubmission, owner_id, "s-course") == 1
    row = db.get(StudentSubmission, (owner_id, "s-course", "w1"))
    assert row is not None
    assert row.state == "TURNED_IN"
    assert row.assigned_points == 7.5
    assert row.draft_points == 7.0
    assert _count(db, CourseWork, owner_id, "s-course") == 1


def test_student_submission_grade_change_is_persisted(db, owner_id):
    _seed_course(db, owner_id, "s-course", role="STUDENT")
    work_cache = {("s-course", "w1"): {"id": "w1", "title": "PS"}}

    def _sub(grade):
        return {
            "courseWorkId": "w1",
            "state": "RETURNED" if grade is not None else "TURNED_IN",
            "late": grade is None,
            "assignedGrade": grade,
            "updateTime": "2026-01-01T10:00:00Z",
        }

    writing._write_student_course(
        db, owner_id, "s-course", [_sub(None)], work_cache
    )
    db.commit()
    writing._write_student_course(db, owner_id, "s-course", [_sub(9.0)], work_cache)
    db.commit()

    row = db.get(StudentSubmission, (owner_id, "s-course", "w1"))
    assert row is not None
    assert row.state == "RETURNED"
    assert row.assigned_points == 9.0
    assert _count(db, StudentSubmission, owner_id, "s-course") == 1


# ------------------------------------------------------------- user isolation


def test_two_users_caching_the_same_google_ids_do_not_collide(db, owner_id):
    """The PK is user-scoped on purpose: identical Google ids, separate rows."""
    from db.models.accounts import User

    other = User(
        provider="google",
        provider_subject="teacher-two",
        email="two@example.test",
        display_name="Two",
        created_at=_now(),
        updated_at=_now(),
        is_active=True,
    )
    db.add(other)
    db.commit()
    other_id = other.id

    _seed_course(db, owner_id, "shared")
    _seed_course(db, other_id, "shared")
    payload = _teacher_payload([_submission("w1", "s1", assigned=5)])

    writing._write_teacher_course(db, owner_id, "shared", payload)
    writing._write_teacher_course(db, other_id, "shared", payload)
    db.commit()

    assert _count(db, CourseWorkSubmission, owner_id, "shared") == 1
    assert _count(db, CourseWorkSubmission, other_id, "shared") == 1


def test_course_row_is_upserted_by_key(db, owner_id):
    """The course row itself goes through the same conditional write."""
    _seed_course(db, owner_id, "t1")
    first = _now()
    store.upsert_submission(
        db,
        Course,
        {"user_id": owner_id, "id": "t1"},
        {"name": "Renamed", "teacher_names": ["Ms Bell"], "synced_at": first},
    )
    db.commit()
    second = _now()
    store.upsert_submission(
        db,
        Course,
        {"user_id": owner_id, "id": "t1"},
        {"name": "Renamed again", "teacher_names": ["Mr Kay"], "synced_at": second},
    )
    db.commit()

    row = db.get(Course, (owner_id, "t1"))
    assert row is not None
    assert row.name == "Renamed again"
    assert row.teacher_names == ["Mr Kay"]
    assert row.synced_at == second
    assert (
        db.execute(
            select(func.count()).select_from(Course).where(Course.user_id == owner_id)
        ).scalar_one()
        == 1
    )


# ---------------------------------------------------------- both SQL backends


def test_upsert_builds_on_conflict_for_both_backends():
    """The app runs on SQLite (desktop) and PostgreSQL (hosted) — pin both.

    Not a database test: it checks that the helper really produces the
    dialect-specific conflict clause, which is the part that would otherwise
    only ever fail on the hosted deployment nobody exercises locally.
    """
    from sqlalchemy.dialects import postgresql, sqlite

    for dialect_name, dialect in (
        ("postgresql", postgresql.dialect()),
        ("sqlite", sqlite.dialect()),
    ):
        insert = writing._upsert_insert(dialect_name)
        stmt = insert(CourseWorkSubmission).values(
            user_id=1,
            course_id="c",
            coursework_id="w",
            student_id="s",
            state="RETURNED",
        )
        compiled = stmt.on_conflict_do_update(
            index_elements=["user_id", "course_id", "coursework_id", "student_id"],
            set_={"state": stmt.excluded.state},
        ).compile(dialect=dialect)
        sql = str(compiled)
        assert "ON CONFLICT" in sql, dialect_name
        assert "excluded.state" in sql, dialect_name
        # Bind values live in the compiled params, not in the SQL text.
        assert "RETURNED" in repr(compiled.params), dialect_name
