"""User-facing ticket endpoints (ADR-0035).

Every handler resolves the caller through ``ownership.get_current_user`` — the
session user in hosted mode, the desktop local owner otherwise — and every query
filters on ``ticket.user_id == user.id`` INSIDE the statement. No handler takes a
user id from the request, so the data scope cannot be chosen by the caller.

A ticket that exists but belongs to somebody else answers **404**, identical to
a ticket that does not exist: a 403 would confirm the id is real (§23).

Bodies are JSON for the text fields and multipart for messages that carry
attachments, because FastAPI cannot parse a JSON body and files in one request.
Creation and reply therefore accept BOTH shapes on the same endpoint — a
multipart request without files is still a multipart request — which keeps one
URL per action instead of a second parallel API. Anything else is 422.

Identity is never taken from the form: the stored author is the authenticated
user and the byline is the profile (admin_auth/schemas_feedback own that rule).
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default (same dispensation as api.py).

import logging
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

# ``request.form()`` yields Starlette's UploadFile (FastAPI's is a subclass of
# it, so the reverse isinstance check would never match a real part).
from starlette.datastructures import UploadFile

# The OWNER projection and the shared 422 shape live in
# ``api/routes/feedback_shapes.py`` (ADR-0039), so what a user is shown is
# defined apart from the routes that serve it.
from api.routes.feedback_shapes import (
    _read_text_field,
    _ticket_detail,
    _validate,
)
from auth import ownership
from auth.roles import is_admin_email
from db.models.accounts import User
from db.models.feedback import (
    AUTHOR_USER,
    STATUS_NEW,
    FeedbackTicket,
    TicketAttachment,
)
from db.session import get_db
from feedback import attachments, service
from schemas.feedback import (
    FeedbackCategory,
    ReplyCreateIn,
    TicketCreateIn,
    TicketDetailOut,
    TicketOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

# ``_validate`` returns whatever model it was handed, so the caller keeps the
# concrete type (``TicketCreateIn`` stays ``TicketCreateIn``, not ``BaseModel``).
ModelT = TypeVar("ModelT", bound=BaseModel)


@router.get("/tickets", response_model=list[TicketOut])
def list_my_tickets(
    db: Session = Depends(get_db),
    user: User = Depends(ownership.get_current_user),
) -> list[TicketOut]:
    """The caller's OWN tickets, newest activity first.

    Sorted by ``updated_at`` (bumped by every message), not by creation date: a
    ticket somebody just answered is the one being looked for.
    """
    tickets = list(
        db.execute(
            select(FeedbackTicket)
            .where(FeedbackTicket.user_id == user.id)
            .order_by(FeedbackTicket.updated_at.desc(), FeedbackTicket.id.desc()),
        ).scalars(),
    )
    return [
        TicketOut(
            id=ticket.id,
            category=ticket.category,
            subject=ticket.subject,
            status=ticket.status,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            message_count=service.message_count(db, ticket.id),
        )
        for ticket in tickets
    ]


def _is_multipart(request: Request) -> bool:
    return "multipart/form-data" in request.headers.get("content-type", "")


async def _uploads(request: Request) -> list[UploadFile]:
    """The uploaded files of a multipart body, under the ``files`` part name.

    Non-file parts are ignored, so the same endpoint serves a form with no
    attachment at all.
    """
    form = await request.form()
    return [
        value
        for value in form.getlist("files")
        if isinstance(value, UploadFile) and value.filename
    ]


@router.post("/tickets", response_model=TicketDetailOut, status_code=201)
async def create_ticket(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(ownership.get_current_user),
) -> TicketDetailOut:
    """Open a ticket: category, subject, the first Markdown message, files.

    201 with the created ticket and its conversation, so the UI can navigate
    straight to the thread. The rate limit is checked BEFORE the body is read,
    so a spam loop never uploads a megabyte.
    """
    service.enforce_creation_limit(request, user)

    category_raw = await _read_text_field(request, "category")
    subject_raw = await _read_text_field(request, "subject")
    body_raw = await _read_text_field(request, "body_markdown")

    if category_raw is None:
        raise HTTPException(status_code=422, detail="Category is required.")
    try:
        # The closed set, validated server-side; anything else is 422.
        category = FeedbackCategory(str(category_raw).strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unknown category.") from exc

    payload = _validate(
        TicketCreateIn,
        category=category,
        subject=subject_raw or "",
        body_markdown=body_raw or "",
    )

    now = service.utcnow()
    ticket = FeedbackTicket(
        user_id=user.id,
        category=category.value,
        subject=payload.subject,
        status=STATUS_NEW,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    files = await _uploads(request) if _is_multipart(request) else None
    await service.add_message(
        db,
        ticket=ticket,
        author=user,
        author_type=AUTHOR_USER,
        body_markdown=payload.body_markdown,
        display_name=service.user_display_name(user),
        files=files,
    )
    logger.info("Feedback ticket id=%s created by user id=%s.", ticket.id, user.id)
    return _ticket_detail(db, ticket)


@router.get("/tickets/{ticket_id}", response_model=TicketDetailOut)
def get_my_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(ownership.get_current_user),
) -> TicketDetailOut:
    """One own ticket with its whole conversation, or 404."""
    ticket = service.own_ticket(db, user, ticket_id)
    return _ticket_detail(db, ticket)


@router.post("/tickets/{ticket_id}/messages", response_model=TicketDetailOut)
async def reply_to_ticket(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(ownership.get_current_user),
) -> TicketDetailOut:
    """Reply to an own ticket.

    The body carries ``body_markdown`` only. ``author_type``,
    ``author_user_id``, ``author_email`` and ``display_name`` are not part of the
    model, so sending them changes nothing — a user cannot post under somebody
    else's name (ADR-0035).

    Replying to a ``resolved`` ticket reopens it (``in_progress``), which the
    UI shows immediately.
    """
    service.enforce_reply_limit(request, user)
    ticket = service.own_ticket(db, user, ticket_id)

    body_raw = await _read_text_field(request, "body_markdown")
    payload = _validate(ReplyCreateIn, body_markdown=body_raw or "")

    files = await _uploads(request) if _is_multipart(request) else None
    await service.add_message(
        db,
        ticket=ticket,
        author=user,
        author_type=AUTHOR_USER,
        body_markdown=payload.body_markdown,
        display_name=service.user_display_name(user),
        files=files,
    )
    db.refresh(ticket)
    return _ticket_detail(db, ticket)


@router.get("/attachments/{attachment_id}")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(ownership.get_current_user),
) -> FileResponse:
    """Download an attachment of a ticket the caller OWNS (or any, as an admin).

    The ownership check is a single joined statement: the attachment's ticket
    must belong to the caller. Somebody else's file is 404 — indistinguishable
    from a missing one. Administrators may read any attachment, because support
    has to see what was sent; the fallback path is still 404 for a missing row.
    """
    row = db.execute(
        select(TicketAttachment)
        .join(FeedbackTicket, FeedbackTicket.id == TicketAttachment.ticket_id)
        .where(
            TicketAttachment.id == attachment_id,
            FeedbackTicket.user_id == user.id,
        ),
    ).scalar_one_or_none()
    if row is None and is_admin_email(db, user.email):
        row = attachments.load_attachment(db, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    return attachments.download_response(row)

# The OWNER projection and the shared 422 shape live in
# ``api/routes/feedback_shapes.py`` (ADR-0039), so that what a user sees is
# defined apart from the routes that serve it.
