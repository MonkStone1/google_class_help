# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Ticket attachments (ADR-0035): validation, storage, serving.

The upload path is the only place of this repository where a browser can make
the server write bytes, so the tests read as an attacker's checklist:

- a ``.png`` that is actually a ZIP/ELF/binary is refused — the type is decided
  by the CONTENT, never by the name or the client's ``Content-Type``;
- an executable, a script or an HTML/SVG document is refused on the NAME even
  when the bytes are harmless text;
- a traversal filename is inert: the file lands under a server-generated name
  inside the feedback root, and nothing is written outside it;
- an over-sized file is refused with 413 and leaves no partial file behind;
- the served answer is ``attachment`` + ``nosniff`` from the authorized endpoint
  only — there is no static mount a browser could reach directly;
- one user's attachment is 404 for another user.
"""

import io

import pytest
from feedback_helpers import (
    SAFE_HEADERS,
    add_session,
    create_ticket,
    grant_admin,
    make_user,
    sign_in,
)
from sqlalchemy.orm import Session

import feedback_attachments as attachments
from models_feedback import FeedbackTicket, TicketAttachment

# 1x1 PNG — the smallest real PNG, the "valid" baseline.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
ZIP = b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + b"\x00" * 24
ELF = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 24


def _alice(hosted_client, db: Session):
    alice = make_user(db, "sub-alice")
    bob = make_user(db, "sub-bob")
    add_session(db, alice, "raw-alice")
    add_session(db, bob, "raw-bob")
    sign_in(hosted_client, "raw-alice")
    return alice, bob


def _upload(client, filename: str, content: bytes, subject: str = "With a file"):
    return create_ticket(
        client,
        subject=subject,
        files=[("files", (filename, io.BytesIO(content), "application/octet-stream"))],
    )


def _boss(hosted_client, db: Session) -> None:
    """Create an administrator account and sign the client in as them."""
    boss = make_user(db, "sub-boss", email="boss@example.com")
    add_session(db, boss, "raw-boss")
    sign_in(hosted_client, "raw-boss")


# ------------------------------------------------------------- happy path


def test_a_png_upload_is_stored_and_listed(hosted_client, db):
    _alice(hosted_client, db)
    body = _upload(hosted_client, "screenshot.png", PNG)
    assert body.status_code == 201, body.text
    files = body.json()["messages"][0]["attachments"]
    assert len(files) == 1
    assert files[0]["original_name"] == "screenshot.png"
    # The type is the SNIFFED one, whatever the client claimed.
    assert files[0]["content_type"] == "image/png"
    assert files[0]["size_bytes"] == len(PNG)


def test_text_and_pdf_are_accepted(hosted_client, db):
    _alice(hosted_client, db)
    text = _upload(hosted_client, "notes.txt", b"just plain text")
    assert text.status_code == 201
    assert text.json()["messages"][0]["attachments"][0]["content_type"] == "text/plain"

    pdf = _upload(hosted_client, "report.pdf", b"%PDF-1.4\n%demo\n")
    assert pdf.status_code == 201
    assert (
        pdf.json()["messages"][0]["attachments"][0]["content_type"] == "application/pdf"
    )


def test_the_file_lives_under_a_server_generated_name(hosted_client, db):
    """The client's filename is display metadata and never touches the disk."""
    _alice(hosted_client, db)
    body = _upload(hosted_client, "../../evil.txt", b"hello there")
    assert body.status_code == 201, body.text

    row = db.query(TicketAttachment).one()
    assert row.stored_name.endswith(".txt")
    assert "/" not in row.stored_name and "\\" not in row.stored_name
    # The original name was sanitized to its last segment only.
    assert "/" not in row.original_name and ".." not in row.original_name

    stored = attachments.attachment_path(row)
    assert stored.is_file()
    assert attachments.FEEDBACK_ROOT.resolve() in stored.parents


# ---------------------------------------------------------------- rejections


@pytest.mark.parametrize(
    ("filename", "content", "reason"),
    [
        ("payload.png", ZIP, "a PNG that is a ZIP archive"),
        ("payload.png", ELF, "a PNG that is an ELF binary"),
        ("photo.png", b"", "an empty file"),
        ("notes.txt", ELF, "a text file that is a binary"),
        ("report.pdf", b"BM6\x00\x00\x00\x00", "a PDF that is a BMP header"),
    ],
)
def test_a_file_whose_content_is_not_allowed_is_rejected(
    hosted_client, db, filename, content, reason
):
    _alice(hosted_client, db)
    body = _upload(hosted_client, filename, content)
    assert body.status_code == 422, f"{reason}: {body.text}"
    assert db.query(TicketAttachment).count() == 0


@pytest.mark.parametrize(
    "filename",
    [
        "virus.exe",
        "script.sh",
        "payload.js",
        "page.html",
        "vector.svg",
        "index.php",
        "double.html.exe",
        "archive.zip.png",
        "notes.txt.sh",
    ],
)
def test_active_content_is_rejected_by_name_even_when_the_bytes_are_text(
    hosted_client, db, filename
):
    """Harmless TEXT with an executable/script/HTML name is still refused."""
    _alice(hosted_client, db)
    body = _upload(hosted_client, filename, b"totally harmless text")
    assert body.status_code == 422, body.text
    assert db.query(TicketAttachment).count() == 0


def test_an_oversized_file_is_413_and_leaves_nothing_behind(
    hosted_client, db, monkeypatch
):
    """The budget is enforced while streaming, so no partial file survives."""
    monkeypatch.setattr(attachments, "FEEDBACK_MAX_ATTACHMENT_BYTES", 1024)
    _alice(hosted_client, db)
    ticket_dir = attachments.FEEDBACK_ROOT.resolve() / "1"
    before = set(ticket_dir.iterdir()) if ticket_dir.exists() else set()

    body = _upload(hosted_client, "big.txt", b"a" * 4096)

    assert body.status_code == 413, body.text
    assert db.query(TicketAttachment).count() == 0
    # The rejected file left nothing behind: the directory is exactly as it was
    # (another test may already have stored files of THIS ticket id).
    after = set(ticket_dir.iterdir()) if ticket_dir.exists() else set()
    assert after == before


def test_the_total_budget_of_one_message_is_enforced(hosted_client, db, monkeypatch):
    monkeypatch.setattr(attachments, "FEEDBACK_MAX_TOTAL_BYTES", 2048)
    monkeypatch.setattr(attachments, "FEEDBACK_MAX_ATTACHMENT_BYTES", 1024)
    _alice(hosted_client, db)
    body = hosted_client.post(
        "/api/feedback/tickets",
        data={"category": "bug", "subject": "Two files", "body_markdown": "See both."},
        files=[
            ("files", ("a.txt", io.BytesIO(b"a" * 900), "text/plain")),
            ("files", ("b.txt", io.BytesIO(b"b" * 900), "text/plain")),
            ("files", ("c.txt", io.BytesIO(b"c" * 900), "text/plain")),
        ],
        headers=SAFE_HEADERS,
    )
    assert body.status_code == 413, body.text
    assert db.query(TicketAttachment).count() == 0


def test_too_many_files_are_422_before_a_single_byte_is_read(
    hosted_client, db, monkeypatch
):
    monkeypatch.setattr(attachments, "FEEDBACK_MAX_ATTACHMENTS", 2)
    _alice(hosted_client, db)
    body = hosted_client.post(
        "/api/feedback/tickets",
        data={"category": "bug", "subject": "Three", "body_markdown": "Three files."},
        files=[
            ("files", ("a.txt", io.BytesIO(b"one"), "text/plain")),
            ("files", ("b.txt", io.BytesIO(b"two"), "text/plain")),
            ("files", ("c.txt", io.BytesIO(b"three"), "text/plain")),
        ],
        headers=SAFE_HEADERS,
    )
    assert body.status_code == 422, body.text


# ------------------------------------------------------------------ serving


def test_the_owner_downloads_their_own_attachment(hosted_client, db):
    _alice(hosted_client, db)
    _upload(hosted_client, "notes.txt", b"my own notes")
    attachment_id = db.query(TicketAttachment).one().id

    response = hosted_client.get(f"/api/feedback/attachments/{attachment_id}")
    assert response.status_code == 200
    assert response.content == b"my own notes"
    # Never rendered in the app's origin, and never sniffed.
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_another_user_cannot_download_the_attachment(hosted_client, db):
    """404 — indistinguishable from an id that does not exist."""
    _alice(hosted_client, db)
    _upload(hosted_client, "private.txt", b"secret")
    attachment_id = db.query(TicketAttachment).one().id

    sign_in(hosted_client, "raw-bob")
    response = hosted_client.get(f"/api/feedback/attachments/{attachment_id}")
    assert response.status_code == 404
    assert b"secret" not in response.content


def test_an_admin_can_download_any_attachment(hosted_client, db, monkeypatch):
    grant_admin(db, "boss@example.com")
    _alice(hosted_client, db)
    _upload(hosted_client, "notes.txt", b"support needs this")
    attachment_id = db.query(TicketAttachment).one().id

    _boss(hosted_client, db)
    response = hosted_client.get(f"/api/feedback/attachments/{attachment_id}")
    assert response.status_code == 200
    assert response.content == b"support needs this"


def test_a_missing_attachment_is_404(hosted_client, db):
    _alice(hosted_client, db)
    assert hosted_client.get("/api/feedback/attachments/999999").status_code == 404


def test_no_static_path_serves_an_upload(hosted_client, db):
    """Uploads live on the appdata volume, never under the SPA's static root."""
    from path_config import FRONTEND_DIST_DIR

    _alice(hosted_client, db)
    _upload(hosted_client, "notes.txt", b"private bytes")
    stored = attachments.attachment_path(db.query(TicketAttachment).one())

    assert FRONTEND_DIST_DIR.resolve() not in stored.parents
    assert "dist" not in str(stored)


def test_the_traversal_filename_never_writes_outside_the_feedback_root(
    hosted_client, db
):
    _alice(hosted_client, db)
    body = _upload(hosted_client, "../../../../evil.txt", b"still inside")
    assert body.status_code == 201, body.text

    stored = attachments.attachment_path(db.query(TicketAttachment).one())
    root = attachments.FEEDBACK_ROOT.resolve()
    assert root in stored.parents
    # Nothing appeared next to the root either.
    assert not (root.parent / "evil.txt").exists()


# ------------------------------------------------- deletion unlinks files


def test_deleting_a_ticket_unlinks_its_files(hosted_client, db, monkeypatch):
    from models_feedback import TicketMessage

    grant_admin(db, "boss@example.com")
    _alice(hosted_client, db)
    ticket_id = _upload(hosted_client, "notes.txt", b"to be removed").json()["id"]
    path = attachments.attachment_path(db.query(TicketAttachment).one())
    assert path.is_file()

    _boss(hosted_client, db)
    assert (
        hosted_client.delete(
            f"/api/admin/feedback/tickets/{ticket_id}", headers=SAFE_HEADERS
        ).status_code
        == 204
    )

    assert not path.exists()
    db.expire_all()
    assert db.query(FeedbackTicket).count() == 0
    assert db.query(TicketMessage).count() == 0
    assert db.query(TicketAttachment).count() == 0


def test_account_deletion_removes_tickets_messages_and_files(hosted_client, db):
    """maintenance.delete_user_data covers the feedback domain too (§5.5)."""
    import maintenance
    from models_auth import User

    _alice(hosted_client, db)
    _upload(hosted_client, "notes.txt", b"mine")
    # Another user's ticket must survive the first user's deletion.
    sign_in(hosted_client, "raw-bob")
    _upload(hosted_client, "other.txt", b"theirs", subject="Not mine")
    assert db.query(FeedbackTicket).count() == 2

    mine = attachments.attachment_path(
        db.query(TicketAttachment)
        .filter(TicketAttachment.original_name == "notes.txt")
        .one()
    )
    theirs = attachments.attachment_path(
        db.query(TicketAttachment)
        .filter(TicketAttachment.original_name == "other.txt")
        .one()
    )

    alice_ticket = db.query(FeedbackTicket).filter_by(subject="With a file").one()
    report = maintenance.delete_user_data(db, db.get(User, alice_ticket.user_id))

    assert report["feedback_tickets"] == 1
    assert (
        db.query(TicketAttachment)
        .filter(TicketAttachment.original_name == "other.txt")
        .count()
        == 1
    )
    assert db.query(FeedbackTicket).count() == 1
    assert not mine.exists()
    assert theirs.is_file()


def test_a_missing_file_does_not_break_the_deletion(hosted_client, db, monkeypatch):
    """Best-effort cleanup: a vanished file must not fail the delete."""
    grant_admin(db, "boss@example.com")
    _alice(hosted_client, db)
    ticket_id = _upload(hosted_client, "notes.txt", b"vanishing").json()["id"]
    attachments.attachment_path(db.query(TicketAttachment).one()).unlink()

    _boss(hosted_client, db)
    assert (
        hosted_client.delete(
            f"/api/admin/feedback/tickets/{ticket_id}", headers=SAFE_HEADERS
        ).status_code
        == 204
    )


# ------------------------------------------------------------ sniff helper


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (PNG, "image/png"),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 8, "image/jpeg"),
        (b"GIF89a" + b"\x00" * 8, "image/gif"),
        (b"GIF87a" + b"\x00" * 8, "image/gif"),
        (b"%PDF-1.7", "application/pdf"),
        (b"plain utf-8 text", "text/plain"),
        (b"with\x00nul", None),
        (b"\xff\xfe\xfa\xfb", None),
        (ZIP, None),
        (ELF, None),
    ],
)
def test_sniff_content_type(head, expected):
    assert attachments.sniff_content_type(head) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("photo.png", "photo.png"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\evil.dll", "evil.dll"),
        ("", "attachment"),
        ("..", "attachment"),
        ("/absolute/name.txt", "name.txt"),
    ],
)
def test_sanitize_original_name(name, expected):
    assert attachments.sanitize_original_name(name) == expected
