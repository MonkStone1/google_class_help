# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Shared helpers for the ticket tests (ADR-0035).

Two things every feedback test needs and none should re-invent:

- ``_make_user`` / ``_add_session`` — the users of tests/test_user_isolation.py,
  unchanged: a ``users`` row and a session whose cookie holds the raw token.
- :func:`sign_in` — switch the hosted client to that user. Unsafe methods need
  ``Sec-Fetch-Site: same-origin`` because the CSRF check judges a request
  without an ``Origin`` by Fetch Metadata (test_stage8_coexistence.py).

``admin`` is a pair of factories, not constants (ADR-0036). The ordinary
administrators are ROWS of the ``admins`` table, so ``grant_admin`` inserts them;
the Super Admin is an environment value parsed once at import time, so
``as_super_admin`` monkeypatches the already-parsed ``config.SUPER_ADMIN_EMAIL``
(the same membership test the API uses) rather than re-reading or reloading the
environment.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import config
import hosted_auth
from models_auth import User, UserSession


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_user(db: Session, subject: str, email: str | None = None) -> User:
    """A Google-provisioned user with a profile (like a real sign-in)."""
    user = User(
        provider="google",
        provider_subject=subject,
        email=email if email is not None else f"{subject}@example.com",
        display_name=subject.replace("sub-", "").title(),
        created_at=_now(),
        updated_at=_now(),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.commit()
    return user


def make_local_owner(db: Session) -> User:
    """The desktop synthetic owner: ``email is None``, never an administrator."""
    user = User(
        provider="local",
        provider_subject="desktop",
        email=None,
        display_name=None,
        created_at=_now(),
        updated_at=_now(),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.commit()
    return user


def add_session(db: Session, user: User, raw_token: str) -> None:
    """A valid session row; only the SHA-256 of the token is stored."""
    now = _now()
    db.add(
        UserSession(
            session_token_hash=hosted_auth._sha256_hex(raw_token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(days=1),
            last_seen_at=now,
        )
    )
    db.commit()


def sign_in(client, token: str) -> None:
    """Make the hosted client act as the owner of ``token``."""
    client.cookies.set("gch_session", token)


SAFE_HEADERS = {"Sec-Fetch-Site": "same-origin"}


def grant_admin(db: Session, *emails: str) -> None:
    """Make ``emails`` ordinary administrators by inserting registry rows.

    Addresses are normalized exactly as the API does (``config.normalize_email``),
    so a test that writes ``"Boss@Example.com"`` exercises the same spelling the
    real insert would store — otherwise the fixture would create a row no
    session could ever match.

    COMMITS, and that is not optional: the API under test opens its OWN SQLite
    connection, so an uncommitted write in this session either blocks it or fails
    it with "database is locked". This is the same lesson as the ``owner_id``
    fixture in conftest.py.
    """
    from config import normalize_email
    from models_admin import Admin

    for email in emails:
        db.add(
            Admin(
                email=normalize_email(email),
                created_at=_now(),
            )
        )
    db.commit()


def as_super_admin(monkeypatch, email: str) -> None:
    """Point the Super Admin configuration at ``email`` for this test.

    Patches the already-parsed value, because config.py reads the environment
    once at import time and conftest deliberately pops the knob. ``monkeypatch``
    restores it afterwards, so one test cannot demote the Super Admin for the
    next one. Normalized here as well: ``resolve_role`` compares normalized
    values, so the fixture must store the same spelling.
    """
    from config import normalize_email

    monkeypatch.setattr(config, "SUPER_ADMIN_EMAIL", normalize_email(email))


def create_ticket(client, **overrides):
    """POST a ticket as the signed-in user.

    JSON when there are no files, multipart (like the real form) when there
    are — the endpoint accepts both shapes on the same URL.
    """
    files = overrides.pop("files", None)
    payload = {
        "category": overrides.pop("category", "problem"),
        "subject": overrides.pop("subject", "Grades look wrong"),
        "body_markdown": overrides.pop("body_markdown", "My average is 10."),
        **overrides,
    }
    if files:
        return client.post(
            "/api/feedback/tickets",
            data=payload,
            files=files,
            headers=SAFE_HEADERS,
        )
    return client.post("/api/feedback/tickets", json=payload, headers=SAFE_HEADERS)


def reply(client, ticket_id: int, body: str = "Any update?", **extra):
    """POST a reply as the signed-in user."""
    payload = {"body_markdown": body, **extra}
    return client.post(
        f"/api/feedback/tickets/{ticket_id}/messages",
        json=payload,
        headers=SAFE_HEADERS,
    )
