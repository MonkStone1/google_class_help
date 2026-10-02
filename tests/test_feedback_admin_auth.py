# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Administrator authorization and the admin surface (ADR-0035/ADR-0036).

This file is the ENFORCEMENT contract of the ticket admin API:

- a regular authenticated user gets 403 from EVERY admin endpoint, an
  administrator gets 200, and the desktop local owner (no e-mail) is never an
  administrator;
- nothing here trusts the frontend: the flags the UI reads are a UX convenience,
  the dependency is the control.

The role RULES (who is an administrator, what ``SUPER_ADMIN_EMAIL`` does when it
is unset, how the name is derived) live in test_admin_roles.py, and the
Super-Admin-only management surface in test_admins_management_api.py.
"""

import pytest
from feedback_helpers import (
    SAFE_HEADERS,
    add_session,
    create_ticket,
    grant_admin,
    make_user,
    reply,
    sign_in,
)
from sqlalchemy.orm import Session

from db.models.feedback import AUTHOR_ADMIN, STATUS_RESOLVED


def _seed(hosted_client, db: Session):
    """Alice's ticket, plus an administrator session (`boss`)."""
    alice = make_user(db, "sub-alice")
    boss = make_user(db, "sub-boss", email="boss@example.com")
    add_session(db, alice, "raw-alice")
    add_session(db, boss, "raw-boss")
    sign_in(hosted_client, "raw-alice")
    ticket_id = create_ticket(hosted_client, subject="Grades are wrong").json()["id"]
    return alice, boss, ticket_id


# -------------------------------------------------------- the empty registry
#
# The ADR-0035 ``ADMIN_EMAILS`` parsing tests lived here and are GONE (D5): the
# environment variable no longer grants administrator access anywhere, so there
# is nothing to parse. What remains in this file is the enforcement contract;
# the role/configuration rules themselves are covered by test_admin_roles.py and
# the management surface by test_admins_management_api.py.


def test_an_empty_registry_admits_nobody(hosted_client, db):
    """The default of the whole feature: no rows, no configuration, no admin.

    Neither a row in ``admins`` nor a ``SUPER_ADMIN_EMAIL`` exists yet, so the
    session that exists (a real Google user) is answered 403 — the API must not
    treat "nobody was appointed yet" as "everybody is".
    """
    from core import config
    from db.models.admins import Admin

    assert config.SUPER_ADMIN_EMAIL is None
    assert db.query(Admin).count() == 0
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")
    assert (
        hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}").status_code == 403
    )


def test_the_registry_membership_test_is_case_insensitive(hosted_client, db):
    """A row stored in one spelling admits the session's other spelling.

    The registry stores the normalized address (``Admin@Example.com`` →
    ``admin@example.com``) and the session address is normalized on the way in,
    so a case difference must never split one account into an administrator and
    a stranger.
    """
    grant_admin(db, "Boss@Example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)  # boss@example.com
    sign_in(hosted_client, "raw-boss")
    assert (
        hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}").status_code == 200
    )


# ------------------------------------------------------------- 403 for users


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/admin/feedback/tickets", None),
        ("get", "/api/admin/feedback/stats", None),
        ("get", "/api/admin/feedback/tickets/1", None),
        ("post", "/api/admin/feedback/tickets/1/messages", {"body_markdown": "hi"}),
        ("patch", "/api/admin/feedback/tickets/1", {"status": "resolved"}),
        ("delete", "/api/admin/feedback/tickets/1", None),
    ],
)
def test_a_regular_user_is_403_on_every_admin_endpoint(
    hosted_client, db, monkeypatch, method, path, payload
):
    """403, not 404 and not 401: the user IS signed in, just not an admin."""
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    path = path.replace("/1", f"/{ticket_id}")

    call = getattr(hosted_client, method)
    response = (
        call(path, json=payload, headers=SAFE_HEADERS)
        if payload is not None
        else call(path, headers=SAFE_HEADERS)
    )
    assert response.status_code == 403, response.text


def test_a_regular_user_cannot_delete_anything(hosted_client, db, monkeypatch):
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-alice")

    response = hosted_client.delete(
        f"/api/admin/feedback/tickets/{ticket_id}", headers=SAFE_HEADERS
    )
    assert response.status_code == 403
    # The refused request changed nothing: the owner still sees the ticket.
    assert hosted_client.get(f"/api/feedback/tickets/{ticket_id}").status_code == 200


def test_a_regular_user_never_becomes_an_admin_by_sending_an_email(
    hosted_client, db, monkeypatch
):
    """§2.6: no address in the request, in any field, grants anything."""
    grant_admin(db, "boss@example.com")
    _seed(hosted_client, db)
    sign_in(hosted_client, "raw-alice")
    response = hosted_client.get(
        "/api/admin/feedback/tickets?email=boss@example.com&is_admin=true"
    )
    assert response.status_code == 403


# --------------------------------------------------------------- admin reads


def test_an_admin_lists_all_tickets_with_the_owner(hosted_client, db, monkeypatch):
    grant_admin(db, "boss@example.com")
    alice, _boss, _first = _seed(hosted_client, db)

    bob = make_user(db, "sub-bob2", email="bob2@example.com")
    add_session(db, bob, "raw-bob2")
    sign_in(hosted_client, "raw-bob2")
    create_ticket(hosted_client, subject="Second report", category="bug")

    sign_in(hosted_client, "raw-boss")
    body = hosted_client.get("/api/admin/feedback/tickets").json()
    assert body["total"] == 2
    assert {item["subject"] for item in body["items"]} == {
        "Grades are wrong",
        "Second report",
    }
    # The admin projection carries the contact details of the ticket owners.
    assert {item["user_email"] for item in body["items"]} == {
        "sub-alice@example.com",
        "bob2@example.com",
    }
    assert {item["user_id"] for item in body["items"]} == {alice.id, bob.id}


def test_an_admin_filters_by_status_and_category_and_searches(
    hosted_client, db, monkeypatch
):
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)

    carol = make_user(db, "sub-carol")
    add_session(db, carol, "raw-carol")
    sign_in(hosted_client, "raw-carol")
    # A DIFFERENT body, so "q" on a message proves it searches bodies and not
    # just subjects.
    second = create_ticket(
        hosted_client,
        subject="Dark theme please",
        category="suggestion",
        body_markdown="Could the sidebar be darker?",
    ).json()["id"]

    sign_in(hosted_client, "raw-boss")
    assert (
        hosted_client.get("/api/admin/feedback/tickets?status=new").json()["total"] == 2
    )
    assert (
        hosted_client.get("/api/admin/feedback/tickets?status=resolved").json()["total"]
        == 0
    )
    assert (
        hosted_client.get("/api/admin/feedback/tickets?category=problem").json()[
            "total"
        ]
        == 1
    )
    assert (
        hosted_client.get("/api/admin/feedback/tickets?category=bug").json()["total"]
        == 0
    )
    assert (
        hosted_client.get("/api/admin/feedback/tickets?category=suggestion").json()[
            "total"
        ]
        == 1
    )
    # q matches the subject …
    found = hosted_client.get("/api/admin/feedback/tickets?q=dark+theme").json()
    assert [item["id"] for item in found["items"]] == [second]
    # … and a message body.
    found = hosted_client.get("/api/admin/feedback/tickets?q=average").json()
    assert [item["id"] for item in found["items"]] == [ticket_id]
    # A search nobody matches is simply empty.
    assert (
        hosted_client.get("/api/admin/feedback/tickets?q=nothing").json()["total"] == 0
    )


def test_an_unknown_status_filter_is_422(hosted_client, db, monkeypatch):
    grant_admin(db, "boss@example.com")
    _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")
    assert (
        hosted_client.get("/api/admin/feedback/tickets?status=whatever").status_code
        == 422
    )


def test_the_admin_list_paginates(hosted_client, db, monkeypatch):
    grant_admin(db, "boss@example.com")
    alice = make_user(db, "sub-alice")
    boss = make_user(db, "sub-boss", email="boss@example.com")
    add_session(db, alice, "raw-alice")
    add_session(db, boss, "raw-boss")
    sign_in(hosted_client, "raw-alice")
    for index in range(3):
        create_ticket(hosted_client, subject=f"Report {index}")

    sign_in(hosted_client, "raw-boss")
    first_page = hosted_client.get(
        "/api/admin/feedback/tickets?limit=2&offset=0"
    ).json()
    assert len(first_page["items"]) == 2
    assert first_page["total"] == 3
    second_page = hosted_client.get(
        "/api/admin/feedback/tickets?limit=2&offset=2"
    ).json()
    assert len(second_page["items"]) == 1
    assert {item["id"] for item in first_page["items"]}.isdisjoint(
        {item["id"] for item in second_page["items"]}
    )


def test_an_admin_reads_any_ticket_with_the_author_email(
    hosted_client, db, monkeypatch
):
    """The admin projection carries the real identities a support answer needs."""
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)

    sign_in(hosted_client, "raw-boss")
    body = hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}")
    assert body.status_code == 200
    payload = body.json()
    assert payload["user_email"] == "sub-alice@example.com"
    # The admin projection DOES carry the real author identity of each message.
    assert payload["messages"][0]["author_email"] == "sub-alice@example.com"
    assert payload["messages"][0]["author_user_id"] is not None


# -------------------------------------------------------------- admin writes


def test_an_admin_reply_records_the_authenticated_author_and_the_chosen_name(
    hosted_client, db, monkeypatch
):
    """Two identities: the INTERNAL author is the session, the byline is chosen."""
    grant_admin(db, "boss@example.com")
    _alice, boss, ticket_id = _seed(hosted_client, db)

    sign_in(hosted_client, "raw-boss")
    body = hosted_client.post(
        f"/api/admin/feedback/tickets/{ticket_id}/messages",
        json={"body_markdown": "We are on it.", "display_name": "Anna from Support"},
        headers=SAFE_HEADERS,
    )
    assert body.status_code == 200, body.text
    message = body.json()["messages"][-1]
    assert message["author_type"] == AUTHOR_ADMIN
    assert message["display_name"] == "Anna from Support"
    assert message["author_email"] == "boss@example.com"
    assert message["author_user_id"] == boss.id


def test_two_admins_post_under_different_names_and_stay_correct_internally(
    hosted_client, db, monkeypatch
):
    grant_admin(db, "boss@example.com", "second@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    other = make_user(db, "sub-second", email="second@example.com")
    add_session(db, other, "raw-second")

    sign_in(hosted_client, "raw-boss")
    hosted_client.post(
        f"/api/admin/feedback/tickets/{ticket_id}/messages",
        json={"body_markdown": "First answer.", "display_name": "Anna"},
        headers=SAFE_HEADERS,
    )
    sign_in(hosted_client, "raw-second")
    hosted_client.post(
        f"/api/admin/feedback/tickets/{ticket_id}/messages",
        json={"body_markdown": "Second answer.", "display_name": "Bohdan"},
        headers=SAFE_HEADERS,
    )

    sign_in(hosted_client, "raw-boss")
    messages = hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}").json()[
        "messages"
    ]
    internal = {
        m["display_name"]: (m["author_user_id"], m["author_email"])
        for m in messages
        if m["author_type"] == AUTHOR_ADMIN
    }
    assert set(internal) == {"Anna", "Bohdan"}
    assert internal["Anna"][1] == "boss@example.com"
    assert internal["Bohdan"][1] == "second@example.com"
    # Two public names, two different internal authors.
    assert internal["Anna"][0] != internal["Bohdan"][0]
    assert other.id in {value[0] for value in internal.values()}


def test_an_admin_reply_defaults_to_the_support_name(hosted_client, db, monkeypatch):
    from core.config import FEEDBACK_DEFAULT_ADMIN_NAME

    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")

    hosted_client.post(
        f"/api/admin/feedback/tickets/{ticket_id}/messages",
        json={"body_markdown": "Answer without a label."},
        headers=SAFE_HEADERS,
    )
    payload = hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}").json()
    assert payload["messages"][-1]["display_name"] == FEEDBACK_DEFAULT_ADMIN_NAME


@pytest.mark.parametrize(
    "payload",
    [
        {"body_markdown": ""},
        {"body_markdown": "   "},
        {},
        {"body_markdown": "x" * 20001},
        {"body_markdown": "ok", "display_name": "x" * 101},
    ],
)
def test_an_invalid_admin_reply_is_422(hosted_client, db, monkeypatch, payload):
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")
    response = hosted_client.post(
        f"/api/admin/feedback/tickets/{ticket_id}/messages",
        json=payload,
        headers=SAFE_HEADERS,
    )
    assert response.status_code == 422, payload


def test_an_admin_reply_never_takes_the_author_id_from_the_body(
    hosted_client, db, monkeypatch
):
    grant_admin(db, "boss@example.com")
    _alice, boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")

    hosted_client.post(
        f"/api/admin/feedback/tickets/{ticket_id}/messages",
        json={
            "body_markdown": "Answer",
            "display_name": "Support",
            "author_user_id": 4242,
            "author_email": "someone@else.example",
            "author_type": "USER",
        },
        headers=SAFE_HEADERS,
    )
    message = hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}").json()[
        "messages"
    ][-1]
    assert message["author_user_id"] == boss.id
    assert message["author_email"] == "boss@example.com"
    assert message["author_type"] == AUTHOR_ADMIN
    sign_in(hosted_client, "raw-boss")
    body = hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}")
    assert body.status_code == 200
    payload = body.json()
    assert payload["user_email"] == "sub-alice@example.com"
    # The admin projection carries the real identity of every message author.
    assert payload["messages"][0]["author_email"] == "sub-alice@example.com"
    assert payload["messages"][0]["author_user_id"] is not None


def test_the_admin_stats_endpoint_counts_per_status(hosted_client, db, monkeypatch):
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    carol = make_user(db, "sub-carol")
    add_session(db, carol, "raw-carol")
    sign_in(hosted_client, "raw-carol")
    create_ticket(hosted_client, subject="Another")

    sign_in(hosted_client, "raw-boss")
    stats = hosted_client.get("/api/admin/feedback/stats").json()
    assert stats == {"total": 2, "new": 2, "in_progress": 0, "resolved": 0}

    hosted_client.patch(
        f"/api/admin/feedback/tickets/{ticket_id}",
        json={"status": "resolved"},
        headers=SAFE_HEADERS,
    )
    stats = hosted_client.get("/api/admin/feedback/stats").json()
    assert stats["resolved"] == 1
    assert stats["new"] == 1


def test_an_admin_reply_reopens_a_resolved_ticket(hosted_client, db, monkeypatch):
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")
    hosted_client.patch(
        f"/api/admin/feedback/tickets/{ticket_id}",
        json={"status": STATUS_RESOLVED},
        headers=SAFE_HEADERS,
    )

    hosted_client.post(
        f"/api/admin/feedback/tickets/{ticket_id}/messages",
        json={"body_markdown": "One more thing."},
        headers=SAFE_HEADERS,
    )
    payload = hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}").json()
    assert payload["status"] == "in_progress"


@pytest.mark.parametrize("status", ["new", "in_progress", "resolved"])
def test_an_admin_changes_the_status(hosted_client, db, monkeypatch, status):
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")

    body = hosted_client.patch(
        f"/api/admin/feedback/tickets/{ticket_id}",
        json={"status": status},
        headers=SAFE_HEADERS,
    )
    assert body.status_code == 200
    assert body.json()["status"] == status


@pytest.mark.parametrize(
    "payload",
    [{"status": "closed"}, {"status": ""}, {}, {"status": None}, {"status": 5}],
)
def test_an_invalid_status_is_422(hosted_client, db, monkeypatch, payload):
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")
    body = hosted_client.patch(
        f"/api/admin/feedback/tickets/{ticket_id}",
        json=payload,
        headers=SAFE_HEADERS,
    )
    assert body.status_code == 422, body.text


def test_a_status_patch_changes_nothing_but_the_status(hosted_client, db, monkeypatch):
    """The endpoint accepts the status ONLY: no author, no subject, no owner."""
    grant_admin(db, "boss@example.com")
    _alice, boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")
    before = hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}").json()

    hosted_client.patch(
        f"/api/admin/feedback/tickets/{ticket_id}",
        json={"status": "resolved", "subject": "hijacked", "user_id": 999},
        headers=SAFE_HEADERS,
    )
    after = hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}").json()
    assert after["status"] == "resolved"
    assert after["subject"] == before["subject"]
    assert after["user_id"] == before["user_id"] != 999
    assert after["messages"] == before["messages"]
    assert boss.id != 999


# --------------------------------------------------------------- admin delete


def test_an_admin_deletes_a_ticket_permanently(hosted_client, db, monkeypatch):
    """Real delete: the row, its messages and its attachment rows are gone."""
    from db.models.feedback import FeedbackTicket, TicketMessage

    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    reply(hosted_client, ticket_id, "One more question")
    sign_in(hosted_client, "raw-boss")

    response = hosted_client.delete(
        f"/api/admin/feedback/tickets/{ticket_id}", headers=SAFE_HEADERS
    )
    assert response.status_code == 204
    assert response.content == b""

    db.expire_all()
    assert db.query(FeedbackTicket).filter_by(id=ticket_id).count() == 0
    assert db.query(TicketMessage).filter_by(ticket_id=ticket_id).count() == 0


def test_after_deletion_the_ticket_is_unreachable_for_everyone(
    hosted_client, db, monkeypatch
):
    """404 for the owner and for the administrator; gone from a fresh list."""
    grant_admin(db, "boss@example.com")
    _alice, _boss, ticket_id = _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")
    assert (
        hosted_client.delete(
            f"/api/admin/feedback/tickets/{ticket_id}", headers=SAFE_HEADERS
        ).status_code
        == 204
    )

    assert (
        hosted_client.get(f"/api/admin/feedback/tickets/{ticket_id}").status_code == 404
    )
    sign_in(hosted_client, "raw-alice")
    assert hosted_client.get(f"/api/feedback/tickets/{ticket_id}").status_code == 404
    assert hosted_client.get("/api/feedback/tickets").json() == []


def test_deleting_a_missing_ticket_is_404(hosted_client, db, monkeypatch):
    grant_admin(db, "boss@example.com")
    _seed(hosted_client, db)
    sign_in(hosted_client, "raw-boss")
    assert (
        hosted_client.delete(
            "/api/admin/feedback/tickets/999999", headers=SAFE_HEADERS
        ).status_code
        == 404
    )
