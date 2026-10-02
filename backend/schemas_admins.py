"""Pydantic models of the administrator registry (ADR-0036).

A domain-specific module, like ``schemas_feedback.py`` holds the ticket shapes:
the registry surface stays readable on its own and ``schemas.py`` is not diluted
by models only one router uses.

Two shapes, deliberately:

- ``AdminOut`` is what the Super Admin may read — and note what it does NOT
  carry: no role column, no "is this the Super Admin" flag. The Super Admin has
  no row here at all (``SUPER_ADMIN_EMAIL`` is the only record of them), so
  there is nothing in a row to report;
- ``AdminCreateIn`` accepts the e-mail and NOTHING else. There is no name field
  because the display name is derived from the address server-side
  (``admin_auth.display_name_from_email``) — an editable name would be a second
  copy of the identity with nothing to keep it in sync.

The e-mail validator is hand-rolled rather than ``pydantic[email]`` on purpose:
adding ``email-validator`` would change ``requirements.txt``, the production
requirements and the Docker image for one field. The rule below is deliberately
pragmatic — "obviously not an address" is refused, and every real Google account
address passes.
"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# The address IS the identity of this registry, so it carries the same width as
# ``users.email`` and ``admins.email``: one value, one width, everywhere.
EMAIL_MAX_CHARS = 255

# Deliberately permissive: local part, "@", then a dotted domain. It refuses
# what a typo produces (no "@", no dot in the domain, embedded whitespace)
# without pretending to implement RFC 5322 — a stricter rule would reject
# legitimate addresses and is not what an identity check needs.
_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _validated_email(value: str) -> str:
    """Normalize and sanity-check one address; ``ValueError`` ⇒ HTTP 422.

    Order matters: normalize FIRST (trim + lower-case), so the duplicate check
    downstream compares the same spelling the row will be stored in. The
    whitespace rule is therefore checked after trimming — a trailing newline from
    a copy-paste is forgiven, a space inside the address is not.
    """
    normalized = (value or "").strip().lower()
    if not normalized:
        raise ValueError("email must not be empty")
    if len(normalized) > EMAIL_MAX_CHARS:
        raise ValueError(f"email must be at most {EMAIL_MAX_CHARS} characters")
    if normalized.count("@") != 1:
        raise ValueError("email must contain exactly one @")
    if any(char.isspace() for char in normalized):
        raise ValueError("email must not contain whitespace")
    if not _EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("email is not a valid address")
    return normalized


class AdminOut(BaseModel):
    """One row of the administrator registry, as the Super Admin sees it.

    ``name`` is DERIVED from ``email`` by the backend
    (``admin_auth.display_name_from_email``): the database stores the address
    only, so the label can never drift from the identity it describes.
    """

    id: int
    email: str
    name: str
    created_at: datetime


class AdminCreateIn(BaseModel):
    """The add-administrator form: an e-mail and nothing else.

    Identity is not a request field — this model creates a ROW, it does not
    authenticate anybody. Pydantic's default ``extra="ignore"`` stays, so a
    forged ``name`` / ``id`` / ``is_super_admin`` field is silently dropped
    rather than honoured.
    """

    email: str = Field(min_length=1, max_length=EMAIL_MAX_CHARS)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _validated_email(value)