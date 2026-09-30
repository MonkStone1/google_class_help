"""Business-logic facade (review §2.2).

The former single sync.py is split into three layers; this module only
re-exports them so existing callers (api.py, background_sync.py) keep their
imports:

- ``grading.py``      — pure domain rules (status, percent, priority);
- ``sync_store.py``   — everything that writes/reads the SQLite cache;
- ``sync_service.py`` — orchestration: pull from Google, call the store.

Import layers directly in new code; this facade exists for compatibility.
"""

from grading import (  # noqa: F401
    SUBMITTED_STATES,
    compute_priority,
    derive_submission_status,
    grade_percent,
    is_submitted_state,
)
from sync_service import (  # noqa: F401
    SERVER_BUSY,
    SUPERSEDED,
    restart_stuck_sync,
    sync_now,
    sync_user_id,
)
from sync_store import (  # noqa: F401
    SYNC_ERROR,
    SYNC_NEEDS_REAUTH,
    SYNC_OK,
    SYNC_PENDING,
    SYNC_RUNNING,
    SubmissionRow,
    abandon_claim,
    get_submission,
    last_sync_error,
    last_sync_time,
    request_sync,
    reset_cache,
    sync_status,
)
