"""Per-user sync status: structured table replaces sync_state (stage 5).

Migration prompt §18 asks for structured per-user sync state
(``last_started_at``/``last_finished_at``/``last_success_at``/``last_error``
/``status``). The key/value ``sync_state`` table (one row per user and key,
stage 3) cannot express "is a run in flight" or "how often did it fail", so
it is replaced by one ``sync_status`` row per user; the scheduler
(sync_scheduler.py) and the worker container read it to decide who is due
and whether an account is paused for re-authorization (§63).

Data note: the two former keys (``last_sync``, ``last_sync_error``) are NOT
carried over — the values are a per-run bookkeeping cache that the next
sync repopulates; on PostgreSQL there is no production data yet (stage 3
migration has not run on a live database), and on desktop the schedule
fills the row at the next startup sync.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_status",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("sync_requested", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.drop_table("sync_state")


def downgrade() -> None:
    # Restores the stage-3 shape: per-user key/value bookkeeping without the
    # structured run state (the scheduler of stage 5 does not work against
    # this shape, so a downgrade also means disabling the worker).
    op.create_table(
        "sync_state",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "key"),
    )
    op.drop_table("sync_status")
