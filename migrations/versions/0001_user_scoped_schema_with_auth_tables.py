"""Initial schema: auth tables + user-scoped Classroom cache (stage 3).

Created by ``alembic revision --autogenerate`` from the SQLAlchemy models,
then reviewed by hand: users/sessions/oauth_tokens/oauth_login_states
(models_auth.py) and courses/coursework/submissions/course_roles/
course_students/coursework_submissions/sync_state (models.py), the latter
all keyed by ``user_id`` with composite FK cascades (migration prompt §10).

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The table/FK order is dependency order (users first, then courses,
    # coursework, then the child cache tables).
    op.create_table(
        "oauth_login_states",
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("browser_nonce", sa.String(length=64), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("redirect_to", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(
        op.f("ix_oauth_login_states_expires_at"),
        "oauth_login_states",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_subject", name="uq_users_provider_subject"
        ),
    )
    op.create_table(
        "courses",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("room", sa.String(), nullable=True),
        sa.Column("enrollment_state", sa.String(), nullable=True),
        sa.Column("course_state", sa.String(), nullable=True),
        sa.Column("teacher_names", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "id"),
    )
    op.create_table(
        "oauth_tokens",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_uri", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_sessions_session_token_hash"),
        "sessions",
        ["session_token_hash"],
        unique=True,
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "sync_state",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "key"),
    )
    op.create_table(
        "course_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "course_id"),
    )
    op.create_table(
        "course_students",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("student_id", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("photo_url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "course_id", "student_id"),
    )
    op.create_table(
        "coursework",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("work_type", sa.String(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("max_points", sa.Float(), nullable=True),
        sa.Column("alternate_link", sa.String(), nullable=True),
        sa.Column("materials", sa.JSON(), nullable=False),
        sa.Column("topic_id", sa.String(), nullable=True),
        sa.Column("creation_time", sa.DateTime(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "id"),
    )
    op.create_index(
        op.f("ix_coursework_due_at"), "coursework", ["due_at"], unique=False
    )
    op.create_index(
        "ix_coursework_user_course",
        "coursework",
        ["user_id", "course_id"],
        unique=False,
    )
    op.create_table(
        "coursework_submissions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("coursework_id", sa.String(), nullable=False),
        sa.Column("student_id", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("late", sa.Boolean(), nullable=False),
        sa.Column("assigned_points", sa.Float(), nullable=True),
        sa.Column("draft_points", sa.Float(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "coursework_id"],
            ["coursework.user_id", "coursework.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "course_id", "coursework_id", "student_id"),
    )
    op.create_index(
        "ix_cw_submission_user_course",
        "coursework_submissions",
        ["user_id", "course_id"],
        unique=False,
    )
    op.create_table(
        "submissions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("coursework_id", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("late", sa.Boolean(), nullable=False),
        sa.Column("assigned_points", sa.Float(), nullable=True),
        sa.Column("draft_points", sa.Float(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["courses.user_id", "courses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "coursework_id"],
            ["coursework.user_id", "coursework.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "course_id", "coursework_id"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # Reverse dependency order; indexes are dropped with their tables.
    op.drop_table("submissions")
    op.drop_index("ix_cw_submission_user_course", table_name="coursework_submissions")
    op.drop_table("coursework_submissions")
    op.drop_index("ix_coursework_user_course", table_name="coursework")
    op.drop_index(op.f("ix_coursework_due_at"), table_name="coursework")
    op.drop_table("coursework")
    op.drop_table("course_students")
    op.drop_table("course_roles")
    op.drop_table("sync_state")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_session_token_hash"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("oauth_tokens")
    op.drop_table("courses")
    op.drop_table("users")
    op.drop_index(
        op.f("ix_oauth_login_states_expires_at"), table_name="oauth_login_states"
    )
    op.drop_table("oauth_login_states")
