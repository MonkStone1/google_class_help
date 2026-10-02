"""Assignment endpoints: the student list, upcoming/overdue, and the
coursework detail page (metadata + submission table).
"""

# ruff: noqa: B008, DTZ005
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.
# DTZ005: the cache stores naive local datetimes on purpose (ADR-0004); due
#       dates arrive from Classroom without a timezone.

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api import guards, queries
from api.deps import current_user_id
from db.models.classroom import CourseWork
from db.session import get_db
from schemas.dashboard import AssignmentDetailOut, AssignmentOut, SubmissionOut

router = APIRouter()


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(
    course_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> list[AssignmentOut]:
    assignments = queries.assignments._student_only(
        queries.assignments._load_assignments(db, owner_id)
    )
    if course_id:
        assignments = [a for a in assignments if a.course_id == course_id]
    if search:
        needle = search.lower()
        assignments = [
            a
            for a in assignments
            if needle in a.title.lower()
            or needle in a.course_name.lower()
            or (a.description and needle in a.description.lower())
        ]
    if status == "todo":
        assignments = [a for a in assignments if not a.submitted]
    elif status == "overdue":
        assignments = [a for a in assignments if a.is_overdue]
    elif status == "completed":
        assignments = [a for a in assignments if a.submitted]
    elif status == "graded":
        assignments = [a for a in assignments if a.graded]
    elif status == "ungraded":
        assignments = [a for a in assignments if not a.graded]
    return assignments


@router.get("/assignments/upcoming", response_model=list[AssignmentOut])
def upcoming(
    days: int = Query(default=7, ge=1, le=60),
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> list[AssignmentOut]:
    now = datetime.now()
    end = now + timedelta(days=days)
    return [
        a
        for a in queries.assignments._student_only(
            queries.assignments._load_assignments(db, owner_id)
        )
        if a.due_at is not None and now <= a.due_at <= end and not a.submitted
    ]


@router.get("/assignments/overdue", response_model=list[AssignmentOut])
def overdue(
    owner_id: int = Depends(current_user_id), db: Session = Depends(get_db)
) -> list[AssignmentOut]:
    return [
        a
        for a in queries.assignments._student_only(
            queries.assignments._load_assignments(db, owner_id)
        )
        if a.is_overdue
    ]


@router.get(
    "/courses/{course_id}/coursework/{coursework_id}",
    response_model=AssignmentDetailOut,
)
def coursework_detail(
    course_id: str,
    coursework_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> AssignmentDetailOut:
    """Full assignment page: metadata, materials and the submission table."""
    course = guards._get_course(db, owner_id, course_id)
    work = db.get(CourseWork, (owner_id, coursework_id))
    if work is None or work.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    base = queries.assignments._assignment_by_id(
        db, owner_id, coursework_id
    )  # PK lookup, not a full scan (§2.1)
    if base is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    submissions = queries.teacher._submissions_for_work(db, owner_id, course, work)
    counts: dict[str, int] = {}
    for item in submissions:
        counts[item.status] = counts.get(item.status, 0) + 1
    return AssignmentDetailOut(
        **base.model_dump(), submissions=submissions, status_counts=counts
    )


@router.get(
    "/courses/{course_id}/coursework/{coursework_id}/submissions",
    response_model=list[SubmissionOut],
)
def coursework_submissions(
    course_id: str,
    coursework_id: str,
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> list[SubmissionOut]:
    course = guards._get_course(db, owner_id, course_id)
    work = db.get(CourseWork, (owner_id, coursework_id))
    if work is None or work.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    return queries.teacher._submissions_for_work(db, owner_id, course, work)