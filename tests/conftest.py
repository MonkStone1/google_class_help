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

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
# Must be set before `config` (imported below) resolves DATA_DIR. Set, not
# setdefault: tests drop all tables, so they must never be able to point at
# the real cache even if the env var is already set in the shell.
os.environ["GC_DASHBOARD_DATA_DIR"] = tempfile.mkdtemp(prefix="gc-dashboard-tests-")

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
