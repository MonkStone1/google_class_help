"""Google's three date formats, parsed (ADR-0039 split).

Split out of ``gapi/classroom.py`` because these are pure PARSING rules with no
network and no client: they take a dict from the API and return a datetime, or
``None`` when the field is absent. Being free of I/O is what makes them testable
without a Classroom service, which is the only reason they were ever a problem.

The three formats are NOT interchangeable and Classroom uses all three in the
same payload:

- ``{"date": ...}`` / ``{"date": ..., "time": ...}`` — the CourseWork resource
- an RFC 3339 string — userinfothis needs its own branch
- a bare epoch-seconds number — submissions

Every one of them returns ``None`` for a missing value rather than raising:
Google omits these fields freely, and a cache row with a null timestamp is
normal while a request that 500s on one is not.
"""

from datetime import datetime


def parse_date(raw: dict | None) -> datetime | None:
    """Parse a Classroom API ``Date`` object into a naive datetime."""
    if not raw:
        return None
    try:
        return datetime(  # noqa: DTZ001 - naive local dates: the whole cache stores naive datetimes
            raw["year"], raw["month"], raw["day"]
        )
    except (KeyError, TypeError, ValueError):
        return None


def parse_date_time(date_raw: dict | None, time_raw: dict | None) -> datetime | None:
    """Parse ``dueDate`` + ``dueTime`` into a naive local datetime.

    Classroom returns dates without a timezone; for a personal local
    application the due moment is interpreted in local time.
    """
    date_part = parse_date(date_raw)
    if not date_part:
        return None
    hours = 23
    minutes = 59
    if time_raw:
        try:
            hours = int(time_raw.get("hours", 23))
            minutes = int(time_raw.get("minutes", 59))
        except (TypeError, ValueError):
            pass
    return date_part.replace(hour=hours, minute=minutes)


def parse_rfc3339(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
