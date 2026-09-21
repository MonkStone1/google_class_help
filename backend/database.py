"""Database engine and session setup (migration stage 3).

Two datastores, one schema (§69):

- Hosted service: PostgreSQL via ``DATABASE_URL`` (§10, §71). The URL
  comes from the environment only — never a committed default. Missing
  DATABASE_URL in hosted mode is a startup error, not a silent SQLite
  fallback (fail closed: SQLite is not the hosted primary datastore).
- Desktop builds keep the local SQLite cache file exactly as before
  (ADR-0003); the SQLite pragmas below are registered for the SQLite
  dialect only.

Schema lifecycle (§11): SQLite keeps ``Base.metadata.create_all`` (the
cache is disposable, ADR-0003). PostgreSQL is versioned through Alembic
(``migrations/``): ``init_db`` runs ``alembic upgrade head`` so a fresh
installation gets the full schema and an existing one is migrated by
versioned, reviewable steps — never by silently creating missing columns.
"""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_FILE, HOSTED_MODE

DATABASE_URL_ENV_VAR = "DATABASE_URL"


def _build_engine() -> Engine:
    """SQLite engine (desktop) or PostgreSQL engine (hosted), by config."""
    url = os.environ.get(DATABASE_URL_ENV_VAR, "").strip()
    if url:
        # pool_pre_ping: drop connections killed by the server/idle timeouts
        # instead of failing a request with "server closed the connection".
        return create_engine(url, pool_pre_ping=True)
    if HOSTED_MODE:
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} is required in hosted mode "
            "(GC_DASHBOARD_HOSTED=1): PostgreSQL is the hosted primary "
            "datastore, there is no SQLite fallback."
        )
    return create_engine(
        f"sqlite:///{DATABASE_FILE}",
        connect_args={"check_same_thread": False},
    )


engine = _build_engine()


if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _record) -> None:
        """Tune SQLite for concurrent API reads + background sync writes (§1.6).

        Without WAL the background sync's commits block API readers with a
        periodic 'database is locked'; busy_timeout turns instant SQLITE_BUSY
        into a short wait; foreign_keys=ON makes the ondelete=CASCADE rules
        real (SQLite silently ignores them without the pragma — the
        user-scoped schema of stage 3 relies on those cascades). PostgreSQL
        enforces foreign keys natively; the pragma must never run there.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute(
            "PRAGMA journal_mode=WAL"
        )  # readers are not blocked by the writer
        cursor.execute(
            "PRAGMA busy_timeout=5000"
        )  # wait instead of instant SQLITE_BUSY
        cursor.execute("PRAGMA foreign_keys=ON")  # enable the real CASCADE
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _import_models() -> None:
    """Import every mapped model so ``Base.metadata`` is complete."""
    from models import (  # noqa: F401
        Course,
        CourseRole,
        CourseStudent,
        CourseWork,
        CourseWorkSubmission,
        StudentSubmission,
        SyncStatus,
    )
    from models_auth import (  # noqa: F401
        OAuthLoginState,
        OAuthToken,
        User,
        UserSession,
    )


def _upgrade_via_alembic() -> None:
    """Bring the schema to the latest versioned migration (§11)."""
    import alembic.command
    import alembic.config

    from path_config import PROJECT_DIR

    alembic_cfg = alembic.config.Config(str(PROJECT_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_DIR / "migrations"))
    alembic.command.upgrade(alembic_cfg, "head")


def init_db() -> None:
    """Create/upgrade the schema for the configured datastore.

    SQLite (desktop): ``create_all`` — the cache is disposable and was
    never migrated (ADR-0003). PostgreSQL (hosted production): versioned
    Alembic migrations only. This is the single schema entry point of the
    application; deployments never rely on implicit column creation.
    """
    _import_models()
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    else:
        _upgrade_via_alembic()
