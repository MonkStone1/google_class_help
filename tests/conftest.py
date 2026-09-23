"""Shared test fixtures.

The app modules import each other as top-level packages, so ``backend/`` is
put on ``sys.path`` before anything is imported. ``GC_DASHBOARD_DATA_DIR``
points at a throwaway directory created before ``config`` is imported, so
tests never touch the real token or database (review §1.8).
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
# Must be set before `config` (imported below) resolves DATA_DIR. Set, not
# setdefault: tests drop all tables, so they must never be able to point at
# the real cache even if the env var is already set in the shell.
os.environ["GC_DASHBOARD_DATA_DIR"] = tempfile.mkdtemp(prefix="gc-dashboard-tests-")

# Hosted-mode configuration (migration stage 2). Hermetic dummy values set
# before `config`/`hosted_auth` are imported, so importing the modules never
# reads a developer's real Google client. The encryption key is a throwaway
# Fernet key generated for this test process only. Tests that need the
# hosted app build it explicitly with create_app(hosted=True).
os.environ.setdefault(
    "GC_DASHBOARD_OAUTH_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii")
)
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-web-client.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-web-client-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "https://gch.test/api/auth/callback")

# Host/Origin allow-list (migration stage 7, §28). Set, not setdefault: a
# stray value from the developer's shell must not silently change which Host
# names the app under test accepts. The hosted fixture serves gch.test; the
# desktop fixtures and Starlette's default "testserver" stay covered too.
os.environ["GC_DASHBOARD_ALLOWED_HOSTS"] = "gch.test,testserver,localhost,127.0.0.1"

from fastapi.testclient import TestClient

from database import Base, SessionLocal, engine
from main import app


@pytest.fixture()
def client():
    """A TestClient bound to the loopback host the local guard trusts.

    Used without a context manager on purpose: the lifespan (DB init +
    background sync) stays out of unit tests, keeping them hermetic and
    fast; the schema is created/dropped explicitly here instead.
    """
    Base.metadata.create_all(engine)
    test_client = TestClient(app, base_url="http://127.0.0.1")
    try:
        yield test_client
    finally:
        test_client.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def db(client):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def owner_id(db):
    """The desktop cache owner (migration stage 3): seeds need its id.

    Committed, not just flushed: the API under test opens its OWN SQLite
    connection, and an uncommitted write transaction in this fixture would
    make that connection fail with "database is locked" (or block it). The
    real desktop path commits the synthetic owner too (sync_service).
    """
    import ownership

    owner = ownership.local_owner_id(db)
    db.commit()
    return owner


@pytest.fixture()
def hosted_client():
    """The hosted-mode app (web OAuth + session gate), no lifespan.

    Built through the app factory instead of the module-level ``app`` so
    the desktop app used by the other tests is not polluted: hosted mode is
    selected per app, not by a process-wide env switch.
    """
    from main import create_app

    Base.metadata.create_all(engine)
    test_client = TestClient(create_app(hosted=True), base_url="https://gch.test")
    try:
        yield test_client
    finally:
        test_client.close()
        Base.metadata.drop_all(engine)
