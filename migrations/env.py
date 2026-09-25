"""Alembic environment (migration stage 3, §11).

The schema is defined once — by the SQLAlchemy models (backend/models.py,
backend/models_auth.py). Autogenerate compares ``target_metadata`` against
the live database, so a reviewed migration is required for every model
change; nothing creates columns implicitly on PostgreSQL.

The database URL comes from the DATABASE_URL environment variable, never
from this file (secrets live in the environment, migration prompt §9).
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# The backend modules use flat imports; put backend/ on sys.path so the
# models import both from the application and from alembic CLI runs.
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: F401  (register cache tables on Base.metadata)
import models_auth  # noqa: F401  (register auth tables on Base.metadata)
from database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.exit(
            "DATABASE_URL is not set: alembic refuses to guess a database. "
            "Export DATABASE_URL (see .env.example) and retry."
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
