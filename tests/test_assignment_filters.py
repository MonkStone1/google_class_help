# pyright: reportMissingImports=false
"""Assignment filters and the SQL course aggregates (review §2.1)."""

from datetime import datetime, timedelta

import pytest

from models import Course, CourseRole, CourseWork, StudentSubmission

NOW = datetime.now()  # noqa: DTZ005 - naive local time matches the cache


def _work(work_id: str, title: str, due_days: int | None, max_points: float = 100):
    due = None if due_days is None else NOW + timedelta(days=due_days)
    return CourseWork(
        id=work_id,
        course_id="c1",
        title=title,
        max_points=max_points,
        state="PUBLISHED",
        due_at=due,
    )


@pytest.fixture()
def seeded_assignments(db):
    db.add(Course(id="c1", name="History", course_state="ACTIVE"))
    db.add(CourseRole(course_id="c1", role="STUDENT"))
    # w1: turned in, overdue window (past due) — completed
    # w2: nothing submitted, past due — todo + overdue
    # w3: nothing submitted, due in 3 days — todo + upcoming
    # w4: turned in and graded — completed + graded
    db.add_all(
        [
            _work("w1", "Essay one", -2),
            _work("w2", "Essay two", -1),
            _work("w3", "Essay three", 3),
            _work("w4", "Test", None),
        ]
    )
    db.add_all(
        [
            StudentSubmission(course_id="c1", coursework_id="w1", state="TURNED_IN"),
            StudentSubmission(
                course_id="c1", coursework_id="w4", state="RETURNED", assigned_points=80
            ),
        ]
    )
    db.commit()


def test_status_todo(client, seeded_assignments):
    body = client.get("/api/assignments", params={"status": "todo"}).json()
    assert {a["id"] for a in body} == {"w2", "w3"}


def test_status_overdue(client, seeded_assignments):
    body = client.get("/api/assignments", params={"status": "overdue"}).json()
    assert {a["id"] for a in body} == {"w2"}


def test_status_completed(client, seeded_assignments):
    body = client.get("/api/assignments", params={"status": "completed"}).json()
    assert {a["id"] for a in body} == {"w1", "w4"}


def test_status_graded(client, seeded_assignments):
    body = client.get("/api/assignments", params={"status": "graded"}).json()
    assert {a["id"] for a in body} == {"w4"}


def test_upcoming_window(client, seeded_assignments):
    body = client.get("/api/assignments/upcoming", params={"days": 7}).json()
    assert {a["id"] for a in body} == {"w3"}


def test_course_aggregates_are_computed_in_sql(client, seeded_assignments):
    course = next(c for c in client.get("/api/courses").json() if c["id"] == "c1")
    assert course["total_assignments"] == 4
    assert course["todo_count"] == 2
    assert course["overdue_count"] == 1
    assert course["graded_count"] == 1
    assert course["average_grade"] == 80.0


def test_coursework_detail_uses_primary_key(client, seeded_assignments):
    response = client.get("/api/courses/c1/coursework/w2")
    assert response.status_code == 200
    assert response.json()["title"] == "Essay two"


def test_coursework_detail_missing_is_404(client, seeded_assignments):
    assert client.get("/api/courses/c1/coursework/missing").status_code == 404


def test_status_totals_come_from_sql(client, seeded_assignments):
    body = client.get("/api/status").json()
    assert body["authenticated"] is False
    assert body["total_assignments"] == 4
    assert body["completed"] == 2
    assert body["overdue"] == 1
    assert body["missing"] == 1
    assert body["due_today"] == 0
    assert body["average_grade"] == 80.0
