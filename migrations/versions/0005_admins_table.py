"""The administrator registry (ADR-0036): one `admins` table.

Why the unique index on ``email`` exists — and why there is no foreign key:

- **The normalized e-mail is the identity.** It is stored trimmed and
  lower-cased (``config.normalize_email``), so the unique constraint is not
  "tidiness": it IS the rule "exactly one row per person". Without it the same
  human could be inserted twice under two spellings and the registry would
  contradict itself about who is an administrator.
- **There is deliberately NO foreign key to ``users``**, unlike the ticket
  tables of revision 0004. An administrator may be appointed before they have
  ever signed in, so at insert time there is frequently no ``users`` row to
  point at — and a FK would then either refuse the appointment or force one.
  It would also make ``maintenance.delete_user_data`` silently revoke the role
  of somebody whose account was removed. The row means "this address is an
  administrator", independent of whether that person has a local account yet;
  orphan rows are the intended state, not garbage to clean up.
- **The Super Admin has no row at all.** Their address lives in the
  ``SUPER_ADMIN_EMAIL`` environment value only, which is what makes "the Super
  Admin cannot be deleted through this API" a structural property rather than a
  check that could be forgotten.

The table has no index beyond that unique one: it is read by a single indexed
lookup per authorization decision (``admins.email``) and listed newest-first in
full, so any further index would answer no query the feature runs.

Nothing here touches an existing ticket table, so this revision applies both to
a clean database and to a production schema already at 0004, and its downgrade
is the reverse of its upgrade.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # The identity of an administrator, stored normalized. Unique: one row
        # per person (see the module docstring).
        sa.Column("email", sa.String(length=255), nullable=False),
        # Naive UTC, like every other timestamp of this schema.
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # No ForeignKey to users.id on purpose — see the module docstring.
    )
    op.create_index(op.f("ix_admins_email"), "admins", ["email"], unique=True)


def downgrade() -> None:
    # The table references nothing, so dropping the index and the table is
    # already in reverse dependency order.
    op.drop_index(op.f("ix_admins_email"), table_name="admins")
    op.drop_table("admins")