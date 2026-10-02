"""Domain rules derived from Classroom data — pure functions (review §2.2).

No Google client, no SQLAlchemy, no I/O: everything here takes plain values
and returns plain values, so it is trivially unit-testable. The transport
lives in classroom_api.py, cache writing in sync_store.py, orchestration in
sync_service.py; sync.py re-exports this module for compatibility.
"""

from datetime import datetime

SUBMITTED_STATES = {"TURNED_IN", "RETURNED"}


def is_submitted_state(state: str | None) -> bool:
    return state in SUBMITTED_STATES


# Submission statuses derived server-side (ADR-0004) so every page renders the
# same word for the same Classroom data. "graded" requires an actual assigned
# grade — a returned submission without points is "returned", never "0".
def derive_submission_status(state: str | None, graded: bool) -> str:
    if graded:
        return "graded"
    if state == "RETURNED":
        return "returned"
    if state == "TURNED_IN":
        return "turned_in"
    return "not_submitted"


def grade_percent(points: float | None, max_points: float | None) -> float | None:
    """Percentage only when both values are valid numbers (section 22)."""
    if points is None or max_points is None or max_points <= 0:
        return None
    return round(points / max_points * 100, 1)


def compute_priority(
    due_at: datetime | None, is_overdue: bool, now: datetime, is_todo: bool
) -> str:
    """Priority is assigned only to to-do (not submitted) work.

    HIGH: overdue or due today; MEDIUM: tomorrow or within 3 days; LOW: later.
    Overdue work is to-do by definition. Completed work always stays LOW so it
    never competes with actually pending assignments.
    """
    if not is_todo:
        return "low"
    if is_overdue:
        return "high"
    if due_at is None:
        return "low"
    days_ahead = (due_at.date() - now.date()).days
    if days_ahead <= 0:
        return "high"
    if days_ahead <= 3:
        return "medium"
    return "low"
