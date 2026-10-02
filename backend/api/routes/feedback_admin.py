"""Administrator ticket endpoints (ADR-0035).

Every handler takes ``admin: User = Depends(require_admin)`` — the single
authorization seam of the feature. There is no route that checks the address
list by hand and no route that forgets the check, because the dependency is a
parameter of every function below: adding a new admin endpoint and forgetting
the guard is not expressible without visibly doing so.

The admin-only row mappers and the request bodies live in
``api/routes/admin_shapes.py`` (ADR-0039): they are the ADMIN view of a ticket,
and keeping them apart is what keeps those fields out of the owner's payload,
which the owner-response test pins to an exact column set.
"""

# ruff: noqa: B008
# B008: FastAPI's documented DI idiom puts Depends() in the parameter default;
# that is how every handler here declares its session and its caller.

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api.routes.admin_shapes import (
    _admin_uploads,
    _detail,
    _owner_names,
    _read_admin_reply,
    _read_status,
)
from auth.roles import require_admin
from core.config import FEEDBACK_DEFAULT_ADMIN_NAME
from db.models.accounts import User
from db.models.feedback import (
    AUTHOR_ADMIN,
    STATUS_IN_PROGRESS,
    STATUS_NEW,
    STATUS_RESOLVED,
    FeedbackTicket,
    TicketMessage,
)
from db.session import get_db
from feedback import attachments, service
from schemas.feedback import (
    AdminStatusUpdateIn,
    AdminTicketDetailOut,
    AdminTicketListOut,
    AdminTicketOut,
    FeedbackStatsOut,
    FeedbackStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/feedback", tags=["feedback-admin"])

# The status filter accepts exactly the statuses the model defines, so the
# query parameter can be rejected with 422 without a database round trip.
FILTER_STATUSES = (STATUS_NEW, STATUS_IN_PROGRESS, STATUS_RESOLVED)


@router.get("/tickets", response_model=AdminTicketListOut)
def list_tickets(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminTicketListOut:
    """Every ticket, filtered by status/category/search, paginated.

    ``q`` matches a subject or a message body as a substring (case-insensitive
    through ``ILIKE``; SQLite's ``like`` is case-insensitive for ASCII, which is
    what the tests assert). The filters are ANDed and the ordering is the same
    "newest activity first" as everywhere else, so the list stays stable while
    somebody works on it.
    """
    statement = select(FeedbackTicket)
    if status:
        normalized = status.strip().lower()
        if normalized not in FILTER_STATUSES:
            raise HTTPException(status_code=422, detail="Unknown status filter.")
        statement = statement.where(FeedbackTicket.status == normalized)
    if category:
        statement = statement.where(FeedbackTicket.category == category.strip().lower())

    needle = (q or "").strip()
    if needle:
        # Parameterized LIKE вЂ” the needle is data, never SQL. The wildcards are
        # stripped so a search for "100%" is a literal search, not a pattern.
        pattern = f"%{needle.replace('%', '').replace('_', '')}%"
        statement = statement.where(
            or_(
                FeedbackTicket.subject.ilike(pattern),
                FeedbackTicket.id.in_(
                    select(TicketMessage.ticket_id).where(
                        TicketMessage.body_markdown.ilike(pattern)
                    )
                ),
            )
        )

    total = len(list(db.execute(statement).scalars()))
    rows = list(
        db.execute(
            statement.order_by(
                FeedbackTicket.updated_at.desc(), FeedbackTicket.id.desc()
            )
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    owners = _owner_names(db, [row.id for row in rows])
    items = [
        AdminTicketOut(
            id=row.id,
            category=row.category,
            subject=row.subject,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            message_count=service.message_count(db, row.id),
            user_id=row.user_id,
            user_name=owners.get(row.user_id, (None, None))[0],
            user_email=owners.get(row.user_id, (None, None))[1],
        )
        for row in rows
    ]
    return AdminTicketListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/stats", response_model=FeedbackStatsOut)
def feedback_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> FeedbackStatsOut:
    """Dashboard counters: total and the per-status breakdown.

    One grouped query (feedback_service.counts_by_status) rather than four
    counts, and no ordering вЂ” the dashboard wants numbers, not rows.
    """
    counts = service.counts_by_status(db)
    return FeedbackStatsOut(
        total=sum(counts.values()),
        new=counts.get(STATUS_NEW, 0),
        in_progress=counts.get(STATUS_IN_PROGRESS, 0),
        resolved=counts.get(STATUS_RESOLVED, 0),
    )


@router.get("/tickets/{ticket_id}", response_model=AdminTicketDetailOut)
def read_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminTicketDetailOut:
    """Any ticket with its full conversation and the real author identities.

    Not filtered by the caller вЂ” an administrator is supposed to see every
    ticket. The dependency above already answered 401/403.
    """
    return _detail(db, service.any_ticket(db, ticket_id))


@router.post("/tickets/{ticket_id}/messages", response_model=AdminTicketDetailOut)
async def reply_to_ticket(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminTicketDetailOut:
    """Answer a ticket under a chosen public display name.

    The stored identity is split in two, and this is the whole point of the
    feature:

    - ``author_user_id`` / ``author_email`` = the AUTHENTICATED administrator,
      taken from the session вЂ” never from the request, so the audit trail stays
      correct;
    - ``display_name`` = the public label the ticket owner sees (default
      ``GoogleClassHelp Support``, capped at 100 characters). Two administrators
      may therefore answer under different names while both are recorded
      correctly internally.
    """
    service.enforce_reply_limit(request, admin)
    ticket = service.any_ticket(db, ticket_id)

    payload = await _read_admin_reply(request)
    files = await _admin_uploads(request)

    await service.add_message(
        db,
        ticket=ticket,
        author=admin,
        author_type=AUTHOR_ADMIN,
        body_markdown=payload.body_markdown,
        display_name=payload.display_name or FEEDBACK_DEFAULT_ADMIN_NAME,
        files=files,
    )
    db.refresh(ticket)
    return _detail(db, ticket)


@router.patch("/tickets/{ticket_id}", response_model=AdminTicketDetailOut)
async def set_status(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminTicketDetailOut:
    """Change the ticket status вЂ” and ONLY the status.

    The body is ``{"status": "resolved"}``; anything else is ignored by the
    model, so this endpoint cannot become a way to rewrite a message, an author
    or an owner. An unknown status is 422 (the closed set).
    """
    ticket = service.any_ticket(db, ticket_id)
    raw = await _read_status(request)
    try:
        # The enum IS the validation: an unknown status raises ValueError here,
        # which becomes a 422 with a short detail.
        payload = AdminStatusUpdateIn(status=FeedbackStatus(raw))
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Unknown status.") from exc

    ticket.status = payload.status.value
    # Bumped so the ticket moves to the top of both lists: a status change is
    # activity, and "newest activity first" must mean what it says.
    ticket.updated_at = service.utcnow()
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return _detail(db, ticket)


@router.delete("/tickets/{ticket_id}", status_code=204)
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Response:
    """Delete a ticket permanently, with its conversation and its files.

    Real deletion, no ``deleted_at`` and no restore (ADR-0035): the row goes,
    ``ON DELETE CASCADE`` takes the messages and attachment rows with it, and the
    files are unlinked from the volume. 204 on success, 404 for a ticket that
    does not exist вЂ” afterwards the id answers 404 for the owner as well, and
    the ticket is gone from a fresh list.

    A file that cannot be unlinked does NOT fail the request: the row deletion
    is the contract, and the filesystem cleanup is best effort.
    """
    ticket = service.any_ticket(db, ticket_id)
    files = service.ticket_files(db, ticket.id)
    db.delete(ticket)
    db.commit()
    attachments.unlink_ticket_files(ticket.id, files)
    logger.info(
        "Feedback ticket id=%s permanently deleted by user id=%s.",
        ticket.id,
        admin.id,
    )
    return Response(status_code=204)
