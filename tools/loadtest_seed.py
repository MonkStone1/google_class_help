#!/usr/bin/env python3
"""Seed the local load-test stand with synthetic users, sessions and cache.

Why this exists: every data endpoint of the hosted service is behind the
session gate (§50), so an authenticated load run needs N valid
``gch_session`` cookies. Getting them the honest way means N real Google
OAuth logins. But a session is only a random token stored as its SHA-256
hash (models_auth.UserSession, hosted_auth._create_session), so a test stand
can mint its own — no Google account, no OAuth client, no token to leak.

What it writes, per synthetic user (``provider_subject`` LIKE 'loadtest-%'):

- ``users``            — a local identity, active, with a fresh login stamp;
- ``sessions``         — one live session, hash only, expiry in 14 days
                         (the same TTL the app uses);
- ``courses``          — a realistic number of ACTIVE courses, so the read
                         endpoints do not answer "[]" and cost nothing;
- ``course_roles``     — TEACHER for the first ``--teachers`` users, so the
                         teacher-gated endpoints are reachable (ADR-0024);
- ``coursework``       — work with mixed states and due dates spread over
                         past/future, which is what makes /assignments,
                         /grades and /calendar return real aggregates;
- ``submissions``      — the student's own submissions (TURNED_IN/RETURNED/
                         missing mix) so average-grade maths is exercised;
- ``course_students`` + ``coursework_submissions`` — for teachers: a roster
                         and graded submissions, i.e. the most expensive
                         SELECTs in the API surface;
- ``sync_status``      — a healthy "ok" row with recent timestamps, so the
                         worker does not immediately try to sync these users
                         and the UI paths behave as after a real login.

It writes NO ``oauth_tokens``: the synthetic users have no Google grant, so a
real Classroom fan-out is impossible for them by construction. Measuring
``google_requests`` therefore stays a one-real-account exercise (scenario S8),
exactly as ADR-0027 §7 frames it.

Scope safety: only rows whose ``provider_subject`` starts with
``loadtest-`` are ever written or deleted, and ``--reset`` removes exactly
those. A real user's cache is never touched. The tool refuses to run against
a database that has no load-test users unless ``--reset`` was requested, so a
mistyped ``--reset`` cannot silently wipe a real account's rows.

Usage (from the project root, against the LOCAL stand only):

    # inside the compose network (postgres is not published to the host)
    docker compose --env-file .env.local -f compose.local.yml \\
        -f compose.loadtest.yml run --rm --entrypoint python web \\
        /tools/loadtest_seed.py --users 20 --teachers 4 \\
        --out /data/session-cookies.txt

    # or from the host against a published port, with DATABASE_URL set
    .venv\\Scripts\\python.exe tools\\loadtest_seed.py --users 20

Exit code 0 = seeded, 1 = database/usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

# The prefix every synthetic identity carries. Reset and cleanup key on it,
# which is what keeps real accounts out of harm's way.
SUBJECT_PREFIX = "loadtest-"
# Session TTL of the app (hosted_auth.SESSION_TTL_SECONDS), so a seeded cookie
# is indistinguishable from a real one for the length of a test run.
SESSION_TTL_DAYS = 14
# Role values the API compares against (models.CourseRole, api._role_map).
ROLE_TEACHER = "TEACHER"
ROLE_STUDENT = "STUDENT"
# Classroom submission states the grading module understands (grading.py).
SUBMITTED_STATES = ("TURNED_IN", "RETURNED")
MISSING_STATES = ("CREATED", "RECLAIMED_BY_STUDENT")


def _utcnow() -> datetime:
    """Naive UTC, the timestamp convention of every user-scoped table."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _database_url() -> str:
    """DSN for the local stand.

    ``DATABASE_URL`` is the app's own variable and is what compose injects, so
    it is preferred. The libpq ``PG*`` variables are accepted as a fallback
    because a local password may contain characters that need URL-encoding,
    and libpq takes them verbatim: re-encoding the password by hand is a
    classic source of "password authentication failed" on a stand that is
    actually configured correctly.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    if os.environ.get("PGHOST") and os.environ.get("PGPASSWORD"):
        # Empty DSN = "take everything from the PG* environment variables".
        return ""
    raise RuntimeError(
        "Neither DATABASE_URL nor PGHOST/PGPASSWORD is set. Run this inside the "
        "compose network (docker compose ... run --rm web /tools/loadtest_seed.py "
        "...), which already injects DATABASE_URL, or export the PG* variables "
        "yourself. The local stand keeps PostgreSQL on a private network, so the "
        "host cannot reach it."
    )


def _connect(url: str):
    """psycopg connection. Imported lazily so --help works without psycopg."""
    try:
        import psycopg
    except ImportError:  # pragma: no cover - environment problem, not logic
        raise RuntimeError(
            "psycopg is missing. Run with the project .venv or inside the web "
            "image (backend/requirements-prod.txt pins psycopg)."
        ) from None
    return psycopg.connect(url, autocommit=False)


def _reset(cur, subject_prefix: str) -> int:
    """Delete every synthetic user; ON DELETE CASCADE takes the cache with it.

    The parent rows are removed first and in one statement, so the composite
    foreign keys (user_id in every primary key, ADR-0021) do the rest.
    """
    cur.execute(
        "SELECT id FROM users WHERE provider_subject LIKE %s",
        (subject_prefix + "%",),
    )
    ids = [row[0] for row in cur.fetchall()]
    if not ids:
        return 0
    cur.execute("DELETE FROM users WHERE id = ANY(%s)", (ids,))
    return len(ids)


def _seed_user(cur, index: int) -> tuple[int, str]:
    """Insert one synthetic user with a live session; returns (id, token).

    The token is random and only its SHA-256 hash is stored — the same
    invariant the app keeps (models_auth.UserSession), so a leaked dump of this
    database is no worse than a leaked dump of the real one.
    """
    now = _utcnow()
    subject = f"{SUBJECT_PREFIX}{index:04d}"
    token = secrets.token_urlsafe(32)
    cur.execute(
        """
        INSERT INTO users (provider, provider_subject, email, display_name,
                           created_at, updated_at, last_login_at, is_active)
        VALUES ('google', %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING id
        """,
        (
            subject,
            f"{subject}@loadtest.invalid",
            f"Load Test User {index:04d}",
            now,
            now,
            now,
        ),
    )
    user_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO sessions (session_token_hash, user_id, created_at,
                              expires_at, last_seen_at, revoked_at, user_agent)
        VALUES (%s, %s, %s, %s, %s, NULL, %s)
        """,
        (
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
            user_id,
            now,
            now + timedelta(days=SESSION_TTL_DAYS),
            now,
            "gch-load-test/2",
        ),
    )
    return user_id, token


def _seed_courses(cur, user_id: int, index: int, args: argparse.Namespace) -> list[str]:
    """Course + role + roster rows; returns the ACTIVE course ids."""
    now = _utcnow()
    # A per-user suffix keeps ids distinct between users. The same Google id
    # may exist in two caches (ADR-0021/0022) and reusing one suffix everywhere
    # would hide exactly that isolation.
    suffix = f"{index:04d}"
    active: list[str] = []
    for course_index in range(args.courses_per_user):
        course_id = f"lt-course-{suffix}-{course_index:03d}"
        # The last course is ARCHIVED on purpose: archived rows must vanish
        # from every read (api.py filters course_state != 'ARCHIVED'), and a
        # stand without one cannot prove the filter holds.
        state = "ARCHIVED" if course_index == args.courses_per_user - 1 else "ACTIVE"
        if state == "ACTIVE":
            active.append(course_id)
        is_teacher = index < args.teachers
        cur.execute(
            """
            INSERT INTO courses (user_id, id, name, description, section, room,
                                 enrollment_state, course_state, teacher_names,
                                 synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::json, %s)
            """,
            (
                user_id,
                course_id,
                f"Load Test Course {course_index + 1}",
                "Synthetic course for the local load stand.",
                f"Section {course_index + 1}",
                f"Room {100 + course_index}",
                "ACTIVE",
                state,
                # Explicit json.dumps + an explicit ::json cast: psycopg adapts a
                # Python list to a PostgreSQL ARRAY, and the column is JSON.
                json.dumps([f"Teacher {suffix}"]),
                now,
            ),
        )
        cur.execute(
            "INSERT INTO course_roles (user_id, course_id, role) VALUES (%s, %s, %s)",
            (user_id, course_id, ROLE_TEACHER if is_teacher else ROLE_STUDENT),
        )
        for student_index in range(args.roster_per_course):
            cur.execute(
                """
                INSERT INTO course_students (user_id, course_id, student_id,
                                             full_name, email, photo_url)
                VALUES (%s, %s, %s, %s, %s, NULL)
                """,
                (
                    user_id,
                    course_id,
                    f"lt-student-{suffix}-{course_index:03d}-{student_index:03d}",
                    f"Student {student_index + 1}",
                    f"student{student_index + 1}@loadtest.invalid",
                ),
            )
    return active


def _seed_work(
    cur,
    user_id: int,
    index: int,
    course_ids: list[str],
    args: argparse.Namespace,
) -> dict[str, int]:
    """Coursework plus the submissions that make the aggregates real.

    Volume and variety are the point, not authenticity: due dates are spread
    over past and future so overdue / due-today / upcoming are all populated
    (the /assignments filters and the calendar aggregates depend on that
    distribution), and states are mixed so average_grade, completed and
    missing are non-trivial.
    """
    now = _utcnow()
    suffix = f"{index:04d}"
    is_teacher = index < args.teachers
    counts = {"coursework": 0, "submissions": 0}

    for course_index, course_id in enumerate(course_ids):
        roster = [
            f"lt-student-{suffix}-{course_index:03d}-{member:03d}"
            for member in range(args.roster_per_course)
        ]
        for work_index in range(args.coursework_per_course):
            work_id = f"lt-work-{suffix}-{course_index:03d}-{work_index:03d}"
            due = now + timedelta(days=(work_index % 21) - 10, hours=work_index % 12)
            max_points = float(10 + (work_index % 6) * 5)
            missing_state = ("CREATED", "RECLAIMED_BY_STUDENT")[work_index % 2]
            counts["coursework"] += 1
            cur.execute(
                """
                INSERT INTO coursework (user_id, course_id, id, title,
                    description, state, work_type, due_at, max_points,
                    alternate_link, materials, topic_id, creation_time,
                    updated_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::json, NULL, %s, %s)
                """,
                (
                    user_id,
                    course_id,
                    work_id,
                    f"Assignment {work_index + 1}",
                    "Synthetic coursework for the local load stand.",
                    missing_state,
                    "ASSIGNMENT",
                    due,
                    max_points,
                    f"https://classroom.google.com/c/{course_id}?_hw={work_id}",
                    json.dumps([]),
                    now - timedelta(days=30),
                    now,
                ),
            )
            if is_teacher:
                # The teacher's view of the class: the aggregate behind
                # /api/courses/{id}/grades and /submissions.
                for student_id in roster:
                    graded = work_index % 3 != 0
                    cur.execute(
                        """
                        INSERT INTO coursework_submissions
                            (user_id, course_id, coursework_id, student_id, state,
                             late, assigned_points, draft_points, attachments,
                             updated_time)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s::json, %s)
                        """,
                        (
                            user_id,
                            course_id,
                            work_id,
                            student_id,
                            "GRADED" if graded else "CREATED",
                            work_index % 5 == 0,
                            round(max_points * (0.5 + (work_index % 5) * 0.1), 1)
                            if graded
                            else None,
                            json.dumps([]),
                            now,
                        ),
                    )
            else:
                # The owner's own submission. StudentSubmission is keyed
                # (user_id, course_id, coursework_id) and has no student_id /
                # submitted_at / attachments (models.py) — the dashboard's
                # "my work" view is exactly this table.
                submitted = work_index % 3 == 0
                counts["submissions"] += 1
                cur.execute(
                    """
                    INSERT INTO submissions
                        (user_id, course_id, coursework_id, state, late,
                         assigned_points, draft_points, updated_time)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, %s)
                    """,
                    (
                        user_id,
                        course_id,
                        work_id,
                        SUBMITTED_STATES[work_index % len(SUBMITTED_STATES)]
                        if submitted
                        else "CREATED",
                        False,
                        round(max_points * 0.8, 1) if submitted else None,
                        now,
                    ),
                )
    return counts


def _seed_sync_status(cur, user_id: int, now: datetime) -> None:
    """A healthy 'ok' sync row.

    Two reasons: the worker must not immediately pick these users up for a
    Classroom fan-out they cannot perform (no oauth_tokens, by design), and
    the UI paths that read last_success_at/sync_status must see the same state
    they see after a real login.
    """
    cur.execute(
        """
        INSERT INTO sync_status (user_id, status, last_started_at,
            last_finished_at, last_success_at, last_error, last_error_at,
            consecutive_failures, sync_requested)
        VALUES (%s, 'ok', %s, %s, %s, NULL, NULL, 0, FALSE)
        """,
        (
            user_id,
            now - timedelta(minutes=5),
            now - timedelta(minutes=4),
            now - timedelta(minutes=4),
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed synthetic users/sessions/cache for the local load stand."
    )
    parser.add_argument("--users", type=int, default=10, help="synthetic users")
    parser.add_argument(
        "--teachers",
        type=int,
        default=2,
        help="how many of the first users get the TEACHER role (ADR-0024)",
    )
    parser.add_argument(
        "--courses-per-user", type=int, default=5, help="incl. one ARCHIVED course"
    )
    parser.add_argument(
        "--coursework-per-course",
        type=int,
        default=20,
        help="per active course; multiplies rows fast (5 x 20 x 10 users = 1000)",
    )
    parser.add_argument(
        "--roster-per-course",
        type=int,
        default=8,
        help="students per course; only used for TEACHER users",
    )
    parser.add_argument(
        "--out",
        default="loadtest/session-cookies.txt",
        help="where to write the `gch_session=...` lines for load_test.py",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete existing loadtest-* users (and their cache) before seeding",
    )
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    if args.users <= 0:
        return _fail("--users must be positive")
    if not 0 <= args.teachers <= args.users:
        return _fail("--teachers must be between 0 and --users")
    if args.courses_per_user < 2:
        return _fail(
            "--courses-per-user must be at least 2: one course is seeded "
            "ARCHIVED on purpose to prove the archived filter (§61)"
        )
    if args.coursework_per_course <= 0 or args.roster_per_course <= 0:
        return _fail("--coursework-per-course and --roster-per-course must be positive")

    try:
        url = _database_url()
    except RuntimeError as exc:
        return _fail(str(exc))

    try:
        with _connect(url) as connection, connection.cursor() as cur:
            if args.reset:
                removed = _reset(cur, SUBJECT_PREFIX)
                print(f"reset         : removed {removed} synthetic user(s)")
            else:
                # Seeding twice would pile up duplicate caches; the tool
                # refuses instead of guessing which run the operator meant.
                cur.execute(
                    "SELECT count(*) FROM users WHERE provider_subject LIKE %s",
                    (SUBJECT_PREFIX + "%",),
                )
                existing = cur.fetchone()
                if existing is not None and existing[0]:
                    return _fail(
                        "synthetic users already exist — re-run with --reset "
                        "to replace them (they are never touched silently)"
                    )

            cookies: list[str] = []
            totals = {"courses": 0, "coursework": 0, "submissions": 0, "roster": 0}
            for index in range(args.users):
                user_id, token = _seed_user(cur, index)
                active = _seed_courses(cur, user_id, index, args)
                counts = _seed_work(cur, user_id, index, active, args)
                _seed_sync_status(cur, user_id, _utcnow())
                totals["courses"] += len(active)
                totals["coursework"] += counts["coursework"]
                totals["submissions"] += counts["submissions"]
                totals["roster"] += (
                    len(active) * args.roster_per_course if index < args.teachers else 0
                )
                cookies.append(f"gch_session={token}")
            connection.commit()
    except Exception as exc:  # noqa: BLE001 — report, do not traceback at the CLI
        return _fail(f"{type(exc).__name__}: {exc}")

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Synthetic sessions for the local load stand.\n")
        handle.write("# Generated by tools/loadtest_seed.py — not real accounts.\n")
        handle.write("\n".join(cookies) + "\n")

    target = url or (
        f"{os.environ.get('PGHOST')}:{os.environ.get('PGPORT', '5432')}/"
        f"{os.environ.get('PGDATABASE', os.environ.get('PGUSER', ''))}"
    )
    print(f"database      : {target} (schema assumed migrated)")
    print(f"users         : {args.users} ({args.teachers} teachers)")
    print(
        f"cache rows    : courses={totals['courses']} coursework={totals['coursework']} "
        f"own submissions={totals['submissions']} roster={totals['roster']}"
    )
    print(f"cookies       : {len(cookies)} written to {out}")
    print(
        "next          : python tools/load_test.py --base-url http://127.0.0.1:8000 "
        f"--cookie-file {args.out} --per-path --path /api/status --path /api/courses "
        "--requests 500 --concurrency 20"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
