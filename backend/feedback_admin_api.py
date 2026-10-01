"""Administrator ticket endpoints (ADR-0035).

Every handler takes ``admin: User = Depends(require_admin)`` — the single
authorization seam of the feature. There is no route that checks the address
list by hand and no route that forgets the check, because the dependency is a
parameter of every function below: adding a new admin endpoint and forgetting
the guard is not expressible without visibly dropping the parameter.

Differences from the user router, and why:

- reads are NOT filtered by the caller, because an administrator is supposed to
  see every ticket — the dependency above already answered 401/403;
- responses use the ``Admin*`` models, which carry the author's real e-mail.
  The user-facing models have no such field, so the regular surface cannot leak
  it even by mistake;
- deletion is real and irreversible: the row goes, ON DELETE CASCADE removes the
  messages and attachment rows, and the files are unlinked from the volume.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default (same dispensation as api.py).

import json
import logging
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

# ``request.form()`` yields Starlette's UploadFile (FastAPI's is a subclass of
# it, so the reverse isinstance check would never match a real part).
from starlette.datastructures import UploadFile

import feedback_attachments as attachments
import feedback_service as service
from admin_auth import require_admin
from config import FEEDBACK_DEFAULT_ADMIN_NAME
from database import get_db
from models_auth import User
from models_feedback import (
    AUTHOR_ADMIN,
    STATUS_IN_PROGRESS,
    STATUS_NEW,
    STATUS_RESOLVED,
    FeedbackTicket,
    TicketAttachment,
    TicketMessage,
)
from schemas_feedback import (
    AdminMessageOut,
    AdminReplyCreateIn,
    AdminStatusUpdateIn,
    AdminTicketDetailOut,
    AdminTicketListOut,
    AdminTicketOut,
    AttachmentOut,
    FeedbackStatsOut,
    FeedbackStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/feedback", tags=["admin"])

# The closed filter set of the admin list. A filter the schema does not know
# would silently return an empty list, so it is validated instead (422).
FILTER_STATUSES = (STATUS_NEW, STATUS_IN_PROGRESS, STATUS_RESOLVED)


def _attachment_out(row: TicketAttachment) -> AttachmentOut:
    return AttachmentOut(
        id=row.id,
        original_name=row.original_name,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )


def _admin_message_out(message: TicketMessage, files) -> AdminMessageOut:
    """The full identity projection an administrator may read."""
    return AdminMessageOut(
        id=message.id,
        author_type=message.author_type,
        display_name=message.display_name,
        author_email=message.author_email,
        author_user_id=message.author_user_id,
        body_markdown=message.body_markdown,
        created_at=message.created_at,
        attachments=[_attachment_out(row) for row in files],
    )


def _owner_names(
    db: Session, ticket_ids: list[int]
) -> dict[int, tuple[str | None, str | None]]:
    """``user_id -> (display_name, email)`` for the tickets on screen.

    One query for the whole page instead of a per-row lookup, and only for the
    ticket owners on this page — an administrator sees the contact details of the
    people who wrote to support, and nothing else.
    """
    if not ticket_ids:
        return {}
    owners = (
        select(FeedbackTicket.user_id, User.display_name, User.email)
        .join(User, User.id == FeedbackTicket.user_id)
        .where(FeedbackTicket.id.in_(ticket_ids))
    )
    return {
        int(user_id): (display_name, email)
        for user_id, display_name, email in db.execute(owners).all()
    }


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
        # Parameterized LIKE — the needle is data, never SQL. The wildcards are
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
    counts, and no ordering — the dashboard wants numbers, not rows.
    """
    counts = service.counts_by_status(db)
    return FeedbackStatsOut(
        total=sum(counts.values()),
        new=counts.get(STATUS_NEW, 0),
        in_progress=counts.get(STATUS_IN_PROGRESS, 0),
        resolved=counts.get(STATUS_RESOLVED, 0),
    )


def _detail(db: Session, ticket: FeedbackTicket) -> AdminTicketDetailOut:
    """The admin projection of a ticket: owner contact + full conversation."""
    owner = db.get(User, ticket.user_id)
    conversation = service.messages_with_attachments(db, ticket.id)
    return AdminTicketDetailOut(
        id=ticket.id,
        category=ticket.category,
        subject=ticket.subject,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        user_id=ticket.user_id,
        user_name=owner.display_name if owner else None,
        user_email=owner.email if owner else None,
        messages=[
            _admin_message_out(message, files) for message, files in conversation
        ],
    )


@router.get("/tickets/{ticket_id}", response_model=AdminTicketDetailOut)
def read_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminTicketDetailOut:
    """Any ticket with its full conversation and the real author identities.

    Not filtered by the caller — an administrator is supposed to see every
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
      taken from the session — never from the request, so the audit trail stays
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
    """Change the ticket status — and ONLY the status.

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
    does not exist — afterwards the id answers 404 for the owner as well, and
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


# ------------------------------------------------------------ request bodies


async def _json_or_form(request: Request) -> dict[str, Any]:
    """The request payload as a dict, from JSON or from a form body."""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or (
        "application/x-www-form-urlencoded" in content_type
    ):
        form = await request.form()
        return {key: value for key, value in form.items() if isinstance(value, str)}
    raw = await request.body()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Malformed request body.") from exc
    return payload if isinstance(payload, dict) else {}


async def _read_admin_reply(request: Request) -> AdminReplyCreateIn:
    """Validate the administrator's answer, including the chosen public name."""
    payload = await _json_or_form(request)
    try:
        return AdminReplyCreateIn(
            body_markdown=str(payload.get("body_markdown") or ""),
            display_name=(
                str(payload["display_name"])
                if payload.get("display_name") is not None
                else None
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=_first_error(exc)) from exc


async def _read_status(request: Request) -> str:
    """The raw status string; an absent or non-string value is 422 downstream."""
    payload = await _json_or_form(request)
    value = payload.get("status")
    if value is None:
        raise HTTPException(status_code=422, detail="Status is required.")
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail="Unknown status.")
    return value.strip().lower()


async def _admin_uploads(request: Request) -> list[UploadFile] | None:
    """The optional files of an administrator's answer."""
    if "multipart/form-data" not in request.headers.get("content-type", ""):
        return None
    form = await request.form()
    return [
        value
        for value in form.getlist("files")
        if isinstance(value, UploadFile) and value.filename
    ]


def _first_error(exc: Exception) -> str:
    """A short validation message, never the whole error object.

    Only a Pydantic ``ValidationError`` is unwrapped here — reaching into an
    arbitrary exception with ``getattr`` and swallowing every failure would hide
    real bugs behind a generic "Invalid value".
    """
    if isinstance(exc, ValidationError) and exc.errors():
        return str(exc.errors()[0].get("msg", "Invalid value."))
    return "Invalid value."
