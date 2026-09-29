#!/usr/bin/env python3
"""One verdict for a load run: latency, resources, database, logs.

The acceptance criteria of §88 are spread over three places: the latency and
status thresholds live in ``tools/load_test.py``, the RAM/CPU limits live in
the compose file, and the "no new quota_errors / no crashes" criterion only
exists in the container logs. Reading three artefacts after every run is how
a limit quietly stops being checked, so this tool joins them into a single
PASS/FAIL with the exit code to put in a checklist.

Inputs (all optional except the load report; a missing input is reported as
"not measured", never as "fine"):

  loadtest/run.json          --json-out of tools/load_test.py
  loadtest/watch-summary.json or loadtest/docker-stats.csv
                              --out of tools/loadtest_watch.py
  loadtest/web.log           docker compose logs web  (or worker)

Usage (from the project root):

    python tools/loadtest_report.py --load-json loadtest/run.json \\
        --watch-json loadtest/watch-summary.json \\
        --log-file loadtest/web.log --log-file loadtest/worker.log

    # or let it collect the logs itself
    python tools/loadtest_report.py --dir loadtest --collect-logs

Exit code 0 = every measured criterion passed, 1 = at least one failed or a
measured criterion is unknown, 2 = usage/IO error. A criterion that could not
be measured counts as NOT passed on purpose: "we did not check" and "it is
fine" must not look the same in a deployment checklist.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Resource ceilings from compose.yml / compose.loadtest.yml (ADR-0028 §2.2).
# The load-test override applies exactly these, so a run under it is judged
# against the production budget rather than the 8-core/32GB developer box.
DEFAULT_LIMITS_MB = {"web": 256.0, "worker": 160.0, "postgres": 288.0}
# Which compose service each container belongs to, by name fragment. The
# project name prefix ("google-class-help-local-web-1") and the throwaway
# container name ("gch-lt-web") both have to resolve.
SERVICE_MATCHERS = (
    ("web", "web"),
    ("worker", "worker"),
    ("postgres", "postgres"),
)

# Log patterns that must NOT appear after a run (§88: no crashes, no quota
# growth, no pool exhaustion). Checked per line, case-insensitively.
LOG_FORBIDDEN = (
    ("queuepool", "DB pool exhausted (QueuePool timeout) — the run was pool-bound"),
    ("max retries exceeded", "retry storm against Google"),
    ("out of memory", "process ran out of memory"),
    ("traceback (most recent call last)", "unhandled exception in the log"),
)
# Informational: counted, not failed. quota_errors is a gate for RAISING
# limits (ADR-0027 §7), not for the run to be rejected.
LOG_COUNTED = (
    ("quota_errors=", "quota_errors reported by a sync"),
    ("google_requests=", "Google requests reported by a sync"),
    ("metrics[", "metrics snapshot line"),
    (" 500 ", "HTTP 500 in the access log"),
    (" 429 ", "HTTP 429 in the access log"),
)
_COUNT_RE = re.compile(r"(\d+)")


@dataclass
class Check:
    """One acceptance criterion.

    ``informational`` marks a row that is reported but never decides the
    verdict: ``quota_errors`` is the gate for RAISING limits (ADR-0027 §7),
    not a reason to reject a run, and the arrival schedule only exists in
    open-loop mode. Without that distinction a run where nothing bad
    happened would still be "INCOMPLETE" purely for being quiet.
    """

    name: str
    ok: bool | None
    detail: str
    informational: bool = False

    @property
    def mark(self) -> str:
        if self.informational:
            return "INFO"
        if self.ok is True:
            return "PASS"
        return "FAIL" if self.ok is False else "SKIP"


def _service_of(container: str) -> str | None:
    """Map a docker container name to a compose service, or None."""
    lowered = container.lower()
    for service, fragment in SERVICE_MATCHERS:
        if fragment in lowered:
            return service
    return None


def _check_latency(report: dict[str, Any]) -> Check:
    latency = report.get("latency_ms") or {}
    p95 = latency.get("p95")
    limit = (report.get("thresholds") or {}).get("max_p95_ms", 500.0)
    if p95 is None:
        return Check("p95 latency", None, "no latency sample in the report")
    detail = (
        f"p95={p95}ms (limit {limit}ms), p50={latency.get('p50')}ms, "
        f"p99={latency.get('p99')}ms"
    )
    # With --repeat, show the spread: a single sample near the threshold cannot
    # be told apart from noise, and the whole point of repeating is that spread.
    runs = report.get("runs") or []
    if runs:
        p95s = [one.get("p95", 0) for one in runs if isinstance(one, dict)]
        if p95s:
            detail += (
                f"; {len(p95s)} runs p95 min={min(p95s):.0f} max={max(p95s):.0f} ms"
            )
    return Check("p95 latency", p95 <= limit, detail)


def _check_errors(report: dict[str, Any]) -> Check:
    five_xx = int(report.get("five_xx") or 0)
    transport = int(report.get("errors") or 0)
    limit = int((report.get("thresholds") or {}).get("max_5xx", 0))
    ok = five_xx <= limit and transport == 0
    return Check(
        "5xx and transport errors",
        ok,
        f"5xx={five_xx} (allowed {limit}), transport={transport}",
    )


def _check_ok_responses(report: dict[str, Any]) -> Check:
    expected = int((report.get("thresholds") or {}).get("expect_status") or 0)
    statuses = report.get("statuses") or {}
    if expected:
        got = int(statuses.get(str(expected), 0))
        return Check(
            "expected status present",
            got > 0,
            f"{expected} x {got} (this scenario expects refusals, not 200s)",
        )
    refused = report.get("refused") or {}
    ok = int(report.get("ok") or 0)
    note = f"ok={ok}"
    if refused:
        note += f", documented refusals={refused}"
    return Check("2xx/3xx responses", ok > 0, note)


def _check_scheduler_lag(report: dict[str, Any]) -> Check:
    lag = int(report.get("scheduler_lag") or 0)
    if report.get("mode") != "open-loop":
        return Check(
            "arrival schedule",
            None,
            "closed-loop run: no arrival rate to fall behind (informational)",
            informational=True,
        )
    return Check(
        "arrival schedule",
        lag == 0,
        f"{lag} late arrivals — the offered rate exceeded what the server took",
    )


def _load_watch(path: Path) -> dict[str, Any]:
    """watch-summary.json if present, else rebuild a summary from the CSV."""
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    csv_path = path.parent / "docker-stats.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"neither {path} nor {csv_path} exists")
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    containers: dict[str, dict[str, float]] = {}
    for row in rows:
        entry = containers.setdefault(
            row["service"],
            {
                "samples": 0,
                "cpu_peak": 0.0,
                "mem_peak_mb": 0.0,
                "mem_limit_mb": float(row.get("mem_limit_mb") or 0),
                "cpu_limit_cores": float(row.get("cpu_limit_cores") or 0),
                "db_connections_max": 0,
                "sync_queue_depth_max": 0,
            },
        )
        entry["samples"] += 1
        entry["cpu_peak"] = max(entry["cpu_peak"], float(row["cpu_percent"] or 0))
        entry["mem_peak_mb"] = max(entry["mem_peak_mb"], float(row["mem_mb"] or 0))
        for key, column in (
            ("db_connections_max", "db_connections"),
            ("sync_queue_depth_max", "sync_queue_depth"),
        ):
            value = int(row.get(column) or -1)
            if value >= 0:
                entry[key] = max(entry[key], value)
    return {"samples": len(rows), "containers": containers}


def _check_memory(watch: dict[str, Any], limits: dict[str, float]) -> list[Check]:
    """Peak RAM per service against the compose budget (ADR-0028 §2.2)."""
    checks: list[Check] = []
    for container, entry in sorted((watch.get("containers") or {}).items()):
        service = _service_of(container)
        if service is None or service not in limits:
            continue
        limit = limits[service]
        peak = float(entry.get("mem_peak_mb") or 0)
        headroom = limit - peak
        checks.append(
            Check(
                f"RAM {service}",
                peak > 0 and peak <= limit,
                f"peak={peak:.0f}MB of {limit:.0f}MB ({headroom:+.0f}MB headroom)",
            )
        )
    if not checks:
        checks.append(
            Check("RAM limits", None, "no known container in the watch summary")
        )
    return checks


def _check_cpu(watch: dict[str, Any]) -> Check:
    """CPU saturation, judged against each container's OWN quota.

    The checklist says "CPU is not at 100%". That only means something on an
    uncapped container: the load-test stand runs web at ``cpus: 0.55``
    (ADR-0028 §2.2), so its peak can never exceed ~55% and the absolute
    reading would pass no matter how hard the container was throttled. A
    capped container that reaches 90% of its quota WAS saturated, and that is
    what this reports instead.
    """
    containers = watch.get("containers") or {}
    if not containers:
        return Check("CPU", None, "no container samples")
    worst = 0.0
    worst_name = ""
    notes: list[str] = []
    unknown: list[str] = []
    skipped = 0
    for container, entry in sorted(containers.items()):
        # Only the stand's own services. A one-off `docker compose run` helper
        # (the seed, the report) can be sampled while it exists and would
        # otherwise show up here as an unnamed "container" in the CPU row.
        if not container.strip() or _service_of(container) is None:
            skipped += 1
            continue
        peak = float(entry.get("cpu_peak") or 0)
        cores = float(
            entry.get("cpu_limit_cores")
            if entry.get("cpu_limit_cores") is not None
            else -1.0
        )
        if cores > 0:
            # docker stats reports host-CPU percent; a quota is a share of one
            # core, so the comparable figure is cores * 100.
            utilisation = peak / (cores * 100) * 100
            notes.append(f"{container}={utilisation:.0f}% of {cores} core(s)")
            if utilisation > worst:
                worst, worst_name = utilisation, container
        elif cores == 0.0:
            notes.append(f"{container}={peak:.0f}% (uncapped)")
            if peak > worst:
                worst, worst_name = peak, container
        else:
            # Quota unreadable: it is NOT the same as "no limit", and guessing
            # "uncapped" is what produced a bogus row in an earlier run.
            unknown.append(container)
    if unknown:
        notes.append(f"quota unknown for: {', '.join(unknown)}")
    tail = f" (skipped {skipped} non-service container(s))" if skipped else ""
    return Check(
        "CPU saturation",
        None if not notes else worst < 90.0,
        f"worst={worst_name} at {worst:.0f}% of its quota — " + "; ".join(notes) + tail,
    )


def _check_pool_and_queue(
    watch: dict[str, Any], pool_budget: int, pool_processes: int
) -> list[Check]:
    """DB connections vs the pool budget, and the sync queue depth (§88).

    ``DB_POOL_SIZE``/``DB_MAX_OVERFLOW`` describe ONE process, and the hosted
    deployment has two of them against the same database (``web`` and
    ``worker``, ADR-0023). ``pg_stat_activity`` counts both plus a few
    bookkeeping connections of PostgreSQL itself, so comparing the total with a
    single process budget reports a false failure on a healthy stand.
    """
    connections = [
        int(entry.get("db_connections_max") or 0)
        for entry in (watch.get("containers") or {}).values()
    ]
    depth = [
        int(entry.get("sync_queue_depth_max") or 0)
        for entry in (watch.get("containers") or {}).values()
    ]
    if not connections:
        return [
            Check("DB pool", None, "no db counters in the watch summary"),
            Check("sync queue", None, "no queue counters in the watch summary"),
        ]
    top_conn = max(connections)
    total_budget = pool_budget * pool_processes
    pool_ok = top_conn <= total_budget
    return [
        Check(
            "DB connections",
            pool_ok,
            f"max={top_conn} (budget {total_budget} = {pool_budget} per process "
            f"x {pool_processes} app processes: web + worker; also counts a few "
            "of PostgreSQL's own connections)"
            + ("" if pool_ok else " — above every pool: the database was the wall"),
        ),
        Check(
            "sync queue depth",
            max(depth) == 0 if depth else None,
            f"max pending sync_requested={max(depth) if depth else 'n/a'} "
            "(a read-only run must not grow the queue)",
        ),
    ]


def _check_logs(paths: list[Path]) -> list[Check]:
    """Forbidden vs merely-counted log lines (§88: no crashes, no pool death)."""
    text: list[str] = []
    read_any = False
    for path in paths:
        if path.is_file():
            read_any = True
            text.append(path.read_text(encoding="utf-8", errors="replace"))
    if not read_any:
        return [Check("container logs", None, "no log file given or found")]

    blob = "\n".join(text).lower()
    found: list[Check] = []
    for needle, explanation in LOG_FORBIDDEN:
        count = blob.count(needle)
        found.append(
            Check(
                f"log: no '{needle}'",
                count == 0,
                "clean" if count == 0 else f"{count} x {explanation}",
            )
        )
    for needle, explanation in LOG_COUNTED:
        count = blob.count(needle)
        # The count itself never decides the verdict: quota_errors in
        # particular is the gate for raising limits, not a reason to fail.
        suffix = ""
        values = _COUNT_RE.findall(blob)
        if needle == "quota_errors=" and values:
            suffix = (
                f" (largest counter value in the log: {max(int(v) for v in values)})"
            )
        found.append(
            Check(
                f"log: {explanation}",
                None,
                "not present" if count == 0 else f"{count} occurrence(s){suffix}",
                informational=True,
            )
        )
    return found


def _collect_logs(out_dir: Path, lines: int) -> list[Path]:
    """`docker compose logs` for web and worker into out_dir; best effort."""
    written: list[Path] = []
    compose = ["docker", "compose", "--env-file", ".env.local"]
    for name in ("compose.local.yml", "compose.loadtest.yml"):
        if Path(name).is_file():
            compose += ["-f", name]
    for service in ("web", "worker"):
        target = out_dir / f"{service}.log"
        try:
            done = subprocess.run(
                compose + ["logs", "--no-color", "--tail", str(lines), service],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0 and done.stdout.strip():
            target.write_text(done.stdout, encoding="utf-8")
            written.append(target)
    return written


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Join a load run's artefacts into one PASS/FAIL verdict (§88)."
    )
    parser.add_argument(
        "--load-json",
        default="loadtest/run.json",
        help="JSON report of tools/load_test.py (--json-out)",
    )
    parser.add_argument(
        "--watch-json",
        default="loadtest/watch-summary.json",
        help="summary of tools/loadtest_watch.py (falls back to its CSV)",
    )
    parser.add_argument(
        "--dir",
        default="loadtest",
        help="directory the artefacts live in; used for the default paths",
    )
    parser.add_argument(
        "--log-file",
        action="append",
        default=[],
        help="container log to scan, repeatable (default: none)",
    )
    parser.add_argument(
        "--collect-logs",
        action="store_true",
        help="run `docker compose logs` for web/worker and scan that",
    )
    parser.add_argument(
        "--pool-budget",
        type=int,
        default=5,
        help="DB_POOL_SIZE + DB_MAX_OVERFLOW of ONE process (3+2 in prod)",
    )
    parser.add_argument(
        "--pool-processes",
        type=int,
        default=2,
        help="app processes sharing the database: web + worker (ADR-0023)",
    )
    parser.add_argument(
        "--web-mem-limit",
        type=float,
        default=DEFAULT_LIMITS_MB["web"],
        help="RAM budget for the web container in MiB",
    )
    parser.add_argument(
        "--worker-mem-limit",
        type=float,
        default=DEFAULT_LIMITS_MB["worker"],
        help="RAM budget for the worker container in MiB",
    )
    parser.add_argument(
        "--postgres-mem-limit",
        type=float,
        default=DEFAULT_LIMITS_MB["postgres"],
        help="RAM budget for the postgres container in MiB",
    )
    return parser


def _render(checks: list[Check], report: dict[str, Any]) -> str:
    lines = [
        "=" * 78,
        (
            "LOAD TEST VERDICT (§88) — "
            f"{report.get('mode', '?')} "
            f"{report.get('requests', '?')} req, "
            f"concurrency {report.get('concurrency', '?')}, "
            f"{report.get('sessions_used', 0)} session(s)"
        ),
        f"target: {report.get('base_url', '?')}  paths: {', '.join(report.get('paths') or [])}",
        "=" * 78,
    ]
    width = max(len(check.name) for check in checks) + 2
    for check in checks:
        lines.append(f"  [{check.mark}] {check.name.ljust(width)}{check.detail}")
    # Informational rows (INFO) are never counted: a run that was simply quiet
    # is not an incomplete run.
    failed = [c for c in checks if c.ok is False and not c.informational]
    skipped = [c for c in checks if c.ok is None and not c.informational]
    passed = sum(1 for c in checks if c.ok is True and not c.informational)
    info = sum(1 for c in checks if c.informational)
    lines.append("-" * 78)
    lines.append(
        f"  {passed} passed, {len(failed)} failed, {len(skipped)} not measured, "
        f"{info} informational"
    )
    if failed:
        lines.append("  VERDICT: FAIL — " + "; ".join(check.name for check in failed))
    elif skipped:
        lines.append(
            "  VERDICT: INCOMPLETE — criteria were not measured: "
            + "; ".join(check.name for check in skipped)
        )
    else:
        lines.append("  VERDICT: PASS")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    out_dir = Path(args.dir)
    load_path = Path(args.load_json)
    watch_path = Path(args.watch_json)
    if not load_path.is_file() and not Path(args.load_json).is_absolute():
        load_path = out_dir / "run.json"
    if not watch_path.is_file() and not Path(args.watch_json).is_absolute():
        watch_path = out_dir / "watch-summary.json"

    if not load_path.is_file():
        print(
            f"ERROR: no load report at {load_path} — run tools/load_test.py with "
            "--json-out first",
            file=sys.stderr,
        )
        return 2
    try:
        report = json.loads(load_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {load_path}: {exc}", file=sys.stderr)
        return 2

    checks = [
        _check_latency(report),
        _check_errors(report),
        _check_ok_responses(report),
        _check_scheduler_lag(report),
    ]

    limits = {
        "web": args.web_mem_limit,
        "worker": args.worker_mem_limit,
        "postgres": args.postgres_mem_limit,
    }
    try:
        watch = _load_watch(watch_path)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"warning: no watch data ({exc})", file=sys.stderr)
        watch = {}
    if watch:
        checks += _check_memory(watch, limits)
        checks.append(_check_cpu(watch))
        checks += _check_pool_and_queue(watch, args.pool_budget, args.pool_processes)
    else:
        checks.append(Check("container resources", None, "loadtest_watch.py not run"))

    log_paths = [Path(item) for item in args.log_file]
    if args.collect_logs:
        log_paths += _collect_logs(out_dir, lines=2000)
    checks += _check_logs(log_paths)

    print(_render(checks, report))

    if any(check.ok is False and not check.informational for check in checks):
        return 1
    if any(check.ok is None and not check.informational for check in checks):
        print(
            "\nnote: unmeasured criteria do not count as a pass — a deployment "
            "checklist may not tick a box that was never checked",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
