"""Support tickets and their conversation (ADR-0035).

Separate from ``models.py``/``models_auth.py`` on purpose, following the
``models_auth.py`` precedent: a new domain gets its own models module instead of
more classes appended to the cache schema.

    users ─┬─ feedback_tickets ─┬─ ticket_messages ── ticket_attachments
           │                    └─ ticket_attachments (denormalized ticket_id)

Three invariants:

- **Ownership is structural.** Every ticket carries ``user_id`` → ``users.id``
  with ``ON DELETE CASCADE``, so deleting an account removes exactly its own
  tickets (maintenance.delete_user_data) and never anyone else's. Reads filter
  on ``user_id`` inside the same statement (never fetch-then-check), so another
  user's ticket is indistinguishable from a missing one (§23/§12).
- **The author is the authenticated user.** ``author_user_id`` is always the
  session user, never a value from the request body; ``author_type`` (``USER`` /
  ``ADMIN``) is the machine-readable distinction the UI styles on, while
  ``display_name`` is only the PUBLIC label of the message (an administrator may
  post under a chosen support name). ``author_email`` is filled for
  administrators and never leaves the admin API.
- **Markdown is stored as source.** ``body_markdown`` holds the untrusted
  Markdown exactly as typed; rendering is the frontend's job and it sanitizes
  (rehype-sanitize). The backend never stores or serves rendered HTML.

Timestamps are naive UTC, like every other table of this schema (models.py).
Attachment FILES live on the ``appdata`` volume under ``DATA_DIR/feedback`` and
are served only through the authorized download endpoint — there is no static
mount for uploads.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base

# The closed status set (stored lowercase).
STATUS_NEW = "new"
STATUS_IN_PROGRESS = "in_progress"
STATUS_RESOLVED = "resolved"
FEEDBACK_STATUSES = (STATUS_NEW, STATUS_IN_PROGRESS, STATUS_RESOLVED)

# The closed author types: a regular user and an administrator answering under a
# public support name. Never inferred from a name or an e-mail in the UI.
AUTHOR_USER = "USER"
AUTHOR_ADMIN = "ADMIN"


class FeedbackTicket(Base):
    """One support ticket opened by one application user."""

    __tablename__ = "feedback_tickets"
    __table_args__ = (
        # "My tickets", newest activity first, scoped to one user.
        Index("ix_feedback_tickets_user_updated", "user_id", "updated_at"),
        # The admin list/dashboard: filtered by status, newest activity first.
        Index("ix_feedback_tickets_status_updated", "status", "updated_at"),
        # The admin category filter.
        Index("ix_feedback_tickets_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The owner. CASCADE: account deletion takes the tickets with it.
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # suggestion | bug | problem | other — validated server-side.
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    # new | in_progress | resolved. A reply to a resolved ticket reopens it
    # (in_progress) — decided in ADR-0035 so a follow-up is never swallowed.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_NEW)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Bumped on every message; drives the "sorted by last activity" ordering.
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TicketMessage(Base):
    """One message of a ticket conversation (question or answer)."""

    __tablename__ = "ticket_messages"
    __table_args__ = (
        # The conversation, always chronological.
        Index("ix_ticket_messages_ticket_created", "ticket_id", "created_at"),
        # Administrator audit: everything one author wrote.
        Index("ix_ticket_messages_author", "author_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("feedback_tickets.id", ondelete="CASCADE"), nullable=False
    )
    # The REAL author — always the authenticated user, taken from the session.
    author_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # USER | ADMIN — the distinction the UI styles on (never the name/email).
    author_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # PUBLIC label: the profile name for a user, the chosen support name for an
    # administrator.
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Real address, administrators only; never sent to a regular user.
    author_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The Markdown SOURCE, untrusted and unsanitized on purpose — rendering is
    # sanitized in the frontend.
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TicketAttachment(Base):
    """One uploaded file of one message.

    ``ticket_id`` is denormalized from ``message_id`` on the server (a client
    never sets it) so the authorization check of a download is a single indexed
    lookup instead of a join through the message.
    """

    __tablename__ = "ticket_attachments"
    __table_args__ = (Index("ix_ticket_attachments_message", "message_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ticket_messages.id", ondelete="CASCADE"), nullable=False
    )
    # Kept consistent with the parent message; CASCADE as well so a deleted
    # message cannot leave an orphan row behind.
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("feedback_tickets.id", ondelete="CASCADE"), nullable=False
    )
    # Server-generated file name (uuid4 + the sniffed type's extension). The
    # uploaded name is display metadata only and never reaches the filesystem.
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Sanitized original name, for display in the UI.
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Sniffed server-side, never the client's Content-Type.
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    # Server-measured byte count.
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
