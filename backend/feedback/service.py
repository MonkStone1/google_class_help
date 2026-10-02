"""The shared ticket service (ADR-0035).

Everything both routers need and NOTHING either of them may decide for itself:

- message creation with the identity rules: the authenticated author plus only
  the inputs the caller is allowed to influence (``author_type`` is derived from
  the route, never from the body; a user reply cannot choose its byline);
- the reopen rule: any new message on a ``resolved`` ticket sets it back to
  ``in_progress``, so a follow-up can never be swallowed;
- the ticket read that resolves the conversation and its attachments;
- the per-user token buckets.

Keeping this in one module is what makes the user path and the admin path
agree by construction rather than by review.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# The file parts come from ``request.form()``, i.e. Starlette's UploadFile.
# `Sequence`, not `list`: `list` is invariant in its element type, so a list of
# Starlette files would not be assignable to a parameter declared with
# FastAPI's subclass — a type error that exists only because of generics.
from starlette.datastructures import UploadFile

from core.config import FEEDBACK_REPLIES_PER_HOUR, FEEDBACK_TICKETS_PER_HOUR
from db.models.accounts import User
from db.models.feedback import (
    STATUS_IN_PROGRESS,
    STATUS_RESOLVED,
    FeedbackTicket,
    TicketAttachment,
    TicketMessage,
)
from feedback import attachments

logger = logging.getLogger(__name__)

# The name a user's message is published under when the profile is empty. The
# desktop local owner has display_name=None and email=None, so it needs one.
FALLBACK_USER_NAME = "User"


def utcnow() -> datetime:
    """Naive UTC — the timestamp convention of the whole backend."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def user_display_name(user: User) -> str:
    """The byline of a user's own message: profile name, then e-mail."""
    return (user.display_name or user.email or FALLBACK_USER_NAME).strip()


# --------------------------------------------------------------- rate limits


def enforce_user_rate_limit(
    request: Request, user: User, action: str, per_hour: int
) -> None:
    """Consume one per-user token; 429 + ``Retry-After`` when the bucket is dry.

    The buckets are the SAME in-memory registry the login/sync/cache surfaces
    use (``app.state.rate_limiter``, rate_limit.py) — one limiter, not two —
    but keyed by ``user.id`` instead of the client IP: a school NAT shares one
    address between many legitimate users, while one authenticated account is
    exactly the identity that should be throttled. The key is namespaced by the
    action, so creating a ticket and replying draw from different allowances.

    Desktop mode keeps the limiter too (it is created for both apps), so the
    limits are identical in both deployment modes — a desktop owner has no
    abuse surface to speak of, and the extra check costs one dict lookup.
    """
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    key = f"feedback:{action}:{user.id}"
    # An hourly window expressed as a refill rate: after the allowance is spent
    # the user recovers gradually instead of waiting for a wall-clock hour.
    if not limiter.allow(key, capacity=per_hour, refill_per_second=per_hour / 3600.0):
        raise HTTPException(
            status_code=429,
            detail="Too many feedback messages; try again later.",
            headers={"Retry-After": "60"},
        )


# ------------------------------------------------------------------- queries


def own_ticket(db: Session, user: User, ticket_id: int) -> FeedbackTicket:
    """One ticket OWNED by the caller, or 404.

    The ``user_id`` filter is part of the SELECT, not a check after it: a ticket
    that exists but belongs to somebody else must be indistinguishable from one
    that does not exist (404, never 403 — a 403 would confirm the id is real).
    """
    ticket = db.execute(
        select(FeedbackTicket).where(
            FeedbackTicket.id == ticket_id, FeedbackTicket.user_id == user.id
        )
    ).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


def any_ticket(db: Session, ticket_id: int) -> FeedbackTicket:
    """Any ticket by id — for the admin routers only.

    These callers already depend on ``require_admin``, so this never runs for a
    regular user; the ownership filter is simply not part of an admin read.
    """
    ticket = db.get(FeedbackTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


def messages_with_attachments(
    db: Session, ticket_id: int
) -> list[tuple[TicketMessage, list[TicketAttachment]]]:
    """The whole conversation in chronological order, each with its files."""
    messages = list(
        db.execute(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at, TicketMessage.id)
        ).scalars()
    )
    if not messages:
        return []
    files: dict[int, list[TicketAttachment]] = {}
    for row in db.execute(
        select(TicketAttachment).where(
            TicketAttachment.message_id.in_([message.id for message in messages])
        )
    ).scalars():
        files.setdefault(row.message_id, []).append(row)
    return [(message, files.get(message.id, [])) for message in messages]


def message_count(db: Session, ticket_id: int) -> int:
    """How many messages a ticket has (a list column, no conversation)."""
    return int(
        db.execute(
            select(func.count(TicketMessage.id)).where(
                TicketMessage.ticket_id == ticket_id
            )
        ).scalar_one()
    )


def counts_by_status(db: Session) -> dict[str, int]:
    """Ticket totals per status — the dashboard counters.

    One grouped query instead of four counts, so the dashboard does not scale
    with the number of statuses.
    """
    rows = db.execute(
        select(FeedbackTicket.status, func.count(FeedbackTicket.id)).group_by(
            FeedbackTicket.status
        )
    ).all()
    return {str(status): int(count) for status, count in rows}


def ticket_files(db: Session, ticket_id: int) -> list[TicketAttachment]:
    """Every attachment row of one ticket (used to unlink the files on delete)."""
    return list(
        db.execute(
            select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id)
        ).scalars()
    )


# --------------------------------------------------------- message creation


async def add_message(
    db: Session,
    *,
    ticket: FeedbackTicket,
    author: User,
    author_type: str,
    body_markdown: str,
    display_name: str,
    files: Sequence[UploadFile] | None = None,
) -> TicketMessage:
    """Append one message and apply the reopen rule.

    Every field of the stored identity is decided HERE, from the authenticated
    author and the route's ``author_type`` — never from the request body:

    - ``author_user_id`` = the session user, so the audit trail cannot be
      forged even by an administrator posting under a public name;
    - ``display_name`` = the profile name for a user, the chosen support label
      for an administrator. Two administrators may therefore publish under
      different names while the internal author stays correct;
    - ``author_email`` = the author's real address. The user-facing response
      models simply do not carry it, so it cannot leak by accident.

    The reopen rule (ADR-0035): a new message on a ``resolved`` ticket sets the
    status back to ``in_progress``. A user who answers after the ticket was
    closed must see it reactivate rather than disappear into a closed thread.

    Attachments are optional and additive: the whole feature works without a
    single file. Files are streamed to disk first (they may be rejected on type
    or size); the database write happens only after every file was accepted, so
    a rejected upload never leaves a message behind.
    """
    now = utcnow()
    message = TicketMessage(
        ticket_id=ticket.id,
        author_user_id=author.id,
        author_type=author_type,
        display_name=display_name,
        author_email=author.email,
        body_markdown=body_markdown,
        created_at=now,
    )
    db.add(message)
    db.flush()

    uploads = [file for file in (files or []) if file is not None]
    if uploads:
        attachments.check_file_count(uploads)
        # One budget for the whole message: the per-file cap is enforced by
        # store_upload, this one caps their SUM.
        budget = attachments.ByteBudget()
        for upload in uploads:
            db.add(
                await attachments.store_upload(
                    upload, ticket.id, message.id, now, budget
                )
            )

    ticket.updated_at = now
    if ticket.status == STATUS_RESOLVED:
        ticket.status = STATUS_IN_PROGRESS
    db.add(ticket)
    db.commit()
    db.refresh(message)
    return message


def enforce_creation_limit(request: Request, user: User) -> None:
    """5 tickets per hour per user (configurable)."""
    enforce_user_rate_limit(request, user, "create", FEEDBACK_TICKETS_PER_HOUR)


def enforce_reply_limit(request: Request, user: User) -> None:
    """30 replies per hour per user (configurable)."""
    enforce_user_rate_limit(request, user, "reply", FEEDBACK_REPLIES_PER_HOUR)
