# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""The user-facing ticket surface (ADR-0035).

What is pinned here:

- anonymous means 401 on every feedback endpoint (the session gate, before
  route dispatch);
- the identity of a stored message comes from the SESSION: a body carrying
  ``author_type`` / ``author_user_id`` / ``display_name`` changes nothing;
- "My tickets" and one-ticket reads are scoped by ``user_id`` INSIDE the
  statement, so another user's ticket is 404 — identical to a missing one, never
  403 (a 403 would confirm the id is real);
- replying to a resolved ticket reopens it;
- the closed category set and every length limit are enforced server-side;
- the per-user rate limit answers 429 with Retry-After.
"""

import pytest
from feedback_helpers import (
    SAFE_HEADERS,
    add_session,
    create_ticket,
    make_user,
    reply,
    sign_in,
)
from sqlalchemy.orm import Session

from models_feedback import (
    AUTHOR_USER,
    STATUS_IN_PROGRESS,
    FeedbackTicket,
    TicketMessage,
)


def _alice_bob(db: Session):
    """Two signed-in hosted users, one session token each."""
    alice = make_user(db, "sub-alice")
    bob = make_user(db, "sub-bob")
    add_session(db, alice, "raw-alice")
    add_session(db, bob, "raw-bob")
    return alice, bob


def alice_id(db: Session) -> int:
    """The id of the signed-in Alice (the user whose reply we forged)."""
    return db.query(FeedbackTicket).one().user_id


# ------------------------------------------------------------------ anonymous


def test_anonymous_is_rejected_on_every_feedback_endpoint(hosted_client):
    """The hosted session gate closes the whole feature before dispatch."""
    assert hosted_client.get("/api/feedback/tickets").status_code == 401
    assert (
        hosted_client.post(
            "/api/feedback/tickets",
            json={"category": "bug", "subject": "x", "body_markdown": "y"},
            headers=SAFE_HEADERS,
        ).status_code
        == 401
    )
    assert hosted_client.get("/api/feedback/tickets/1").status_code == 401
    assert (
        hosted_client.post(
            "/api/feedback/tickets/1/messages",
            json={"body_markdown": "hello"},
            headers=SAFE_HEADERS,
        ).status_code
        == 401
    )
    assert hosted_client.get("/api/feedback/attachments/1").status_code == 401


def test_anonymous_is_rejected_on_every_admin_endpoint(hosted_client):
    """No admin endpoint is reachable without a session — the gate is shared."""
    assert hosted_client.get("/api/admin/feedback/tickets").status_code == 401
    assert hosted_client.get("/api/admin/feedback/stats").status_code == 401
    assert hosted_client.get("/api/admin/feedback/tickets/1").status_code == 401
    assert (
        hosted_client.post(
            "/api/admin/feedback/tickets/1/messages",
            json={"body_markdown": "hi"},
            headers=SAFE_HEADERS,
        ).status_code
        == 401
    )
    assert (
        hosted_client.patch(
            "/api/admin/feedback/tickets/1",
            json={"status": "resolved"},
            headers=SAFE_HEADERS,
        ).status_code
        == 401
    )
    assert (
        hosted_client.delete(
            "/api/admin/feedback/tickets/1", headers=SAFE_HEADERS
        ).status_code
        == 401
    )


# --------------------------------------------------------------------- create


def test_a_user_creates_a_ticket_under_their_own_identity(hosted_client, db):
    alice, _ = _alice_bob(db)
    sign_in(hosted_client, "raw-alice")

    body = create_ticket(hosted_client, subject="Calendar is empty")

    assert body.status_code == 201, body.text
    payload = body.json()
    assert payload["subject"] == "Calendar is empty"
    assert payload["category"] == "problem"
    assert payload["status"] == "new"
    assert len(payload["messages"]) == 1
    message = payload["messages"][0]
    assert message["author_type"] == AUTHOR_USER
    # The byline comes from the profile, and the user NEVER receives an
    # author_email (the field does not exist on the user-facing model).
    assert message["display_name"] == "Alice"
    assert "author_email" not in message

    stored = db.query(FeedbackTicket).one()
    assert stored.user_id == alice.id
    message_row = db.query(TicketMessage).one()
    assert message_row.author_user_id == alice.id
    assert message_row.author_type == AUTHOR_USER


def test_a_ticket_creation_needs_no_attachments(hosted_client, db):
    """Attachments are optional: the whole feature works without a single file."""
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    body = create_ticket(hosted_client)
    assert body.status_code == 201
    assert body.json()["messages"][0]["attachments"] == []


def test_a_user_lists_only_their_own_tickets(hosted_client, db):
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    create_ticket(hosted_client, subject="Alice one")
    create_ticket(hosted_client, subject="Alice two")

    sign_in(hosted_client, "raw-bob")
    create_ticket(hosted_client, subject="Bob one")

    sign_in(hosted_client, "raw-alice")
    mine = hosted_client.get("/api/feedback/tickets").json()
    assert {t["subject"] for t in mine} == {"Alice one", "Alice two"}

    sign_in(hosted_client, "raw-bob")
    theirs = hosted_client.get("/api/feedback/tickets").json()
    assert [t["subject"] for t in theirs] == ["Bob one"]


def test_a_user_opens_their_own_ticket_with_the_conversation(hosted_client, db):
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    ticket_id = create_ticket(hosted_client, subject="Mine").json()["id"]
    reply(hosted_client, ticket_id, "Still broken.")

    body = hosted_client.get(f"/api/feedback/tickets/{ticket_id}")
    assert body.status_code == 200
    payload = body.json()
    assert [m["body_markdown"] for m in payload["messages"]] == [
        "My average is 10.",
        "Still broken.",
    ]
    assert all(m["author_type"] == AUTHOR_USER for m in payload["messages"])


def test_a_user_cannot_open_another_users_ticket(hosted_client, db):
    """404, not 403: the answer must not confirm that the id exists."""
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    ticket_id = create_ticket(hosted_client, subject="Private matter").json()["id"]

    sign_in(hosted_client, "raw-bob")
    body = hosted_client.get(f"/api/feedback/tickets/{ticket_id}")
    assert body.status_code == 404
    assert "Private" not in body.text
    # A ticket id that never existed answers exactly the same way.
    missing = hosted_client.get(f"/api/feedback/tickets/{ticket_id + 9999}")
    assert missing.status_code == 404
    assert missing.json() == body.json()


def test_a_user_cannot_reply_to_another_users_ticket(hosted_client, db):
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    ticket_id = create_ticket(hosted_client).json()["id"]

    sign_in(hosted_client, "raw-bob")
    body = reply(hosted_client, ticket_id, "Let me in")
    assert body.status_code == 404

    sign_in(hosted_client, "raw-alice")
    detail = hosted_client.get(f"/api/feedback/tickets/{ticket_id}").json()
    assert len(detail["messages"]) == 1


def test_a_user_reply_cannot_forge_the_identity(hosted_client, db):
    """The stored identity comes from the session, whatever the body claims."""
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    ticket_id = create_ticket(hosted_client).json()["id"]

    body = hosted_client.post(
        f"/api/feedback/tickets/{ticket_id}/messages",
        json={
            "body_markdown": "This is not really me.",
            "author_type": "ADMIN",
            "author_user_id": 999,
            "display_name": "GoogleClassHelp Support",
            "author_email": "attacker@example.com",
        },
        headers=SAFE_HEADERS,
    )
    assert body.status_code == 200, body.text
    message = body.json()["messages"][-1]
    assert message["author_type"] == AUTHOR_USER
    assert message["display_name"] == "Alice"

    row = (
        db.query(TicketMessage).filter_by(body_markdown="This is not really me.").one()
    )
    assert row.author_user_id == alice_id(db)
    assert row.author_user_id != 999
    assert row.display_name == "Alice"


def test_a_reply_reopens_a_resolved_ticket(hosted_client, db):
    """ADR-0035: a follow-up can never be swallowed by a closed thread."""
    _alice_bob(db)


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "spam", "subject": "Hi", "body_markdown": "Hello"},
        {"category": "", "subject": "Hi", "body_markdown": "Hello"},
        {"category": "bug", "subject": "   ", "body_markdown": "Hello"},
        {"category": "bug", "subject": "", "body_markdown": "Hello"},
        {"category": "bug", "subject": "Hi", "body_markdown": "   "},
        {"category": "bug", "subject": "Hi", "body_markdown": ""},
        {"category": "bug", "subject": "x" * 201, "body_markdown": "Hello"},
        {"category": "bug", "subject": "Hi", "body_markdown": "x" * 20001},
        {"subject": "Hi", "body_markdown": "Hello"},
        {"category": "bug", "body_markdown": "Hello"},
        {"category": "bug", "subject": "Hi"},
    ],
)
def test_invalid_creation_input_is_422(hosted_client, db, payload):
    """Server-side validation only — the frontend check is a convenience."""
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    body = hosted_client.post(
        "/api/feedback/tickets", json=payload, headers=SAFE_HEADERS
    )
    assert body.status_code == 422, body.text


def test_an_invalid_reply_is_422(hosted_client, db):
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    ticket_id = create_ticket(hosted_client).json()["id"]
    for payload in ({}, {"body_markdown": ""}, {"body_markdown": "   "}):
        body = hosted_client.post(
            f"/api/feedback/tickets/{ticket_id}/messages",
            json=payload,
            headers=SAFE_HEADERS,
        )
        assert body.status_code == 422, body.text


def test_a_malformed_body_is_422_and_never_leaks_internals(hosted_client, db):
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    body = hosted_client.post(
        "/api/feedback/tickets",
        content=b"{not json",
        headers={**SAFE_HEADERS, "Content-Type": "application/json"},
    )
    assert body.status_code == 422
    assert "Traceback" not in body.text


# ----------------------------------------------------------------- rate limits


def test_the_creation_rate_limit_answers_429_with_retry_after(
    hosted_client, db, monkeypatch
):
    import feedback_service

    _alice_bob(db)
    # Patched on the module that READS it: the endpoint must see the test's
    # allowance, not the process default of 5/hour.
    monkeypatch.setattr(feedback_service, "FEEDBACK_TICKETS_PER_HOUR", 2)
    sign_in(hosted_client, "raw-alice")

    assert create_ticket(hosted_client).status_code == 201
    assert create_ticket(hosted_client).status_code == 201

    blocked = create_ticket(hosted_client)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_the_reply_rate_limit_answers_429(hosted_client, db, monkeypatch):
    import feedback_service

    _alice_bob(db)
    monkeypatch.setattr(feedback_service, "FEEDBACK_REPLIES_PER_HOUR", 1)
    sign_in(hosted_client, "raw-alice")
    ticket_id = create_ticket(hosted_client).json()["id"]

    assert reply(hosted_client, ticket_id, "one").status_code == 200
    blocked = reply(hosted_client, ticket_id, "two")
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_the_rate_limit_is_per_user_not_per_ip(hosted_client, db, monkeypatch):
    """A school NAT shares one address: exhausting Alice must not block Bob."""
    import feedback_service

    alice, bob = _alice_bob(db)
    monkeypatch.setattr(feedback_service, "FEEDBACK_TICKETS_PER_HOUR", 1)
    sign_in(hosted_client, "raw-alice")
    assert create_ticket(hosted_client).status_code == 201
    assert create_ticket(hosted_client).status_code == 429

    sign_in(hosted_client, "raw-bob")
    assert create_ticket(hosted_client).status_code == 201
    assert bob.id != alice.id


# ------------------------------------------------------------- markdown safety


@pytest.mark.parametrize(
    "body",
    [
        "<script>alert(1)</script>",
        '<img src=x onerror="alert(1)">',
        "[click](javascript:alert(1))",
        "<iframe src='https://evil.example'></iframe>",
        "<svg/onload=alert(1)>",
    ],
)
def test_untrusted_markdown_is_stored_verbatim(hosted_client, db, body):
    """The backend stores the SOURCE; rendering is sanitized in the frontend.

    Storing anything else (escaping, stripping) would make the stored value a
    lie — and the sanitizer already has to cope with a preview typed before the
    message was ever sent.
    """
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    response = create_ticket(hosted_client, body_markdown=body)
    assert response.status_code == 201
    assert response.json()["messages"][0]["body_markdown"] == body

    row = db.query(TicketMessage).one()
    assert row.body_markdown == body


def test_no_response_ever_carries_the_admin_addresses(hosted_client, db, monkeypatch):
    """§6: the allow-list is server-side; the browser only ever sees a boolean."""
    from feedback_helpers import as_admin

    as_admin(monkeypatch, "boss@example.com")
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    create_ticket(hosted_client)

    for path in ("/api/feedback/tickets", "/api/auth/status", "/api/me"):
        body = hosted_client.get(path)
        assert "boss@example.com" not in body.text
    assert "boss@example.com" not in hosted_client.get("/openapi.json").text
    sign_in(hosted_client, "raw-alice")
    ticket_id = create_ticket(hosted_client).json()["id"]

    stored = db.query(FeedbackTicket).filter_by(id=ticket_id).one()
    stored.status = "resolved"
    db.commit()

    body = reply(hosted_client, ticket_id, "It happened again.")
    assert body.status_code == 200
    assert body.json()["status"] == STATUS_IN_PROGRESS
    db.expire_all()
    assert (
        db.query(FeedbackTicket).filter_by(id=ticket_id).one().status
        == STATUS_IN_PROGRESS
    )


def test_a_reply_bumps_the_updated_at_of_the_ticket(hosted_client, db):
    _alice_bob(db)
    sign_in(hosted_client, "raw-alice")
    create_ticket(hosted_client)
    ticket_id = hosted_client.get("/api/feedback/tickets").json()[0]["id"]
    first = hosted_client.get("/api/feedback/tickets").json()[0]["updated_at"]

    reply(hosted_client, ticket_id, "again")
    second = hosted_client.get("/api/feedback/tickets").json()[0]["updated_at"]
    assert second >= first
