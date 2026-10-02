"""The vocabulary both halves of a sync share (ADR-0039).

The outcome codes are the contract with the frontend: they are the only part of
a sync run the UI ever sees, and ``schemas.SyncResult`` mirrors them one for
one. Keeping them here rather than in the fetch half means the write half can
report ``superseded`` without importing the module that produced the claim it
lost — which is exactly the situation in which it needs to report it.

``public_error`` lives here for the same reason: deciding what is safe to show
a user is a policy, not part of either phase.
"""

from datetime import datetime, timezone

# Outcome codes. The frontend branches on these exact strings.
ALREADY_RUNNING = "already_running"
NOT_SIGNED_IN = "not_signed_in"
NEEDS_REAUTH = "needs_reauth"
COURSES_FAILED = "courses_failed"
# A run whose claim was taken over by a newer one (ADR-0032). The newer run
# will report its own outcome, so this run must NOT overwrite the status row.
SUPERSEDED = "superseded"


def now() -> datetime:
    """Naive UTC — the timestamp convention of every user-scoped table."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def public_error(exc: Exception) -> str:
    """Short, user-safe description of a failed sync (section 18).

    Raw exception text (Google's HTTP error body, request URLs, payload
    fragments) stays in the log; the dashboard only needs to know how to react.
    The HTTP status is read defensively: ``googleapiclient`` errors expose
    ``resp.status``, anything else falls back to a generic sentence that carries
    no exception detail at all.
    """
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 401:
        return NEEDS_REAUTH
    if status == 403:
        return "Google denied access to Classroom data; please sign in again."
    if status == 429:
        return "Google rate limit reached; the next sync will retry."
    if isinstance(status, int):
        return f"Google API error (HTTP {status}); the next sync will retry."
    return "Sync failed; see the server log for details."
