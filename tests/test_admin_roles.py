# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Role resolution and the Super Admin configuration (ADR-0036).

The contract these tests pin:

- roles come from the validated session's e-mail and nothing else (D3);
- the Super Admin is configured ONLY through ``SUPER_ADMIN_EMAIL``, and the
  configuration fails CLOSED: unset, blank or ``@``-less means nobody (D6);
- ordinary administrators come from the ``admins`` table ONLY — the ADR-0035
  ``ADMIN_EMAILS`` allow-list is gone and grants nothing anywhere (D5);
- the frontend learns two booleans and never an address (D4).

The API-level enforcement (403 for a plain user, 403 for a plain administrator
on the registry) lives in test_feedback_admin_auth.py and
test_admins_management_api.py.
"""

import pytest
from feedback_helpers import (
    add_session,
    as_super_admin,
    grant_admin,
    make_local_owner,
    make_user,
    sign_in,
)
from sqlalchemy.orm import Session

from auth import roles
from auth.roles import (
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_USER,
    display_name_from_email,
    resolve_role,
)
from core.config import normalize_email


def _role_of(db: Session, email: str | None) -> str:
    return resolve_role(db, email)


# --------------------------------------------------------------- the three roles


def test_the_super_admin_is_recognized_from_the_environment(db: Session, monkeypatch):
    """The configured address is the Super Admin — and nothing else needs to be."""
    as_super_admin(monkeypatch, "boss@example.com")
    assert _role_of(db, "boss@example.com") == ROLE_SUPER_ADMIN
    # They are also an administrator: ``is_admin`` means "any administrator".
    assert roles.is_admin_email(db, "boss@example.com") is True


def test_a_registry_row_is_an_administrator_not_a_super_admin(db: Session, monkeypatch):
    """A row grants exactly one role: ADMIN. Only the environment grants SUPER."""
    as_super_admin(monkeypatch, "root@example.com")
    grant_admin(db, "boss@example.com")

    assert _role_of(db, "boss@example.com") == ROLE_ADMIN
    assert roles.is_admin_email(db, "boss@example.com") is True
    assert _role_of(db, "root@example.com") == ROLE_SUPER_ADMIN


def test_a_normal_user_is_neither_admin_nor_super_admin(db: Session, monkeypatch):
    """The default for anybody with no row and no configuration."""
    as_super_admin(monkeypatch, "root@example.com")
    assert _role_of(db, "alice@example.com") == ROLE_USER
    assert roles.is_admin_email(db, "alice@example.com") is False


# --------------------------------------------------------- normalization rules


@pytest.mark.parametrize(
    "spelling",
    [
        "Boss@Example.com",
        "BOSS@EXAMPLE.COM",
        "boss@example.com",
        "  boss@example.com  ",
    ],
)
def test_the_comparison_is_case_insensitive_and_trims(db: Session, monkeypatch, spelling):
    """One account, one role: case and surrounding spaces never split it."""
    as_super_admin(monkeypatch, "boss@example.com")
    assert _role_of(db, spelling) == ROLE_SUPER_ADMIN

    as_super_admin(monkeypatch, "root@example.com")
    grant_admin(db, "boss@example.com")
    assert _role_of(db, spelling) == ROLE_ADMIN


@pytest.mark.parametrize("configured", ["", "   ", "not-an-email", "@", "boss", "boss@"])
def test_an_unusable_super_admin_configuration_admits_nobody(
    monkeypatch, configured, db: Session
):
    """Fail closed (D6): each of these means NOBODY, notably not a real address.

    ``boss@`` contains an "@", so it is exactly the kind of half-typed value that
    could otherwise half-match a real address. A malformed configuration is
    treated as a MISSING one, so a typo in the deployment can never widen access.
    """
    from core import config

    monkeypatch.setattr(config, "SUPER_ADMIN_EMAIL", normalize_email(configured))
    for candidate in ("boss@example.com", "admin@example.com", "root@example.com"):
        assert roles.is_super_admin_email(candidate) is False
        assert roles.is_admin_email(db, candidate) is False


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_an_unset_configuration_is_no_super_admin(monkeypatch, configured):
    """``None`` is the shipped default: the feature exists, nobody is Super."""
    from core import config

    monkeypatch.setattr(config, "SUPER_ADMIN_EMAIL", configured)
    assert roles.is_super_admin_email("boss@example.com") is False


def test_the_desktop_local_owner_is_never_an_administrator(db: Session, monkeypatch):
    """The desktop owner has ``email is None`` and cannot reach the admin surface."""
    as_super_admin(monkeypatch, "root@example.com")
    grant_admin(db, "boss@example.com")
    owner = make_local_owner(db)

    assert owner.email is None
    assert _role_of(db, owner.email) == ROLE_USER
    assert _role_of(db, "") == ROLE_USER


# ------------------------------------------- the deleted allow-list stays dead


def test_admin_emails_no_longer_grants_anything(db: Session, monkeypatch):
    """D5: the ADR-0035 variable is deleted, and a leftover value changes nothing.

    ``config`` no longer defines ``ADMIN_EMAILS`` at all, and a value left in the
    environment (an old ``.env`` on a deployment, a shell export on a laptop) is
    read by nobody — both halves are asserted here, so a future "compatibility
    shim" cannot creep back in unnoticed.
    """
    from core import config

    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com")
    assert not hasattr(config, "ADMIN_EMAILS")

    boss = make_user(db, "sub-boss", email="boss@example.com")
    add_session(db, boss, "raw-boss")
    assert _role_of(db, boss.email) == ROLE_USER
    assert roles.is_admin_email(db, boss.email) is False


# ---------------------------------------------------------- derived display name


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("john.doe@gmail.com", "John Doe"),
        ("john_doe@gmail.com", "John Doe"),
        ("john-doe@gmail.com", "John Doe"),
        ("john@gmail.com", "John"),
    ],
)
def test_the_display_name_is_derived_from_the_address(email, expected):
    """D8: deterministic, stored nowhere, and identical for every spelling."""
    assert display_name_from_email(email) == expected


def test_the_display_name_is_case_insensitive_too():
    """The derivation runs on the normalized address, like every other rule."""
    assert display_name_from_email("John.DOE@Gmail.com") == "John Doe"


# ----------------------------------------- one Session per request (dependency cache)


def test_the_guard_and_the_handler_share_one_session(
    hosted_client, db: Session, monkeypatch
):
    """FastAPI caches a dependency per request: the guard's ``db`` IS the handler's.

    This is load-bearing, not trivia — ``require_admin`` resolves its own
    ``get_db`` session, and a SECOND resolution would put the guard's read of
    ``admins`` on a different connection than the handler's own reads (and leak
    one connection per admin request).

    Counted at ``database.SessionLocal``, the single factory ``get_db`` calls.
    ``main.py``'s session gate holds its own module-level binding, so it is NOT
    counted here: what remains is exactly the request's dependency sessions.
    One request, one session — that is the cache working.
    """
    from db import session as database

    opened: list[object] = []
    real_session_local = database.SessionLocal

    def _recording_session_local(*args, **kwargs):
        session = real_session_local(*args, **kwargs)
        opened.append(session)
        return session

    as_super_admin(monkeypatch, "root@example.com")
    grant_admin(db, "boss@example.com")
    boss = make_user(db, "sub-boss2", email="boss@example.com")
    add_session(db, boss, "raw-boss2")
    sign_in(hosted_client, "raw-boss2")

    monkeypatch.setattr(database, "SessionLocal", _recording_session_local)
    opened.clear()
    response = hosted_client.get("/api/admin/feedback/tickets")
    assert response.status_code == 200
    assert len(opened) == 1, "the guard and the handler did not share one session"


# ------------------------------------------------- nothing leaks to the frontend


def test_the_super_admin_address_never_reaches_a_response(
    hosted_client, db: Session, monkeypatch
):
    """D4: the frontend learns two booleans, never somebody else's address.

    Read as a PLAIN ADMIN, not as the Super Admin: the configured address is
    ``root@example.com`` while the caller is ``boss@example.com``, so any
    appearance of it would be a leak of the configuration rather than the
    caller's own identity (which ``UserOut.email`` obviously does return).
    """
    as_super_admin(monkeypatch, "root@example.com")
    grant_admin(db, "boss@example.com")
    root = make_user(db, "sub-root", email="root@example.com")
    boss = make_user(db, "sub-boss", email="boss@example.com")
    add_session(db, root, "raw-root")
    add_session(db, boss, "raw-boss")
    sign_in(hosted_client, "raw-boss")

    for path in ("/api/auth/status", "/api/me", "/openapi.json"):
        body = hosted_client.get(path)
        assert body.status_code == 200, path
        assert "root@example.com" not in body.text, path

    # The registry list is refused to a plain admin, and even the Super Admin's
    # own list would never contain them: they have no row at all.
    refused = hosted_client.get("/api/admin/admins")
    assert refused.status_code == 403
    assert "root@example.com" not in refused.text

    sign_in(hosted_client, "raw-root")
    listed = hosted_client.get("/api/admin/admins").json()
    assert [row["email"] for row in listed] == ["boss@example.com"]


def test_the_role_flags_agree_with_the_guards(hosted_client, db: Session, monkeypatch):
    """What ``/api/me`` reports is what the API enforces — one resolver, one truth."""
    as_super_admin(monkeypatch, "root@example.com")
    grant_admin(db, "boss@example.com")
    alice = make_user(db, "sub-alice", email="alice@example.com")
    boss = make_user(db, "sub-boss", email="boss@example.com")
    root = make_user(db, "sub-root", email="root@example.com")
    for user, token in ((alice, "raw-a"), (boss, "raw-b"), (root, "raw-r")):
        add_session(db, user, token)

    expected = {
        "raw-a": (False, False),
        "raw-b": (True, False),
        "raw-r": (True, True),
    }
    for token, (is_admin, is_super_admin) in expected.items():
        sign_in(hosted_client, token)
        me = hosted_client.get("/api/me").json()
        assert (me["is_admin"], me["is_super_admin"]) == (is_admin, is_super_admin)
        assert hosted_client.get("/api/auth/status").json()["user"] == me

    # And the guards agree with the flags they published.
    sign_in(hosted_client, "raw-a")
    assert hosted_client.get("/api/admin/feedback/tickets").status_code == 403
    sign_in(hosted_client, "raw-b")
    assert hosted_client.get("/api/admin/feedback/tickets").status_code == 200
    assert hosted_client.get("/api/admin/admins").status_code == 403
    sign_in(hosted_client, "raw-r")
    assert hosted_client.get("/api/admin/admins").status_code == 200


@pytest.mark.parametrize("path", ["/api/admin/admins", "/api/admin/admins/"])
def test_the_registry_never_answers_with_the_spa_shell(hosted_client, db: Session, path):
    """An unauthorized probe must be refused, not served the HTML fallback.

    With the route registered under ``"/"`` only, the un-slashed path matched
    nothing, skipped the guard and fell through to the static SPA mount — which
    answers 200 with ``index.html``. That is exactly the failure D11 forbids: an
    API path answering with a page instead of the documented status code. Both
    spellings are pinned here.
    """
    alice = make_user(db, "sub-alice", email="alice@example.com")
    add_session(db, alice, "raw-alice")
    sign_in(hosted_client, "raw-alice")

    response = hosted_client.get(path)
    assert response.status_code == 403, response.text
    assert "<!doctype html>" not in response.text.lower()