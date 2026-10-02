"""Sync orchestration, in two halves: fetch (here) and write (``results``).

This package is the entry point; the two halves are separated because they fail
differently — the fetch is slow, network-bound and retryable, the write is a
short transaction that must first confirm it still owns the claim (ADR-0032).

Callers import ``sync.service`` and get the same names as before. The three
public functions and the outcome codes are re-bound to the objects themselves,
not copied, so a monkeypatch on either half is visible through this facade.
"""

from sync.service._fetch import (
    ALREADY_RUNNING,
    COURSES_FAILED,
    NEEDS_REAUTH,
    NOT_SIGNED_IN,
    SERVER_BUSY,
    SUPERSEDED,
    build_service,
    restart_stuck_sync,
    sync_now,
    sync_user_id,
)
from sync.service.results import write_sync_results

__all__ = [
    "ALREADY_RUNNING",
    "COURSES_FAILED",
    "NEEDS_REAUTH",
    "NOT_SIGNED_IN",
    "SERVER_BUSY",
    "SUPERSEDED",
    "build_service",
    "restart_stuck_sync",
    "sync_now",
    "sync_user_id",
    "write_sync_results",
]

# The private seam ``_do_sync`` calls when the fetch is done. It is bound here
# so a test can patch ``service._write_sync_results`` and have the fetch half
# pick the replacement up — the same reason the store facade exists.
_write_sync_results = write_sync_results
