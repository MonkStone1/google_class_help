# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Teacher mode and the API surface (migration stage 6, §21–§24).

The invariants under test:

- §21: teacher mode is a per-course role; a teacher-only view requires BOTH
  an authenticated user and ``role == TEACHER``, and a student course never
  exposes a roster;
- §22: business semantics survive the migration — a missing grade is not 0,
  teacher aggregates are not the teacher's own submission, archived courses
  stay hidden, submission states and percentages stay consistent;
- §23: 403 for an authenticated user without the course role, 404 for a
  resource outside the caller's scope (never disclosing another user's row);
- §24: ``/api/auth/status`` and ``/api/me`` describe the current
  application session and carry no OAuth material.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import hosted_auth
import ownership
from models import (
    Course,
    CourseRole,
    CourseStudent,
    CourseWork,
    CourseWorkSubmission,
)
from models_auth import User, UserSession


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_user(db: Session, subject: str, name: str) -> User:
    user = User(
        provider="google",
        provider_subject=subject,
        email=f"{subject}@example.com",
        display_name=name,
        created_at=_now(),
        updated_at=_now(),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _add_session(db: Session, user: User, raw_token: str) -> None:
    now = _now()
    db.add(
        UserSession(
            session_token_hash=hosted_auth._sha256_hex(raw_token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(days=1),
            last_seen_at=now,
        )
    )
    db.commit()


@pytest.fixture()
def teacher_course(db, owner_id):
    """A teacher course with one roster student who turned work in ungraded."""
    db.add(Course(user_id=owner_id, id="t1", name="Physics", course_state="ACTIVE"))
    db.add(CourseRole(user_id=owner_id, course_id="t1", role="TEACHER"))
    db.add(
        CourseWork(
            user_id=owner_id,
            id="tw1",
            course_id="t1",
            title="Lab",
            max_points=100,
            state="PUBLISHED",
        )
    )
    db.add(
        CourseStudent(
            user_id=owner_id,
            course_id="t1",
            student_id="s1",
            full_name="Sam Student",
            email="sam@example.com",
        )
    )
    # TURNED_IN with no assigned grade: must stay "not graded", never 0.
    db.add(
        CourseWorkSubmission(
            user_id=owner_id,
            course_id="t1",
            coursework_id="tw1",
            student_id="s1",
            state="TURNED_IN",
            assigned_points=None,
        )
    )
    db.commit()


@pytest.fixture()
def student_course(db, owner_id):
    db.add(Course(user_id=owner_id, id="c1", name="Math", course_state="ACTIVE"))
    db.add(CourseRole(user_id=owner_id, course_id="c1", role="STUDENT"))
    db.add(
        CourseWork(
            user_id=owner_id,
            id="w1",
            course_id="c1",
            title="Quiz",
            max_points=50,
            state="PUBLISHED",
        )
    )
    # Leftover roster from a former teaching period: must not surface.
    db.add(
        CourseStudent(
            user_id=owner_id,
            course_id="c1",
            student_id="leftover",
            full_name="Left Over",
        )
    )
    db.commit()


# ------------------------------------------------------------ §21 role gates


def test_teacher_only_endpoints_reject_the_student_role(client, student_course):
    assert client.get("/api/courses/c1/students").status_code == 403
    assert client.get("/api/courses/c1/grades").status_code == 403


def test_course_detail_hides_the_roster_for_a_student(client, student_course):
    body = client.get("/api/courses/c1").json()
    assert body["role"] == "STUDENT"
    assert body["students"] == []


def test_course_detail_exposes_the_roster_to_the_teacher(client, teacher_course):
    body = client.get("/api/courses/t1").json()
    assert body["role"] == "TEACHER"
    assert [student["id"] for student in body["students"]] == ["s1"]


# --------------------------------------------------------- §22 the semantics


def test_missing_grade_is_not_zero(client, teacher_course):
    """§22: an ungraded TURNED_IN submission keeps points/percent empty."""
    matrix = client.get("/api/courses/t1/grades").json()
    cell = matrix["rows"][0]["cells"][0]
    assert cell["status"] == "turned_in"
    assert cell["submitted"] is True
    assert cell["graded"] is False
    assert cell["points"] is None
    assert cell["percent"] is None
    # A missing grade contributes nothing to the class average.
    assert matrix["class_average"] is None

    detail = client.get("/api/courses/t1/coursework/tw1").json()
    submission = detail["submissions"][0]
    assert submission["points"] is None
    assert submission["percent"] is None
    assert detail["status_counts"] == {"turned_in": 1}


def test_teacher_aggregates_are_not_the_teachers_own_submission(client, teacher_course):
    """§22: the teacher is not a student in their own course."""
    coursework = client.get("/api/courses/t1/coursework").json()
    assert len(coursework) == 1
    work = coursework[0]
    assert work["role"] == "TEACHER"
    # Personal student fields stay empty for a teacher course.
    assert work["submitted"] is False
    assert work["graded"] is False
    assert work["points"] is None
    # The class-wide aggregates carry the real numbers.
    assert work["student_count"] == 1
    assert work["submission_count"] == 1
    assert work["graded_count"] == 0
    assert work["average_percent"] is None

    # Teacher coursework never leaks into the personal dashboard views.
    assert client.get("/api/assignments").json() == []
    assert client.get("/api/grades").json() == []


def test_percentages_stay_consistent_across_views(client, db, owner_id):
    """§22: the same grade yields the same percent in every representation."""
    db.add(Course(user_id=owner_id, id="t2", name="Chem", course_state="ACTIVE"))
    db.add(CourseRole(user_id=owner_id, course_id="t2", role="TEACHER"))
    db.add(
        CourseWork(
            user_id=owner_id,
            id="tw2",
            course_id="t2",
            title="Exam",
            max_points=100,
            state="PUBLISHED",
        )
    )
    db.add(
        CourseStudent(
            user_id=owner_id, course_id="t2", student_id="s1", full_name="Sam"
        )
    )
    db.add(
        CourseWorkSubmission(
            user_id=owner_id,
            course_id="t2",
            coursework_id="tw2",
            student_id="s1",
            state="RETURNED",
            assigned_points=90.0,
        )
    )
    db.commit()

    matrix = client.get("/api/courses/t2/grades").json()
    assert matrix["rows"][0]["cells"][0]["percent"] == 90.0
    assert matrix["rows"][0]["average_percent"] == 90.0
    assert matrix["class_average"] == 90.0

    work = client.get("/api/courses/t2/coursework").json()[0]
    assert work["average_percent"] == 90.0
    assert work["graded_count"] == 1

    student = client.get("/api/courses/t2/students/s1/grades").json()
    assert student["average_percent"] == 90.0
    assert student["items"][0]["percent"] == 90.0


def test_archived_courses_are_hidden_everywhere(client, db, owner_id):
    db.add(Course(user_id=owner_id, id="arch", name="Old", course_state="ARCHIVED"))
    db.add(CourseRole(user_id=owner_id, course_id="arch", role="STUDENT"))
    db.commit()

    assert client.get("/api/courses").json() == []
    assert client.get("/api/courses/arch").status_code == 404
    assert client.get("/api/courses/arch/coursework").status_code == 404


# ----------------------------------------------------------- §23 status codes


def test_unknown_student_is_404_for_a_teacher(client, teacher_course):
    """§23: a student outside the roster is not disclosed as an empty row."""
    response = client.get("/api/courses/t1/students/nobody/grades")
    assert response.status_code == 404


def test_student_asking_for_another_student_is_403(client, student_course):
    assert client.get("/api/courses/c1/students/someone/grades").status_code == 403


def test_me_requires_a_session_in_hosted_mode(hosted_client):
    assert hosted_client.get("/api/me").status_code == 401


# ------------------------------------------------------- §24 identity surface


def test_desktop_me_returns_the_local_owner(client, owner_id):
    body = client.get("/api/me").json()
    assert body["id"] == owner_id
    # The desktop local owner has no Google-derived profile until it syncs.
    assert body["name"] is None
    assert body["email"] is None


def test_auth_status_reports_no_identity_until_signed_in(client, owner_id):
    """§26: an unauthenticated desktop session carries no identity at all."""
    body = client.get("/api/auth/status").json()
    assert body["authenticated"] is False
    assert body["user"] is None
    assert "user_name" not in body and "user_email" not in body
    _assert_no_oauth_material(body)


def test_auth_status_carries_a_nested_user_and_no_oauth_material(
    client, owner_id, monkeypatch
):
    """§26: ``user`` is the only identity shape — the stage-6 flat mirrors
    were dropped once the frontend switched over."""
    import auth

    monkeypatch.setattr(auth, "get_valid_credentials", lambda: object())
    monkeypatch.setattr(
        "api._cached_profile",
        lambda user, creds: ("Desk Owner", "owner@example.com"),
    )
    body = client.get("/api/auth/status").json()
    assert body["authenticated"] is True
    # ``is_admin`` (ADR-0035) is the single admin BOOLEAN the backend derives;
    # the desktop owner is never an administrator.
    assert body["user"] == {
        "id": owner_id,
        "name": "Desk Owner",
        "email": "owner@example.com",
        "is_admin": False,
    }
    assert "user_name" not in body and "user_email" not in body
    _assert_no_oauth_material(body)


def test_hosted_me_and_auth_status_describe_the_session_user(hosted_client, db):
    alice = _seed_user(db, "sub-alice", "Alice")
    _add_session(db, alice, "raw-alice-token")
    hosted_client.cookies.set("gch_session", "raw-alice-token")

    me = hosted_client.get("/api/me")
    assert me.status_code == 200
    # The admin flag is a BOOLEAN derived by the backend (ADR-0035) — this
    # session is not in ADMIN_EMAILS, and the addresses themselves are never
    # part of the response.
    assert me.json() == {
        "id": alice.id,
        "name": "Alice",
        "email": "sub-alice@example.com",
        "is_admin": False,
    }

    status = hosted_client.get("/api/auth/status")
    assert status.status_code == 200
    assert status.json()["user"] == me.json()
    _assert_no_oauth_material(status.json())


def test_usernames_are_not_crossed_between_sessions(hosted_client, db):
    """§24: each browser's status names its OWN session user."""
    alice = _seed_user(db, "sub-alice", "Alice")
    bob = _seed_user(db, "sub-bob", "Bob")
    _add_session(db, alice, "raw-alice-token")
    _add_session(db, bob, "raw-bob-token")

    hosted_client.cookies.set("gch_session", "raw-alice-token")
    assert hosted_client.get("/api/auth/status").json()["user"]["id"] == alice.id
    hosted_client.cookies.set("gch_session", "raw-bob-token")
    assert hosted_client.get("/api/auth/status").json()["user"]["id"] == bob.id


def _assert_no_oauth_material(body: dict) -> None:
    """No token, secret, code or Google credential object may be serialized."""
    text = json.dumps(body).lower()
    assert "token" not in text
    assert "secret" not in text
    assert "authorization_code" not in text
    # The consent URL is a desktop-only loopback affordance (ADR-0019); the
    # hosted status must never hand one to the browser.
    assert body.get("auth_url") is None


def test_local_provider_is_never_created_by_a_hosted_request(hosted_client, db):
    """§24: an anonymous hosted call cannot mint the desktop local owner."""
    alice = _seed_user(db, "sub-alice", "Alice")
    _add_session(db, alice, "raw-alice-token")
    hosted_client.cookies.set("gch_session", "raw-alice-token")
    hosted_client.get("/api/me")

    local_rows = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.provider == ownership.LOCAL_PROVIDER)
    )
    assert local_rows == 0
