"""Alembic environment (migration stage 3, §11).

The schema is defined once — by the SQLAlchemy models (backend/models.py,
backend/models_auth.py). Autogenerate compares ``target_metadata`` against
the live database, so a reviewed migration is required for every model
change; nothing creates columns implicitly on PostgreSQL.

The database URL comes from the DATABASE_URL environment variable, never
from this file (secrets live in the environment, migration prompt §9).
"""

import logging
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

# Alembic's own logging must never win over the hosting application.
#
# The web and worker processes call init_db() (database.py ->
# _upgrade_via_alembic) AFTER configuring their own logging (main.py /
# sync_worker.py logging.basicConfig), i.e. in a process that is NOT a bare
# `alembic` CLI run. Plain fileConfig() broke that twice over:
#
#   1. disable_existing_loggers=True (the default) sets .disabled=True on
#      every already-created application logger — sync_service,
#      sync_scheduler, sync_worker, api;
#   2. it also REPLACES the root configuration with alembic.ini's, i.e.
#      [logger_root] level=WARNING plus a stderr handler, so even INFO records
#      from the application were dropped.
#
# Together these made `docker logs` show the alembic lines (its logger is
# declared in alembic.ini and survives) and NOTHING from the application — no
# "Sync ok ... google_requests=... duration=...", no errors. A dead or slow
# sync was undiagnosable, which is how a stuck claim went unnoticed for an
# hour.
#
# So: apply alembic.ini only when nothing else has configured logging yet (the
# plain CLI case, where it is what the user wants). Inside the application,
# leave the root logger exactly as it was found.
if config.config_file_name is not None and not logging.getLogger().handlers:
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
