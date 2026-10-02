"""Which user syncs when: the scan/queue/execute loop (ADR-0023, ADR-0039).

This package is the entry point:

- ``due``  — the pure time arithmetic (stagger, backoff, the due query)
- ``_scan``— the ``SyncScheduler`` class that owns the thread pool and the loop

The split is the reason ``due.py`` can be tested without starting a thread:
"who is due" and "how many may run at once" are different questions, and the
class answers only the second one.

Callers import ``sync.scheduler``; the names below are the objects themselves,
so a monkeypatch on ``due`` is visible to the class that calls them.
"""

from sync.scheduler._scan import SyncScheduler, start, stop
from sync.scheduler.due import (
    next_sync_at,
    retry_delay_seconds,
    run_user,
    select_due_users,
    stagger_offset_seconds,
    sync_users,
)

__all__ = [
    "SyncScheduler",
    "next_sync_at",
    "retry_delay_seconds",
    "run_user",
    "select_due_users",
    "stagger_offset_seconds",
    "start",
    "stop",
    "sync_users",
]
