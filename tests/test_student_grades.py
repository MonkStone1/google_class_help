# pyright: reportMissingImports=false
"""Regression test for the student grades endpoint (review §1.2).

Before the fix, ``/students/{id}/grades`` always read CourseWorkSubmission
(a teacher-table) and returned an empty grade list for a student.
"""

import pytest

from db.models.classroom import Course, CourseRole, CourseWork, StudentSubmission


@pytest.fixture()
def seeded_student_course(db, owner_id):
    db.add(Course(user_id=owner_id, id="c1", name="Math", course_state="ACTIVE"))
    db.add(CourseRole(user_id=owner_id, course_id="c1", role="STUDENT"))
    db.add(
        CourseWork(
            user_id=owner_id,
            id="w1",
            course_id="c1",
            title="Quiz",
            max_points=100,
            state="PUBLISHED",
        )
    )
    db.add(
        StudentSubmission(
            user_id=owner_id,
            course_id="c1",
            coursework_id="w1",
            state="RETURNED",
            assigned_points=90,
        )
    )
    db.commit()


def test_student_sees_own_grades(client, seeded_student_course):
    response = client.get("/api/courses/c1/students/me/grades")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["points"] == 90  # before the fix: None
    assert item["graded"] is True
    assert item["percent"] == 90.0
    assert body["average_percent"] == 90.0


def test_student_cannot_view_someone_elses_grades(client, seeded_student_course):
    response = client.get("/api/courses/c1/students/someone-else/grades")
    assert response.status_code == 403
