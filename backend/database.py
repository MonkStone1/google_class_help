from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_FILE

engine = create_engine(
    f"sqlite:///{DATABASE_FILE}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _record) -> None:
    """Tune SQLite for concurrent API reads + background sync writes (§1.6).

    Without WAL the background sync's commits block API readers with a
    periodic 'database is locked'; busy_timeout turns instant SQLITE_BUSY
    into a short wait; foreign_keys=ON makes the ondelete=CASCADE rules
    real (SQLite silently ignores them without the pragma).
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")  # readers are not blocked by the writer
    cursor.execute("PRAGMA busy_timeout=5000")  # wait instead of instant SQLITE_BUSY
    cursor.execute("PRAGMA foreign_keys=ON")  # enable the real CASCADE
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from models import (  # noqa: F401
        Course,
        CourseRole,
        CourseStudent,
        CourseWork,
        CourseWorkSubmission,
        StudentSubmission,
        SyncState,
    )

    Base.metadata.create_all(engine)
