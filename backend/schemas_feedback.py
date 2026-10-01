"""Pydantic models of the ticket feature (ADR-0035).

A domain-specific module, like ``schemas.py`` holds the shared response models
of the Classroom cache: the feedback surface stays readable on its own and the
shared shapes are not diluted by tables nobody else uses.

Two shapes per row, deliberately:

- the plain ``*Out`` models a regular user may see — no author e-mail, no
  author id, nothing that would leak another account's identity;
- the ``Admin*`` models add the ``author_email``/``author_user_id`` an
  administrator legitimately needs (ADR-0035). There is no admin field on the
  user-facing models, so "forget to strip the e-mail" is not a possible bug.

Validation here is the *server-side* control (the frontend check is a
convenience): the closed category set, the trimmed non-empty subject, the
non-empty body and every length limit are enforced by these models and by
``feedback_attachments``, not by the UI.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

# Imported once at module level, not per validator: ``config`` imports only
# ``path_config``, so there is no cycle to dodge, and re-reading a module-level
# constant inside a hot validator on every request is pointless work.
from config import (
    FEEDBACK_MAX_DISPLAY_NAME_CHARS,
    FEEDBACK_MAX_MESSAGE_CHARS,
    FEEDBACK_MAX_SUBJECT_CHARS,
)


class FeedbackCategory(str, Enum):
    """The closed category set of a new ticket (never free text)."""

    suggestion = "suggestion"
    bug = "bug"
    problem = "problem"
    other = "other"


class FeedbackStatus(str, Enum):
    """The closed status set. A reply to ``resolved`` reopens it."""

    new = "new"
    in_progress = "in_progress"
    resolved = "resolved"


def _trimmed(value: str) -> str:
    """Strip surrounding whitespace; the inner text is preserved."""
    return value.strip()


class TicketCreateIn(BaseModel):
    """The ticket form: category + subject + the first message.

    No author fields exist here on purpose (§4.2 of the feature plan): identity
    comes from the session, and an unknown/forged field is simply ignored by
    Pydantic's default ``extra="ignore"`` instead of being able to change the
    stored author.
    """

    category: FeedbackCategory
    subject: str = Field(min_length=1, max_length=200)
    body_markdown: str = Field(min_length=1, max_length=20000)

    @field_validator("subject", "body_markdown")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        trimmed = _trimmed(value)
        if not trimmed:
            raise ValueError("must not be empty")
        return trimmed

    @field_validator("subject")
    @classmethod
    def _subject_length(cls, value: str) -> str:
        # The env knob may be lower than the model bound; re-check the effective
        # limit so raising GC_DASHBOARD_FEEDBACK_MAX_SUBJECT_CHARS is the only
        # way to make a longer subject acceptable.
        if len(value) > FEEDBACK_MAX_SUBJECT_CHARS:
            raise ValueError("subject is too long")
        return value

    @field_validator("body_markdown")
    @classmethod
    def _body_length(cls, value: str) -> str:
        if len(value) > FEEDBACK_MAX_MESSAGE_CHARS:
            raise ValueError("message is too long")
        return value


class ReplyCreateIn(BaseModel):
    """A user reply to an own ticket.

    The body accepts ``body_markdown`` and nothing else. A crafted payload with
    ``author_type``, ``author_user_id``, ``author_email`` or ``display_name`` is
    dropped by the default ``extra="ignore"`` — the stored identity always comes
    from the session, so impersonation is impossible rather than merely blocked.
    """

    body_markdown: str = Field(min_length=1, max_length=20000)

    @field_validator("body_markdown")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        trimmed = _trimmed(value)
        if not trimmed:
            raise ValueError("must not be empty")
        return trimmed

    @field_validator("body_markdown")
    @classmethod
    def _body_length(cls, value: str) -> str:
        if len(trimmed := _trimmed(value)) > FEEDBACK_MAX_MESSAGE_CHARS:
            raise ValueError("message is too long")
        return trimmed


class AdminReplyCreateIn(BaseModel):
    """An administrator's answer: the body plus the PUBLIC label to post under.

    ``display_name`` is the only author-ish input an admin sends, and it only
    changes how the message is *presented*. ``author_user_id``/``author_email``
    are still taken from the authenticated session — never from the request.
    """

    body_markdown: str = Field(min_length=1, max_length=20000)
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator("body_markdown")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        trimmed = _trimmed(value)
        if not trimmed:
            raise ValueError("must not be empty")
        return trimmed

    @field_validator("body_markdown")
    @classmethod
    def _body_length(cls, value: str) -> str:
        if len(value) > FEEDBACK_MAX_MESSAGE_CHARS:
            raise ValueError("message is too long")
        return value

    @field_validator("display_name")
    @classmethod
    def _name_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = _trimmed(value)
        if not trimmed:
            # An empty label is the same request as "no label": fall back to the
            # configured default rather than posting under an empty byline.
            return None
        if len(trimmed) > FEEDBACK_MAX_DISPLAY_NAME_CHARS:
            raise ValueError("display name is too long")
        return trimmed


class AdminStatusUpdateIn(BaseModel):
    """The status change — and ONLY the status (ADR-0035)."""

    status: FeedbackStatus


class AttachmentOut(BaseModel):
    """Metadata of one uploaded file; the bytes come from the download endpoint."""

    id: int
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class MessageOut(BaseModel):
    """One conversation message as a regular user may see it.

    No ``author_user_id`` and no ``author_email``: a regular user sees the
    PUBLIC byline of the conversation and nothing else.
    """

    id: int
    author_type: str
    display_name: str
    body_markdown: str
    created_at: datetime
    attachments: list[AttachmentOut] = Field(default_factory=list)


class TicketOut(BaseModel):
    """One ticket in a list (no conversation)."""

    id: int
    category: str
    subject: str
    status: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class TicketDetailOut(BaseModel):
    """One ticket with its whole conversation, as its OWNER sees it."""

    id: int
    category: str
    subject: str
    status: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = Field(default_factory=list)


class AdminMessageOut(MessageOut):
    """A message with the internal identity an administrator may read."""

    author_user_id: int
    author_email: str | None = None


class AdminTicketOut(TicketOut):
    """A ticket row for the admin list, with its owner."""

    user_id: int
    user_name: str | None = None
    user_email: str | None = None


class AdminTicketDetailOut(BaseModel):
    """Any ticket with the full conversation and the real author identities."""

    id: int
    category: str
    subject: str
    status: str
    created_at: datetime
    updated_at: datetime
    user_id: int
    user_name: str | None = None
    user_email: str | None = None
    messages: list[AdminMessageOut] = Field(default_factory=list)


class AdminTicketListOut(BaseModel):
    """A page of the admin list plus the total for the pagination control."""

    items: list[AdminTicketOut] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class FeedbackStatsOut(BaseModel):
    """Dashboard counters: the totals per status plus the closed/open split."""

    total: int
    new: int
    in_progress: int
    resolved: int
