"""Ticket feature (ADR-0035): feedback_tickets, ticket_messages, attachments.

Three tables, created after ``users`` and deleted with it:

    users ── feedback_tickets ── ticket_messages ── ticket_attachments
             (ON DELETE CASCADE all the way down)

Why each index exists — every one answers a query the feature actually runs,
and none is added "for symmetry":

- **ix_feedback_tickets_user_updated (user_id, updated_at)** — the "My tickets"
  list of ONE user, newest activity first. Both columns are in the predicate and
  the ordering, so the index serves the query end to end instead of filtering
  the whole table per user.
- **ix_feedback_tickets_status_updated (status, updated_at)** — the admin list
  and the dashboard, always filtered by status and ordered by activity. This is
  the index that keeps a growing ticket table cheap to triage.
- **ix_feedback_tickets_category (category)** — the admin category filter: a
  narrow, small index (four distinct values) that saves a full scan plus sort
  once the table outgrows a few thousand rows.
- **ix_ticket_messages_ticket_created (ticket_id, created_at)** — the
  conversation, read strictly in chronological order; it also serves the
  message-count aggregate of the list endpoints.
- **ix_ticket_messages_author (author_user_id)** — the administrator audit:
  "everything this account wrote", the question the ADMIN author type exists to
  answer.
- **ix_ticket_attachments_message (message_id)** — loading the files of one
  message, which every conversation read needs.

No uniqueness on ``(user_id, subject)``: the product does not promise that two
tickets cannot share a subject line, and a constraint invented for "tidiness"
would reject a legitimate second report of the same problem.

``ticket_attachments.ticket_id`` is denormalized from ``message_id`` on the
server (a client never sets it) so the authorization check of a download is one
indexed lookup instead of a join; it carries its own CASCADE so a deleted
message cannot leave an orphan row.

Attachment FILES are not part of this migration: they live on the appdata
volume under ``DATA_DIR/feedback/<ticket_id>/`` and are removed by the delete
endpoint, not by the database.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback_tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # The owner. CASCADE: deleting an account takes its tickets with it, so
        # a deleted user leaves no orphaned support history behind.
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        # Naive UTC, like every other timestamp of this schema.
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_feedback_tickets_user_updated",
        "feedback_tickets",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_feedback_tickets_status_updated",
        "feedback_tickets",
        ["status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_feedback_tickets_category",
        "feedback_tickets",
        ["category"],
        unique=False,
    )

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("feedback_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The REAL author, always the authenticated user. CASCADE for the same
        # reason as the ticket owner.
        sa.Column(
            "author_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_type", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("author_email", sa.String(length=255), nullable=True),
        # The Markdown SOURCE (untrusted), not rendered HTML.
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_messages_ticket_created",
        "ticket_messages",
        ["ticket_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ticket_messages_author",
        "ticket_messages",
        ["author_user_id"],
        unique=False,
    )

    op.create_table(
        "ticket_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey("ticket_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("feedback_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_attachments_message",
        "ticket_attachments",
        ["message_id"],
        unique=False,
    )


def downgrade() -> None:
    # Reverse dependency order: children first, so no statement runs while a
    # table it references is already gone.
    op.drop_index(
        op.f("ix_ticket_attachments_message"), table_name="ticket_attachments"
    )
    op.drop_table("ticket_attachments")
    op.drop_index(op.f("ix_ticket_messages_author"), table_name="ticket_messages")
    op.drop_index(
        op.f("ix_ticket_messages_ticket_created"), table_name="ticket_messages"
    )
    op.drop_table("ticket_messages")
    op.drop_index(op.f("ix_feedback_tickets_category"), table_name="feedback_tickets")
    op.drop_index(
        op.f("ix_feedback_tickets_status_updated"), table_name="feedback_tickets"
    )
    op.drop_index(
        op.f("ix_feedback_tickets_user_updated"), table_name="feedback_tickets"
    )
    op.drop_table("feedback_tickets")
