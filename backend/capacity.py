"""Capacity arithmetic for the ~1,000-user target (migration stage 9, §88).

The migration prompt asks the engineering process to QUANTIFY the Google
Classroom load instead of assuming it, and to keep the first production
configuration conservative. This module holds that arithmetic in code so
the numbers in ADR-0027 can be recomputed and tested rather than trusted:

    average requests/minute ≈ (users × requests_per_sync) / interval_minutes

Teacher accounts are not like student accounts: one teacher sync may list
courses, coursework, rosters and every submission, all paginated, so the
planning model charges them with a separate teacher request shape
(``REQUESTS_PER_TEACHER_SYNC``) on top of the plain user shape.

Nothing here calls Google or the database — it is pure planning math plus a
few reads of the configured budgets, so it is safe to import anywhere
(including a one-off ``python -c`` capacity check).
"""

from config import (
    SYNC_INTERVAL_MINUTES,
    SYNC_MAX_CONCURRENT_USERS,
    SYNC_MAX_WORKERS,
)

# Observed request shapes from the sync code (classroom_api.py), used as the
# planning defaults. Measured values from the ``google_requests=`` log line
# (sync_service) should replace them once production traffic exists.
REQUESTS_PER_STUDENT_SYNC = 3 + 2  # courses x2 + userinfo + a few point gets
REQUESTS_PER_TEACHER_SYNC = 40  # courses x2 + coursework + roster + sweep, paged

# Reference deployment of §88: 1 vCPU / 1 GB, ~1,000 registered users.
TARGET_USERS = 1000
TARGET_TEACHERS = 25


def estimate_requests_per_minute(
    *,
    users: int = TARGET_USERS,
    teachers: int = TARGET_TEACHERS,
    interval_minutes: int | None = None,
) -> float:
    """Average Google request rate of the whole installation (§88).

    One full synchronization per user per interval; every user contributes
    ``REQUESTS_PER_STUDENT_SYNC`` requests and every teacher an additional
    ``REQUESTS_PER_TEACHER_SYNC`` (they are also counted as users). The
    result is an average, not a peak: the scheduler's stagger and bounded
    concurrency decide the peak.
    """
    interval = SYNC_INTERVAL_MINUTES if interval_minutes is None else interval_minutes
    if interval <= 0:
        raise ValueError("interval_minutes must be positive")
    # Every user does a student-shaped pass (courses + userinfo + own work);
    # teachers additionally sweep coursework, rosters and submissions, so
    # their sync is charged with both shapes.
    per_interval = users * REQUESTS_PER_STUDENT_SYNC + teachers * (
        REQUESTS_PER_TEACHER_SYNC
    )
    return per_interval / interval


def estimate_requests_per_second(**kwargs) -> float:
    """The same estimate expressed per second (quota comparison, §40)."""
    return estimate_requests_per_minute(**kwargs) / 60.0


def sync_thread_budget(
    workers: int | None = None, concurrent_users: int | None = None
) -> int:
    """Threads the worker may hold at once: workers × concurrent users (§88).

    This is the number that must stay small on a 1 vCPU box: every thread
    holds a socket to Google and a slice of memory.
    """
    return (workers or SYNC_MAX_WORKERS) * (
        concurrent_users or SYNC_MAX_CONCURRENT_USERS
    )


def peak_requests_per_minute(
    *,
    users_per_sync: int,
    max_workers: int | None = None,
) -> int:
    """Worst-case request rate of one user's sync (quota headroom check).

    ``max_workers`` threads can be in flight at once, each completing one
    request per round trip, so the burst is bounded by the per-user pool —
    which is why the pool exists (§40).
    """
    return users_per_sync * (max_workers or SYNC_MAX_WORKERS)


def capacity_report(
    *,
    users: int = TARGET_USERS,
    teachers: int = TARGET_TEACHERS,
    interval_minutes: int | None = None,
) -> dict[str, float | int]:
    """One dict a deploy can log or a reviewer can read (§60/§88)."""
    return {
        "users": users,
        "teachers": teachers,
        "interval_minutes": interval_minutes or SYNC_INTERVAL_MINUTES,
        "avg_requests_per_minute": round(
            estimate_requests_per_minute(
                users=users, teachers=teachers, interval_minutes=interval_minutes
            ),
            1,
        ),
        "avg_requests_per_second": round(
            estimate_requests_per_second(
                users=users, teachers=teachers, interval_minutes=interval_minutes
            ),
            2,
        ),
        "sync_thread_budget": sync_thread_budget(),
        "max_concurrent_users": SYNC_MAX_CONCURRENT_USERS,
        "workers_per_user": SYNC_MAX_WORKERS,
    }
