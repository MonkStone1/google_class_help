"""Uploaded ticket files: validation, safe storage, authorized serving.

This is the FIRST upload mechanism in the repository — the Caddyfile even said
"the application has no upload feature" — so the design is deliberately the
simplest secure one:

**Allow-list, matched on the CONTENT, never on the name or the client's
``Content-Type``.** The extension is a hint only: a file called ``photo.png``
that starts with a ZIP or ELF header is rejected, and a valid PNG called
``evil.sh`` is stored as ``<uuid>.png``. The sniffed type is also what the
download endpoint announces, so the stored extension and the served type can
never disagree.

**Sizes are enforced while the upload streams**, in chunks, and the request is
aborted as soon as the budget is exceeded — the bytes are never fully buffered
in memory first (the edge caps the body too, but the application must not
rely on the edge existing).

**Files live on the appdata volume** under ``DATA_DIR/feedback/<ticket_id>/``
with a server-generated name. Every resolved path is verified to stay inside
that root before a write and before a delete (path-traversal defence), and the
client's filename is sanitized to a display-only basename.

**Serving is an authorized API endpoint** (``GET /api/feedback/attachments/
{id}``): the row is loaded, the caller must be the ticket's owner or an
administrator, and the answer is a ``FileResponse`` with
``Content-Disposition: attachment`` and the sniffed type. There is no static
mount for uploads — ``frontend/dist`` is the only static mount in the app, and
an SPA fallback there would happily expose whatever it finds under ``/``.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

# The UPLOADED-file type that ``await request.form()`` actually yields.
# ``fastapi.UploadFile`` is a SUBCLASS of it, so an ``isinstance`` check
# against the FastAPI name would be False for every real part — the parser
# hands out Starlette's own class.
from starlette.datastructures import UploadFile

from config import (
    FEEDBACK_MAX_ATTACHMENT_BYTES,
    FEEDBACK_MAX_ATTACHMENTS,
    FEEDBACK_MAX_TOTAL_BYTES,
)
from models_feedback import TicketAttachment
from path_config import DATA_DIR

logger = logging.getLogger(__name__)

# The whole feature's file space, one directory per ticket.
FEEDBACK_ROOT = DATA_DIR / "feedback"

# Sniffed type -> the extension the file is stored and served under. The
# extension is always the SNIFFED one, never the uploaded one.
ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}

# Rejected outright, whatever the bytes say: these are executables, scripts or
# documents a browser would EXECUTE or render as active content. The upload is
# refused instead of being neutered, because a `.html` attachment has no
# legitimate use in a support ticket.
BLOCKED_EXTENSIONS = frozenset(
    {
        ".exe",
        ".com",
        ".bat",
        ".cmd",
        ".msi",
        ".scr",
        ".pif",
        ".dll",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".psm1",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".py",
        ".rb",
        ".pl",
        ".php",
        ".html",
        ".htm",
        ".xhtml",
        ".svg",
        ".xml",
        ".jar",
        ".app",
        ".deb",
        ".rpm",
        ".apk",
        # Archives: nothing legitimate in a support ticket, and the classic
        # double-extension trick (`report.pdf.zip`) otherwise smuggles a file
        # past the name check that the content check cannot judge.
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
    }
)

# Read/write chunk size: small enough to abort a huge body early, large enough
# that a 5 MB file costs a handful of reads.
CHUNK_SIZE = 64 * 1024

# Control characters, path separators and Windows-reserved characters are
# stripped from the DISPLAY name; it never reaches the filesystem anyway.
_UNSAFE_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f<>:\"/\\|?*]")


def _bad(detail: str, status_code: int = 422) -> HTTPException:
    """A short, non-sensitive validation error (never a path or a trace)."""
    return HTTPException(status_code=status_code, detail=detail)


def sanitize_original_name(name: str | None) -> str:
    """A display-only, single-segment name for the UI.

    Path separators, drive letters and ``..`` are stripped, so a traversal
    filename is inert as metadata too; anything left empty becomes
    ``attachment``. The value is capped at 255 characters to fit the column.
    """
    raw = (name or "").strip().replace("\\", "/")
    base = raw.rsplit("/", 1)[-1]
    cleaned = _UNSAFE_NAME_CHARS.sub("_", base).strip().strip(".")
    if not cleaned or cleaned in {".", ".."}:
        return "attachment"
    return cleaned[:255]


def _extension_of(filename: str | None) -> str:
    """The lower-cased extension of a filename, ``""`` when there is none."""
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    _, dot, ext = base.rpartition(".")
    if not dot or not ext:
        return ""
    return f".{ext.lower()}"


def _has_blocked_extension(filename: str | None) -> bool:
    """Whether the name (or its double extension) looks active/executable.

    ``report.html.exe`` and ``x.html`` are refused on the NAME even when the
    bytes would sniff as text: the name is what a human downloads and
    double-clickable, so it is part of the attack surface.
    """
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not base:
        return False
    parts = [part for part in base.split(".") if part]
    if len(parts) < 2:
        return False
    # Every extension after the first dot, so both `x.html` and `x.html.exe`
    # are caught.
    return any(f".{part}" in BLOCKED_EXTENSIONS for part in parts[1:])


def sniff_content_type(head: bytes) -> str | None:
    """Identify the content type from magic numbers; ``None`` when unknown.

    ``text/plain`` has no signature, so it is decided by decodability: a body
    that is valid UTF-8 (with no NUL bytes) is plain text. This is why an ELF
    binary or a ZIP archive named ``.txt`` is rejected rather than stored.
    """
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if not head:
        return None
    if b"\x00" in head:
        return None
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return "text/plain"


def _ticket_dir(ticket_id: int) -> Path:
    """The directory of one ticket, resolved and verified inside the root."""
    root = FEEDBACK_ROOT.resolve()
    candidate = (root / str(int(ticket_id))).resolve()
    # Path-traversal defence: a ticket id is an int, but the resolved path is
    # verified anyway so no future caller can widen the blast radius.
    if candidate != root and root not in candidate.parents:
        raise _bad("Invalid ticket id.", 422)
    return candidate


def ticket_files_dir(ticket_id: int) -> Path:
    """``.../feedback/<ticket_id>``, created on demand before a write."""
    directory = _ticket_dir(ticket_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def store_upload(
    upload: UploadFile,
    ticket_id: int,
    message_id: int,
    now: datetime,
    budget: ByteBudget,
) -> TicketAttachment:
    """Stream one upload to disk and return its row.

    The byte budget is checked on every chunk, so an oversized body is abandoned
    while it is still arriving (413) and the partial file is removed — a large
    upload never lands on the volume.
    """
    if _has_blocked_extension(upload.filename):
        raise _bad("This file type is not allowed.")
    head = await upload.read(CHUNK_SIZE)
    content_type = sniff_content_type(head)
    if content_type is None or content_type not in ALLOWED_TYPES:
        raise _bad("This file type is not allowed.")

    stored_name = f"{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"
    directory = ticket_files_dir(ticket_id)
    path = (directory / stored_name).resolve()
    root = FEEDBACK_ROOT.resolve()
    if root not in path.parents:
        # Unreachable via uuid4 + a fixed extension, verified because this is
        # the last line before a write on disk.
        raise _bad("Could not store the attachment.", 500)

    size = 0
    try:
        with path.open("wb") as handle:
            chunk = head
            while chunk:
                size += len(chunk)
                if size > FEEDBACK_MAX_ATTACHMENT_BYTES:
                    raise _bad("The file exceeds the maximum allowed size.", 413)
                budget.consume(len(chunk))
                handle.write(chunk)
                chunk = await upload.read(CHUNK_SIZE)
    except BaseException:
        # Never leave a partial file behind — not on a rejection, not on a
        # cancelled request.
        path.unlink(missing_ok=True)
        raise

    return TicketAttachment(
        message_id=message_id,
        ticket_id=ticket_id,
        stored_name=stored_name,
        original_name=sanitize_original_name(upload.filename),
        content_type=content_type,
        size_bytes=size,
        created_at=now,
    )


class ByteBudget:
    """The per-message byte budget shared by every file of that message.

    The limit is read AT CONSTRUCTION from the module attribute (not baked
    into the signature as a default), so it reflects configuration and can be
    tightened in a test without reloading the module.
    """

    def __init__(self, limit: int | None = None) -> None:
        self.limit = FEEDBACK_MAX_TOTAL_BYTES if limit is None else limit
        self.used = 0

    def consume(self, amount: int) -> None:
        self.used += amount
        if self.used > self.limit:
            raise _bad("The attachments exceed the maximum total size.", 413)


def check_file_count(files: Sequence[UploadFile]) -> None:
    """Reject more files than a message may carry, before reading any byte."""
    if len(files) > FEEDBACK_MAX_ATTACHMENTS:
        raise _bad("Too many attachments.", 422)


def attachment_path(attachment: TicketAttachment) -> Path:
    """The resolved on-disk path of an attachment, verified inside the root."""
    root = FEEDBACK_ROOT.resolve()
    path = (_ticket_dir(attachment.ticket_id) / attachment.stored_name).resolve()
    if root not in path.parents:
        raise _bad("Attachment not found.", 404)
    return path


def download_response(attachment: TicketAttachment) -> FileResponse:
    """The authorized download answer.

    ``Content-Disposition: attachment`` for everything, so the browser never
    renders an uploaded file in the app's origin — an HTML/SVG upload could
    otherwise become stored XSS on the site's own domain even with nosniff.
    ``X-Content-Type-Options: nosniff`` is already sent globally (main.py).
    """
    path = attachment_path(attachment)
    if not path.is_file():
        # The row is authoritative; a lost file must not 500 the whole delete
        # path or the download path.
        raise _bad("Attachment file not found.", 404)
    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.stored_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def unlink_attachment(attachment: TicketAttachment) -> None:
    """Remove one file, tolerating a file that is already gone."""
    try:
        attachment_path(attachment).unlink(missing_ok=True)
    except (OSError, HTTPException) as exc:
        # Deletion is a cleanup step: a missing permission or a vanished file
        # must not fail the ticket deletion it belongs to.
        logger.info(
            "Attachment file of attachment id=%s could not be unlinked.",
            attachment.id,
            exc_info=exc,
        )


def unlink_ticket_files(ticket_id: int, attachments: list[TicketAttachment]) -> None:
    """Remove every file of one ticket (called by the delete endpoints)."""
    for attachment in attachments:
        unlink_attachment(attachment)
    try:
        directory = _ticket_dir(ticket_id)
        if (
            directory.is_dir()
            and FEEDBACK_ROOT.resolve() in directory.resolve().parents
        ):
            # Only removes the now-empty per-ticket directory; rmdir fails on a
            # non-empty one, so an unexpected leftover file is never destroyed.
            directory.rmdir()
    except OSError as exc:
        logger.info(
            "Feedback directory of ticket id=%s could not be removed.",
            ticket_id,
            exc_info=exc,
        )


def load_attachment(db: Session, attachment_id: int) -> TicketAttachment | None:
    """The attachment row, or ``None`` when it does not exist.

    The caller performs the authorization decision: it must be the ticket's
    owner or an administrator. Doing the scope check here would duplicate it
    and could get it subtly wrong per endpoint.
    """
    return db.execute(
        select(TicketAttachment).where(TicketAttachment.id == attachment_id)
    ).scalar_one_or_none()
