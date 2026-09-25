"""Stage-9 index review: composite session index, no blind indexes (§68).

The user-scoped schema of stage 3 already gives every cache table an index
whose leftmost column is ``user_id`` (the primary keys start with it, plus
``ix_coursework_user_course`` / ``ix_cw_submission_user_course``), so the
candidate list of §68 is satisfied without adding anything:

    courses(user_id, id)                                PK
    coursework(user_id, id)                             PK
    coursework(user_id, course_id)                      ix_coursework_user_course
    submissions(user_id, course_id, coursework_id)      PK
    course_roles(user_id, course_id)                    PK
    course_students(user_id, course_id, student_id)     PK
    coursework_submissions(user_id, course_id, ...)     ix_cw_submission_user_course

The one real gap was ``sessions``: the retention sweep and the per-user
session listing select on ``(user_id, expires_at)``, while the table had two
separate single-column indexes. Revision 0003 adds the composite index and
drops the now-redundant ``ix_sessions_user_id`` (its column is the
composite's leftmost prefix). No other index was added — §68 asks for
indexes justified by query patterns, not for a blind list.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_sessions_user_expires",
        "sessions",
        ["user_id", "expires_at"],
        unique=False,
    )
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")


def downgrade() -> None:
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.drop_index("ix_sessions_user_expires", table_name="sessions")
