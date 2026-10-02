"""The synchronization pipeline (ADR-0039).

Six modules that were flat files named ``sync_*`` plus a facade, which made the
layer boundary invisible: anything could import anything. Here the order inside
the package IS the order of the pipeline.

    worker -> scheduler -> service -> gapi/  (fetch)
                             \\-> store      (write) -> db/

- ``grading``   — pure domain rules (status, percent, priority). No I/O at all.
- ``store``     — everything that writes or reads the Classroom cache.
- ``service``   — orchestration: pull from Google, hand it to the store.
- ``scheduler`` — which user syncs when (scan/queue/execute, ADR-0023).
- ``worker``    — the process entry point (``python -m sync.worker``).
- ``background``— the desktop single-account schedule (ADR-0015).
- ``__init__``  — the compatibility facade the API layer imports.

The facade exists because ``api/`` needs a handful of names and must not reach
into the pipeline's internals; new code imports the module it actually means
(``from sync import service``). Nothing is re-implemented here, so there is
exactly one ``sync_now`` in the process.

Budget: ≤ 400 lines per module.
"""

from sync.grading import (  # noqa: F401  (facade: re-export, see module docstring)
    SUBMITTED_STATES,
    compute_priority,
    derive_submission_status,
    grade_percent,
    is_submitted_state,
)
from sync.service import (  # noqa: F401
    ALREADY_RUNNING,
    SERVER_BUSY,
    SUPERSEDED,
    restart_stuck_sync,
    sync_now,
    sync_user_id,
)
from sync.store import (  # noqa: F401
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
