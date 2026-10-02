# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""The administrator management API (ADR-0036).

``/api/admin/admins`` is Super-Admin-only, and these tests pin the whole status
contract of D11 on it:

- **401** anonymous (the hosted session gate) and **403** for an authenticated
  non-administrator — with no registry data in the body either way;
- **403** for a PLAIN administrator on all three routes, which is the requirement
  that must never regress: they may answer tickets, not appoint colleagues;
- **201/200/204** for the Super Admin, **409** for a duplicate and for any attempt
  to add or remove the Super Admin, **422** for a malformed address, **404** for
  a row that is gone.

Every request is made through the API — no endpoint here accepts an identity
claim, and the last tests prove that a forged one changes nothing.
"""

import pytest
from feedback_helpers import (
    SAFE_HEADERS,
    add_session,
    as_super_admin,
    create_ticket,
    grant_admin,
    make_user,
    sign_in,
)
from sqlalchemy.orm import Session

from db.models.admins import Admin

# Both spellings are exercised throughout: an API path must never answer with the
# SPA shell (see test_admin_roles.test_the_registry_never_answers_with_the_spa_shell).
LIST_PATH = "/api/admin/admins"
CREATE_PATH = "/api/admin/admins/"


def _seed_people(db: Session) -> tuple[str, str, str]:
    """Alice (user), Boss (admin row) and Root (the configured Super Admin)."""
    alice = make_user(db, "sub-alice", email="alice@example.com")
    boss = make_user(db, "sub-boss", email="boss@example.com")
    root = make_user(db, "sub-root", email="root@example.com")
    add_session(db, alice, "raw-alice")
    add_session(db, boss, "raw-boss")
    add_session(db, root, "raw-root")
    grant_admin(db, "boss@example.com")
    return "raw-alice", "raw-boss", "raw-root"


# ------------------------------------------------------- 401 / 403 for the others


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", LIST_PATH, None),
        ("post", CREATE_PATH, {"email": "new.admin@example.com"}),
        ("delete", "/api/admin/admins/1", None),
    ],
)
def test_an_anonymous_caller_is_401(hosted_client, db: Session, method, path, payload):
    """Unauthenticated: the hosted session gate answers before the guard runs."""
    _seed_people(db)
    call = getattr(hosted_client, method)
    response = (
        call(path, json=payload, headers=SAFE_HEADERS)
        if payload is not None
        else call(path, headers=SAFE_HEADERS)
    )
    assert response.status_code == 401, response.text
    assert "boss@example.com" not in response.text


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", LIST_PATH, None),
        ("post", CREATE_PATH, {"email": "new.admin@example.com"}),
        ("delete", "/api/admin/admins/1", None),
    ],
)
def test_a_regular_user_is_403_and_learns_nothing(
    hosted_client, db: Session, method, path, payload
):
    """Authenticated but not an administrator: 403, never 404 (which would confirm)."""
    _seed_people(db)
    sign_in(hosted_client, "raw-alice")
    call = getattr(hosted_client, method)
    response = (
        call(path, json=payload, headers=SAFE_HEADERS)
        if payload is not None
        else call(path, headers=SAFE_HEADERS)
    )
    assert response.status_code == 403, response.text
    # No registry data leaked into the refusal.
    assert "boss@example.com" not in response.text
    assert db.query(Admin).count() == 1


def test_a_plain_admin_is_403_on_the_whole_registry(
    hosted_client, db: Session, monkeypatch
):
    """The requirement that must not regress: Admins cannot manage Admins."""
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-boss")

    assert hosted_client.get(LIST_PATH).status_code == 403
    created = hosted_client.post(
        CREATE_PATH,
        json={"email": "second.admin@example.com"},
        headers=SAFE_HEADERS,
    )
    assert created.status_code == 403, created.text
    row = db.query(Admin).filter_by(email="second.admin@example.com").one_or_none()
    assert row is None
    existing = db.query(Admin).filter_by(email="boss@example.com").one()
    assert hosted_client.delete(
        f"/api/admin/admins/{existing.id}", headers=SAFE_HEADERS
    ).status_code == 403
    assert db.query(Admin).filter_by(email="boss@example.com").count() == 1


def test_a_plain_admin_keeps_the_ticket_admin_surface(
    hosted_client, db: Session, monkeypatch
):
    """The two roles differ ONLY in registry management — tickets stay shared."""
    alice_token, boss_token, _root_token = _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, alice_token)
    create_ticket(hosted_client, subject="Grades are wrong")

    sign_in(hosted_client, boss_token)
    assert hosted_client.get("/api/admin/feedback/tickets").status_code == 200
    assert hosted_client.get("/api/admin/feedback/stats").status_code == 200


# ---------------------------------------------------------- the Super Admin works


def test_the_super_admin_lists_adds_and_deletes(
    hosted_client, db: Session, monkeypatch
):
    """The whole happy path: list, add, remove."""
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-root")

    listed = hosted_client.get(LIST_PATH)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["email"] for row in rows] == ["boss@example.com"]
    # The display name is DERIVED server-side (D8), never a stored field.
    assert rows[0]["name"] == "Boss"
    assert rows[0]["created_at"]

    created = hosted_client.post(
        CREATE_PATH,
        json={"email": "Test.Admin@Example.com"},
        headers=SAFE_HEADERS,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    # Normalized on the way in, so the row is stored in one spelling.
    assert body["email"] == "test.admin@example.com"
    assert body["name"] == "Test Admin"
    assert body["id"] in {row.id for row in db.query(Admin).all()}

    removed = hosted_client.delete(
        f"/api/admin/admins/{body['id']}", headers=SAFE_HEADERS
    )
    assert removed.status_code == 204
    assert removed.content == b""
    db.expire_all()
    assert db.query(Admin).filter_by(email="test.admin@example.com").count() == 0


# ------------------------------------------------------------- conflicts (409)


def test_a_duplicate_is_409_and_creates_no_second_row(
    hosted_client, db: Session, monkeypatch
):
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-root")

    response = hosted_client.post(
        CREATE_PATH,
        json={"email": "boss@example.com"},
        headers=SAFE_HEADERS,
    )
    assert response.status_code == 409, response.text
    assert db.query(Admin).filter_by(email="boss@example.com").count() == 1


@pytest.mark.parametrize(
    "spelling",
    ["boss@example.com", "Boss@Example.com", "  boss@example.com  "],
)
def test_normalization_happens_before_the_duplicate_check(
    hosted_client, db: Session, monkeypatch, spelling
):
    """Case and surrounding spaces are the SAME person, so they are a duplicate."""
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-root")

    response = hosted_client.post(
        CREATE_PATH, json={"email": spelling}, headers=SAFE_HEADERS
    )
    assert response.status_code == 409, response.text
    db.expire_all()
    assert db.query(Admin).count() == 1


def test_adding_the_super_admin_is_409_and_creates_no_row(
    hosted_client, db: Session, monkeypatch
):
    """The Super Admin is not a row: storing one would duplicate the authority."""
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-root")

    response = hosted_client.post(
        CREATE_PATH, json={"email": "root@example.com"}, headers=SAFE_HEADERS
    )
    assert response.status_code == 409, response.text
    assert db.query(Admin).filter_by(email="root@example.com").count() == 0


def test_deleting_the_super_admin_row_is_409(hosted_client, db: Session, monkeypatch):
    """Only reachable if the configuration CHANGED after the row was inserted.

    The POST endpoint refuses to create such a row, so this covers the one path
    that could produce it: a row inserted while the address was a normal
    administrator, and the environment later promoted it to Super Admin.
    """
    from datetime import datetime, timezone

    _seed_people(db)
    db.add(
        Admin(
            email="root@example.com",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    db.commit()
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-root")

    row = db.query(Admin).filter_by(email="root@example.com").one()
    response = hosted_client.delete(
        f"/api/admin/admins/{row.id}", headers=SAFE_HEADERS
    )
    assert response.status_code == 409, response.text
    assert db.query(Admin).filter_by(email="root@example.com").count() == 1


# -------------------------------------------------------- malformed input (422)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "not-an-email",
        "@",
        "boss@",
        "@example.com",
        "two@@example.com",
        "has space@example.com",
        "nodomain@localhost",
        "x" * 250 + "@example.com",
    ],
)
def test_a_malformed_address_is_422(hosted_client, db: Session, monkeypatch, value):
    """Hand-rolled validation (D7) — no new dependency, and no row is created."""
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-root")

    response = hosted_client.post(
        CREATE_PATH, json={"email": value}, headers=SAFE_HEADERS
    )
    assert response.status_code == 422, response.text
    assert db.query(Admin).count() == 1


# ------------------------------------------------------------ missing row (404)


def test_deleting_a_missing_row_is_404(hosted_client, db: Session, monkeypatch):
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-root")
    assert (
        hosted_client.delete("/api/admin/admins/999999", headers=SAFE_HEADERS).status_code
        == 404
    )


# ------------------------------------------------------- access changes take effect


def test_removing_an_administrator_revokes_them_immediately(
    hosted_client, db: Session, monkeypatch
):
    """The next authorization check after the DELETE is already the new truth."""
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")

    sign_in(hosted_client, "raw-boss")
    assert hosted_client.get("/api/admin/feedback/tickets").status_code == 200

    sign_in(hosted_client, "raw-root")
    row = db.query(Admin).filter_by(email="boss@example.com").one()
    assert (
        hosted_client.delete(
            f"/api/admin/admins/{row.id}", headers=SAFE_HEADERS
        ).status_code
        == 204
    )

    sign_in(hosted_client, "raw-boss")
    assert hosted_client.get("/api/admin/feedback/tickets").status_code == 403
    assert hosted_client.get("/api/me").json()["is_admin"] is False


def test_a_row_written_straight_to_the_database_changes_authorization(
    hosted_client, db: Session
):
    """Authorization follows the table, with no restart and no cache to clear."""
    _seed_people(db)
    sign_in(hosted_client, "raw-alice")
    assert hosted_client.get("/api/admin/feedback/tickets").status_code == 403

    grant_admin(db, "alice@example.com")
    assert hosted_client.get("/api/admin/feedback/tickets").status_code == 200

    db.query(Admin).filter_by(email="alice@example.com").delete()
    db.commit()
    assert hosted_client.get("/api/admin/feedback/tickets").status_code == 403


# --------------------------------------------------------- nothing can escalate


def test_no_request_field_can_grant_or_escalate_a_role(
    hosted_client, db: Session, monkeypatch
):
    """D3: identity comes from the session, never from the request.

    Every plausible carrier is tried at once — body fields, query parameters and
    headers — because the point is that NONE of them is ever read.
    """
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-alice")

    forged_body = hosted_client.post(
        CREATE_PATH,
        json={
            "email": "root@example.com",
            "is_admin": True,
            "is_super_admin": True,
            "id": 1,
            "name": "Root",
        },
        headers=SAFE_HEADERS,
    )
    assert forged_body.status_code == 403, forged_body.text
    assert db.query(Admin).count() == 1

    # A query parameter cannot promote the caller either.
    assert (
        hosted_client.get(
            f"{LIST_PATH}?email=root@example.com&is_super_admin=true"
        ).status_code
        == 403
    )
    # Nor can a header.
    assert (
        hosted_client.get(
            LIST_PATH, headers={**SAFE_HEADERS, "X-Admin": "root@example.com"}
        ).status_code
        == 403
    )
    assert hosted_client.get("/api/me").json()["is_super_admin"] is False


def test_an_unknown_field_is_ignored_not_honoured(
    hosted_client, db: Session, monkeypatch
):
    """``extra="ignore"``: a forged ``name`` cannot smuggle in a display name."""
    _seed_people(db)
    as_super_admin(monkeypatch, "root@example.com")
    sign_in(hosted_client, "raw-root")

    response = hosted_client.post(
        CREATE_PATH,
        json={"email": "new.admin@example.com", "name": "Forged Name"},
        headers=SAFE_HEADERS,
    )
    assert response.status_code == 201, response.text
    # The name in the answer is the DERIVED one (D8), not the submitted one.
    assert response.json()["name"] == "New Admin"
    assert db.query(Admin).filter_by(email="new.admin@example.com").one().email