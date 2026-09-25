"""Pydantic response models shared by the API endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    """Identity of the authenticated user (migration stage 6, §24).

    Exactly the three fields the frontend needs to render "signed in as".
    No Google credential material, no tokens, no OAuth state: the local
    ``users.id`` is the only identifier and it is the caller's own.
    """

    id: int
    name: str | None = None
    email: str | None = None


class AuthStatus(BaseModel):
    """Auth state of THIS browser's application session (§24).

    ``user`` is the only identity shape (migration stage 7, §26): the flat
    ``user_name``/``user_email`` mirrors were dropped once the frontend
    switched over. ``auth_url``/``login_in_progress`` remain because the
    desktop loopback flow still publishes its single-use consent URL.
    """

    authenticated: bool
    login_in_progress: bool = False
    error: str | None = None
    # Consent URL, exposed while the sign-in waits for the redirect: a build
    # whose shell cannot open a browser (Wine) must still be signable (ADR-0019).
    auth_url: str | None = None
    # Identity of the signed-in user; None while unauthenticated.
    user: UserOut | None = None


class MaterialOut(BaseModel):
    type: str | None = None
    title: str | None = None
    url: str | None = None


class AssignmentOut(BaseModel):
    id: str
    course_id: str
    course_name: str
    title: str
    description: str | None = None
    due_at: datetime | None = None
    max_points: float | None = None
    work_type: str | None = None
    state: str | None = None
    alternate_link: str | None = None
    materials: list[MaterialOut] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Derived, application-side fields (never written back to Google).
    submission_state: str | None = None
    submitted: bool = False
    graded: bool = False
    points: float | None = None
    late: bool = False
    is_overdue: bool = False
    priority: str = "low"  # high | medium | low
    # Which view this row belongs to: TEACHER (class-wide) or STUDENT (mine).
    role: str = "STUDENT"
    # Teacher-course aggregates. Not the authenticated user's own submission,
    # which is why they are separate from `submitted`/`graded` above: a
    # teacher is not a student in their own course.
    student_count: int = 0
    submission_count: int = 0
    graded_count: int = 0
    average_percent: float | None = None


class CourseOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    section: str | None = None
    room: str | None = None
    course_state: str | None = None
    teachers: list[str] = Field(default_factory=list)
    role: str = "STUDENT"
    student_count: int = 0
    total_assignments: int = 0
    todo_count: int = 0
    overdue_count: int = 0
    graded_count: int = 0
    average_grade: float | None = None


class GradeItem(BaseModel):
    assignment_id: str
    title: str
    points: float | None = None
    max_points: float | None = None
    percent: float | None = None
    graded_at: datetime | None = None
    due_at: datetime | None = None


class CourseGrades(BaseModel):
    course_id: str
    course_name: str
    average: float | None = None
    items: list[GradeItem] = Field(default_factory=list)


# ------------------------------------------------------ teacher-mode views


class StudentOut(BaseModel):
    id: str
    full_name: str = ""
    email: str | None = None
    photo_url: str | None = None


class SubmissionOut(BaseModel):
    """One student's submission for a coursework item (teacher view).

    `status` collapses the API state + grade into one label
    (not_submitted | turned_in | returned | graded); the booleans stay
    available for filtering. A missing grade is never rendered as 0.
    """

    student_id: str
    student_name: str = ""
    coursework_id: str
    submission_state: str | None = None
    status: str = "not_submitted"
    submitted: bool = False
    returned: bool = False
    graded: bool = False
    late: bool = False
    points: float | None = None
    max_points: float | None = None
    percent: float | None = None
    submitted_at: datetime | None = None
    updated_at: datetime | None = None
    attachments: list[MaterialOut] = Field(default_factory=list)


class AssignmentDetailOut(AssignmentOut):
    submissions: list[SubmissionOut] = Field(default_factory=list)
    # Counts of each derived status, for the assignment statistics block.
    status_counts: dict[str, int] = Field(default_factory=dict)


class CourseDetailOut(BaseModel):
    course: CourseOut
    role: str = "STUDENT"
    students: list[StudentOut] = Field(default_factory=list)
    last_sync: datetime | None = None


class GradeColumn(BaseModel):
    assignment_id: str
    title: str
    max_points: float | None = None
    due_at: datetime | None = None


class SubmissionCell(BaseModel):
    coursework_id: str
    status: str = "not_submitted"
    submitted: bool = False
    returned: bool = False
    graded: bool = False
    late: bool = False
    points: float | None = None
    max_points: float | None = None
    percent: float | None = None
    submitted_at: datetime | None = None
    updated_at: datetime | None = None


class StudentGradeRow(BaseModel):
    student: StudentOut
    cells: list[SubmissionCell] = Field(default_factory=list)
    average_percent: float | None = None


class TeacherGradesOut(BaseModel):
    course_id: str
    course_name: str
    role: str = "TEACHER"
    assignments: list[GradeColumn] = Field(default_factory=list)
    rows: list[StudentGradeRow] = Field(default_factory=list)
    class_average: float | None = None
    last_sync: datetime | None = None


class StudentGradeItem(BaseModel):
    assignment_id: str
    title: str
    due_at: datetime | None = None
    max_points: float | None = None
    submission_state: str | None = None
    status: str = "not_submitted"
    submitted: bool = False
    returned: bool = False
    graded: bool = False
    late: bool = False
    points: float | None = None
    percent: float | None = None
    submitted_at: datetime | None = None
    updated_at: datetime | None = None
    attachments: list[MaterialOut] = Field(default_factory=list)
    alternate_link: str | None = None


class StudentGradesOut(BaseModel):
    course_id: str
    course_name: str
    student: StudentOut
    average_percent: float | None = None
    items: list[StudentGradeItem] = Field(default_factory=list)
    last_sync: datetime | None = None


class SyncStatus(BaseModel):
    authenticated: bool
    last_sync: datetime | None = None
    last_sync_error: str | None = None
    # ``syncing`` is true for both a queued request and a claimed/running job.
    # The frontend uses it to keep watching until the worker reaches a final
    # state; ``sync_status`` remains ``pending`` while the job waits in queue.
    syncing: bool = False
    # Structured sync state (migration stage 5, §18). ``sync_status`` is one
    # of "pending"/"running"/"ok"/"error"/"needs_reauth"; together with the
    # derived ``syncing`` flag it lets the frontend distinguish an active
    # queued/running job, a retryable error, and a re-auth prompt without
    # parsing the error text.
    sync_status: str = "pending"
    last_sync_started_at: datetime | None = None
    last_sync_finished_at: datetime | None = None
    total_assignments: int = 0
    completed: int = 0
    missing: int = 0
    overdue: int = 0
    due_today: int = 0
    average_grade: float | None = None


class SyncResult(BaseModel):
    ok: bool
    last_sync: datetime | None = None
    courses: int = 0
    assignments: int = 0
    error: str | None = None
    # Stage 10 (queued manual sync): hosted POST /api/sync no longer runs the
    # Classroom fan-out inside the HTTP request. It only flags
    # ``sync_requested`` and answers immediately; the worker does the work.
    # ``queued=True`` + ``status="queued"`` means "accepted, watch
    # GET /api/status (sync_status/queued) for progress". Desktop keeps the
    # inline contract (queued=False).
    queued: bool = False
    status: str | None = None
