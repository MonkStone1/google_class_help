"""In-process operational counters (migration stage 9, §60).

Observability without new infrastructure: the migration prompt asks for
enough logging/metrics to understand who is active, how often sign-ins and
syncs succeed, how long a sync takes and how much Google quota is being
consumed — but explicitly forbids adding Redis/Prometheus-style components
"solely because the application has 1,000 registered users" (§88). So the
counters live in this process, are exposed through :func:`snapshot`, and a
single summary line is logged periodically by the worker (see
``sync_scheduler``/``sync_worker``).

Rules kept from §42/§60:

- counters are keyed by event NAME only — never by email, student name or
  any other personal data; per-user correlation stays in the log lines that
  already carry the local numeric user id;
- a missing counter reads as 0, so new events need no registration;
- recording never raises and never blocks a request (a plain dict under a
  lock; the work is a few hundred nanoseconds).
"""

import logging
import threading
from collections import Counter

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_counters: Counter[str] = Counter()

# Event names, kept as constants so call sites and the periodic log agree.
LOGIN_SUCCEEDED = "login_succeeded"
LOGIN_FAILED = "login_failed"
LOGOUT = "logout"
SESSION_REJECTED = "session_rejected"
SYNC_SUCCEEDED = "sync_succeeded"
SYNC_FAILED = "sync_failed"
SYNC_NEEDS_REAUTH = "sync_needs_reauth"
SYNC_JOB_CRASHED = "sync_job_crashed"
SESSION_PURGED = "session_purged"
LOGIN_STATE_PURGED = "login_state_purged"


def record(event: str, amount: int = 1) -> None:
    """Increment one event counter (§60). Never raises."""
    try:
        with _lock:
            _counters[event] += amount
    except Exception:
        logger.debug("Metrics counter %r could not be updated.", event, exc_info=True)


def snapshot() -> dict[str, int]:
    """A copy of every counter (safe to log or assert on)."""
    with _lock:
        return dict(_counters)


def log_snapshot(context: str = "periodic") -> dict[str, int]:
    """Log and return the current counters as one structured line (§60)."""
    values = snapshot()
    if values:
        logger.info(
            "metrics[%s] %s",
            context,
            " ".join(f"{name}={count}" for name, count in sorted(values.items())),
        )
    return values


def reset() -> None:
    """Clear every counter — tests only; production never needs a reset."""
    with _lock:
        _counters.clear()
