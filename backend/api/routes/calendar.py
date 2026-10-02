"""Due-date calendar grouped by day.

Month grids are built client-side (ADR-0009); this endpoint only answers "which
assignments fall between these two dates", which it does from the same cached
assignment list the dashboard renders.
"""

# ruff: noqa: B008, DTZ005
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004).

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api import queries
from api.deps import current_user_id
from database import get_db

router = APIRouter()


@router.get("/calendar")
def calendar(
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    def _parse(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    start = _parse(from_date) or datetime.now().replace(day=1)
    end = _parse(to_date) or (start + timedelta(days=62))
    grouped: dict[str, list] = {}
    for a in queries.assignments._student_only(
        queries.assignments._load_assignments(db, owner_id)
    ):
        if a.due_at is None or not (start <= a.due_at <= end):
            continue
        grouped.setdefault(a.due_at.date().isoformat(), []).append(a)
    return {"from": start.isoformat(), "to": end.isoformat(), "days": grouped}