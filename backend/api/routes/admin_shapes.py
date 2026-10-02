"""Row → response, and the request bodies the admin API accepts (ADR-0039 split).

Split out of the routes because the ADMIN view of a ticket is not the owner's
view of the same row: the admin response carries the author's identity and the
internal category, and it exists only for accounts in the ``admins`` table.
Keeping the two mappers apart is what stops the admin fields from drifting into
the owner's payload — the test that pins the owner's response to the exact
column set would otherwise have to allow them.

The request bodies live here too, next to the shapes they produce, so the
OpenAPI document is generated from one file per concern rather than from a
module that mixes pydantic models with HTTP handlers.
"""

import json
from typing import Any

from fastapi import HTTPException, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.accounts import User
from db.models.feedback import FeedbackTicket, TicketAttachment, TicketMessage
from feedback import service
from schemas.feedback import (
    AdminMessageOut,
    AdminReplyCreateIn,
    AdminTicketDetailOut,
    AttachmentOut,
)


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
