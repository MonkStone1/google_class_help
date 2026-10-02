"""Cache write layer: everything that writes Classroom data into the cache.

This package is the entry point; the work lives in three modules chosen by what
they are FOR, not by size:

- ``status``  — the sync-status row: claim, progress, release
- ``cache``   — the two-table submission read and the destructive purges
- ``writing`` — the Google payload → cache row translation and the upserts

Callers keep importing ``sync.store`` and get the same names they always did.
The names below are re-bound to the function objects, so a monkeypatch of
``sync.store.upsert_submission`` is visible to whoever reads it through this
facade — which is why the facade exists at all instead of each caller reaching
into a submodule.
"""

from sync.store.cache import (
    SubmissionRow,
    get_submission,
    reset_cache,
)
from sync.store.status import (
    SYNC_ERROR,
    SYNC_NEEDS_REAUTH,
    SYNC_OK,
    SYNC_PENDING,
    SYNC_RUNNING,
    abandon_claim,
    claim_is_own,
    claim_sync,
    last_sync_error,
    last_sync_time,
    mark_sync_failed,
    mark_sync_needs_reauth,
    mark_sync_pending,
    mark_sync_succeeded,
    release_claim,
    request_sync,
    sync_status,
)
from sync.store.writing import (
    upsert_submission,
)

__all__ = [
    "SYNC_ERROR",
    "SYNC_NEEDS_REAUTH",
    "SYNC_OK",
    "SYNC_PENDING",
    "SYNC_RUNNING",
    "SubmissionRow",
    "abandon_claim",
    "claim_is_own",
    "claim_sync",
    "get_submission",
    "last_sync_error",
    "last_sync_time",
    "mark_sync_failed",
    "mark_sync_needs_reauth",
    "mark_sync_pending",
    "mark_sync_succeeded",
    "release_claim",
    "request_sync",
    "reset_cache",
    "sync_status",
    "upsert_submission",
]
