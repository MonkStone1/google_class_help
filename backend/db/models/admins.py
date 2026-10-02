"""The administrator registry (ADR-0036).

Separate module, following the ``models_feedback.py`` precedent: a new domain
gets its own models file instead of more classes appended to the cache schema.

Invariants:

- **The e-mail IS the identity.** It is stored normalized (trim + lower-case,
  ``config.normalize_email``), so exactly one row can exist per person and two
  spellings of one address can never become two administrators.
- **There is no name column.** The display name shown in the console is
  DERIVED from the stored address by the backend
  (``admin_auth.display_name_from_email``): deterministic, needs no Google
  lookup, and cannot drift from the address it came from. An editable name
  field would be a second source of identity with nothing to keep it honest.
- **There is deliberately NO foreign key to ``users``.** An administrator may
  be appointed before they ever sign in, and ``maintenance.delete_user_data``
  must not silently revoke a role. Orphan rows are the intended behaviour, not
  a leak to clean up.
- **The Super Admin is deliberately absent from this table.** Their identity
  lives only in the ``SUPER_ADMIN_EMAIL`` environment value, which is exactly
  why the management API can never delete them: there is no row to point at.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Admin(Base):
    """One normal administrator, identified by e-mail."""

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The authoritative identifier, stored normalized (strip + lowercase) so
    # the unique index is the "one row per person" rule itself.
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # Naive UTC, like every other timestamp in this schema.
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)