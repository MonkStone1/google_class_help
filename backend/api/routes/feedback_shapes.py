"""Owner-facing mappers, and the validation that turns errors into 422s.

Split out of the routes (ADR-0039) for one reason that the test suite already
enforces elsewhere: an owner must never see an administrator's view. This
module holds the OWNER projection only — no internal category, no author
identity beyond "support" — so that boundary is one import away from being
reviewed instead of scattered across the handlers.

``validate`` is here rather than in each handler because the error shape must
be identical for every field: a 422 that names the offending field is a contract
the frontend reads, and re-deriving it per handler is how one field starts
answering 500 while its neighbours answer 422.
"""

import json
from collections.abc import Sequence
from typing import Any, TypeVar

from fastapi import HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from db.models.feedback import FeedbackTicket, TicketAttachment, TicketMessage
from feedback import service
from schemas.feedback import AttachmentOut, MessageOut, TicketDetailOut

ModelT = TypeVar("ModelT")

def _attachment_out(row: TicketAttachment) -> AttachmentOut:
    return AttachmentOut(
        id=row.id,
        original_name=row.original_name,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )


def _message_out(
    message: TicketMessage,
    files: Sequence[TicketAttachment],
) -> MessageOut:
    """A message WITHOUT the author e-mail — the user-facing projection.

    ``author_email`` is simply not a field of this model, so a regular user can
    never receive another account's address (§12).
    """
    return MessageOut(
        id=message.id,
        author_type=message.author_type,
        display_name=message.display_name,
        body_markdown=message.body_markdown,
        created_at=message.created_at,
        attachments=[_attachment_out(row) for row in files],
    )


def _ticket_detail(db: Session, ticket: FeedbackTicket) -> TicketDetailOut:
    conversation = service.messages_with_attachments(db, ticket.id)
    return TicketDetailOut(
        id=ticket.id,
        category=ticket.category,
        subject=ticket.subject,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        messages=[_message_out(message, files) for message, files in conversation],
    )


async def _read_text_field(request: Request, name: str) -> str | None:
    """Read one text field from either a JSON or a multipart body.

    The same endpoint serves both shapes, so the field may arrive as a JSON
    property or as a form field. Nothing here ever reads an author field: a
    multipart part called ``display_name`` on the USER reply endpoint is
    ignored, exactly like a JSON property, because the model has no such field.
    """
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or (
        "application/x-www-form-urlencoded" in content_type
    ):
        form = await request.form()
        value = form.get(name)
        return value if isinstance(value, str) else None
    raw = await request.body()
    if not raw:
        return None
    try:
        payload: Any = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Malformed request body.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Malformed request body.")
    value = payload.get(name)
    return value if isinstance(value, str) else None


def _validate(model: type[ModelT], **fields: Any) -> ModelT:
    """Validate the collected fields through the Pydantic model (422 on error).

    Only ``ValidationError`` is translated. A bare ``except Exception`` here
    would relabel any unrelated bug in model construction as a client error,
    and the 422 would quietly hide a real failure.

    ``**fields: Any`` is deliberate: the keys are the model's own field names and
    the values arrive from a JSON body or a form, so there is no narrower honest
    type than "whatever the caller sent" — and the model is what checks them.
    """
    try:
        return model(**fields)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_first_error(exc)) from exc


def _first_error(exc: Exception) -> str:
    """A short validation message, never the whole error object.

    Only a Pydantic ``ValidationError`` is unwrapped here — reaching into an
    arbitrary exception with ``getattr`` and swallowing every failure would hide
    real bugs behind a generic "Invalid value".
    """
    if isinstance(exc, ValidationError) and exc.errors():
        return str(exc.errors()[0].get("msg", "Invalid value."))
    return "Invalid value."
