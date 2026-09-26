#!/usr/bin/env python3
"""Sample container CPU/RAM and PostgreSQL counters during a load run.

``tools/load_test.py`` measures the service from the outside (latency, status
codes). This tool measures the machine from the outside too — the other half
of the §88 acceptance criteria, which is written in DEPLOYMENT_CHECKLIST.md §8
as "docker stats --no-stream in parallel with the load".

Why a script and not a manual second terminal: the interesting numbers are
the PEAKS. CPU that never exceeds 60% and RAM that grows monotonically are
invisible in a screenshot taken after the run, and an OOM kill of the web
container during a load test is exactly the failure this is meant to catch.
Sampling every couple of seconds and keeping every row makes the peak
recoverable afterwards, from the CSV.

It also samples the two database counters that explain WHY latency moved:

- ``pg_stat_activity`` connection count vs ``DB_POOL_SIZE + MAX_OVERFLOW``.
  The prod profile is 3 + 2 = 5 (ADR-0028 §2.2); a web process that holds
  exactly that many connections while latency climbs is a pool-bound run, and
  the fix is a knob in .env, not a code change.
- ``sync_status WHERE sync_requested`` — the sync queue depth. A queue that
  grows during a read-only run and never drains means the worker is behind
  (§19/§63); a read-only run must leave it flat.

Usage (from the project root):

    # one terminal
    python tools/loadtest_watch.py --duration 180 --out loadtest

    # another terminal
    python tools/load_test.py --base-url http://127.0.0.1:8000 ...

Stop with Ctrl+C; the CSV is flushed on every sample, so an interrupted run
still leaves usable data. Only the Python standard library is used, so the
same file runs on the VPS with a bare python.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Compose files of the local stand. The load-test override is listed too so
# the same command works whichever of the two is currently up.
COMPOSE_FILES = ("compose.local.yml", "compose.loadtest.yml")
ENV_FILE = ".env.local"
# Services of the local stand; postgres is the only one that answers SQL.
POSTGRES_SERVICE = "postgres"
WEB_SERVICE = "web"
# '10.5MiB / 15.52GiB' -> bytes on both sides; docker prints binary units.
_MEM_RE = re.compile(r"([\d.]+)\s*([KMG]i?B)", re.IGNORECASE)
_MEM_FACTOR = {"b": 1, "kb": 1000, "mb": 1000**2, "gb": 1000**3, "tb": 1000**4}
_MEM_FACTOR_BIN = {
    "b": 1,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}


def _to_mb(value: str, unit: str) -> float:
    """Human docker size → MiB, honouring the binary KiB/MiB/GiB units."""
    factor = _MEM_FACTOR_BIN.get(unit.lower().replace("i", "i"))
    if factor is None:
        factor = _MEM_FACTOR.get(unit.lower(), 1)
    return float(value) * factor / (1024 * 1024)


def _parse_mem(text: str) -> tuple[float, float]:
    """'12.3MiB / 15.52GiB' → (12.3, 15872.0) in MiB; (0, 0) if unparsable."""
    parts = [p.strip() for p in text.split("/")]
    if len(parts) != 2:
        return 0.0, 0.0
    out: list[float] = []
    for part in parts:
        match = _MEM_RE.search(part)
        out.append(_to_mb(match.group(1), match.group(2)) if match else 0.0)
    return out[0], out[1]


@dataclass
class Sample:
    ts: float
    service: str
    cpu_percent: float
    mem_mb: float
    mem_limit_mb: float
    # CPU quota of this container in cores; 0.0 = unlimited. Kept per sample so
    # a container recreated with a different limit mid-run is noticed.
    cpu_limit_cores: float
    db_connections: int
    sync_queue_depth: int


def _compose_base() -> list[str]:
    """`docker compose` invocation for the local stand (files that exist)."""
    files = [name for name in COMPOSE_FILES if Path(name).is_file()]
    if not files:
        raise RuntimeError(
            "neither compose.local.yml nor compose.loadtest.yml is in the "
            "current directory — run this from the project root"
        )
    base = ["docker", "compose", "--env-file", ENV_FILE]
    for name in files:
        base += ["-f", name]
    return base


def _run(cmd: list[str], timeout: float = 20.0) -> str:
    """Run a command and return stdout; empty string on any failure.

    Failures are expected here (a container may be restarting mid-run), and a
    sampler that dies on the first hiccup is worse than one that skips a
    sample, so every error is swallowed and reported as an empty result.
    """
    try:
        done = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def _cpu_quotas() -> dict[str, float]:
    """Container name → CPU quota in cores (nanocpus/1e9), 0.0 = unlimited.

    Why the tool needs this: a container capped at ``cpus: 0.35`` can never
    report more than ~35% on `docker stats`, so the checklist's "CPU is not at
    100%" is vacuous on the resource-capped stand. The meaningful reading is
    "how close to its own quota did it get" — a web container pinned at its
    limit was throttled for the whole run, which is a saturation signal even
    though no number looks high.
    """
    out = _run(["docker", "ps", "--format", "{{.Names}}"])
    quotas: dict[str, float] = {}
    for name in out.split():
        detail = _run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.HostConfig.NanoCpus}} {{.HostConfig.CpuQuota}} {{.HostConfig.CpuPeriod}}",
                name,
            ],
            timeout=10.0,
        ).strip()
        if not detail:
            continue
        nano, quota, period = (detail.split() + ["0", "0", "0"])[:3]
        try:
            value = int(nano) / 1e9
            if value <= 0 and int(quota) > 0 and int(period) > 0:
                value = int(quota) / int(period)
        except ValueError:
            value = 0.0
        quotas[name] = round(value, 3)
    return quotas


def _docker_stats() -> list[Sample]:
    """One `docker stats --no-stream` sample of every container.

    The format string is explicit on purpose: the human-readable table is not
    a stable interface, and this file has to keep working on the VPS.
    """
    out = _run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}",
        ]
    )
    quotas = _cpu_quotas()
    now = time.time()
    samples: list[Sample] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, cpu, mem = parts
        numeric = cpu.rstrip("%").replace(".", "", 1)
        cpu_value = float(cpu.rstrip("%")) if numeric.isdigit() else 0.0
        used, limit = _parse_mem(mem)
        samples.append(
            Sample(
                ts=now,
                service=name,
                cpu_percent=cpu_value,
                mem_mb=round(used, 1),
                mem_limit_mb=round(limit, 1),
                cpu_limit_cores=quotas.get(name, 0.0),
                db_connections=-1,
                sync_queue_depth=-1,
            )
        )
    return samples


def _db_counters() -> tuple[int, int]:
    """(pg connections, sync queue depth) for the local database.

    -1 means "could not be read", which is different from "zero" and must not
    be averaged into the report as if the database were idle.
    """
    sql = (
        "select (select count(*) from pg_stat_activity "
        "where datname = current_database()), "
        "(select count(*) from sync_status where sync_requested)"
    )
    out = _run(
        _compose_base()
        + [
            "exec",
            "-T",
            POSTGRES_SERVICE,
            "psql",
            "-U",
            _pg_user(),
            "-d",
            _pg_database(),
            "-Atc",
            sql,
        ]
    ).strip()
    if not out:
        return -1, -1
    # psql -At may print the NOTICE lines before the result; take the last
    # line that is exactly two integers.
    for line in reversed(out.splitlines()):
        parts = line.split("|")
        if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
            return int(parts[0]), int(parts[1])
    return -1, -1


def _env_value(key: str, default: str) -> str:
    """Read one key from .env.local without sourcing the file into the shell."""
    path = Path(ENV_FILE)
    if not path.is_file():
        return default
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip() or default
    return default


def _pg_user() -> str:
    return _env_value("POSTGRES_USER", "google_class_help_local")


def _pg_database() -> str:
    return _env_value("POSTGRES_DB", "google_class_help_local")


def _summarize(samples: list[Sample]) -> dict[str, dict[str, float]]:
    """Peak CPU / peak RAM / last counter value per container."""
    out: dict[str, dict[str, float]] = {}
    for sample in samples:
        entry = out.setdefault(
            sample.service,
            {
                "samples": 0,
                "cpu_peak": 0.0,
                "mem_peak_mb": 0.0,
                "mem_limit_mb": sample.mem_limit_mb,
                "cpu_limit_cores": sample.cpu_limit_cores,
                "db_connections_max": 0,
                "sync_queue_depth_max": 0,
            },
        )
        entry["samples"] += 1
        entry["cpu_peak"] = max(entry["cpu_peak"], sample.cpu_percent)
        entry["mem_peak_mb"] = max(entry["mem_peak_mb"], sample.mem_mb)
        if sample.db_connections >= 0:
            entry["db_connections_max"] = max(
                entry["db_connections_max"], sample.db_connections
            )
        if sample.sync_queue_depth >= 0:
            entry["sync_queue_depth_max"] = max(
                entry["sync_queue_depth_max"], sample.sync_queue_depth
            )
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sample container CPU/RAM and PostgreSQL counters during a run."
    )
    parser.add_argument(
        "--out",
        default="loadtest",
        help="directory for docker-stats.csv / db-stats.csv / watch-summary.json",
    )
    parser.add_argument(
        "--interval", type=float, default=2.0, help="seconds between samples"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="stop after this many seconds; 0 = run until Ctrl+C",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="do not query PostgreSQL (container stats only)",
    )
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    if args.interval <= 0:
        print("--interval must be positive", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stats_path = out_dir / "docker-stats.csv"
    db_path = out_dir / "db-stats.csv"

    stats_fields = [
        "ts",
        "service",
        "cpu_percent",
        "mem_mb",
        "mem_limit_mb",
        "cpu_limit_cores",
        "db_connections",
        "sync_queue_depth",
    ]
    # Opened line-buffered and flushed per row: an interrupted run (Ctrl+C, a
    # wedged container, a closed terminal) must still leave a readable CSV.
    with (
        stats_path.open("w", encoding="utf-8", newline="") as stats_file,
        db_path.open("w", encoding="utf-8", newline="") as db_file,
    ):
        stats_writer = csv.DictWriter(stats_file, fieldnames=stats_fields)
        stats_writer.writeheader()
        db_writer = csv.writer(db_file)
        db_writer.writerow(["ts", "db_connections", "sync_queue_depth"])

        collected: list[Sample] = []
        started = time.time()
        print(
            f"sampling every {args.interval}s into {stats_path} (Ctrl+C to stop)",
            flush=True,
        )
        try:
            while True:
                tick = time.time()
                connections, depth = (-1, -1) if args.skip_db else _db_counters()
                rows = _docker_stats()
                for sample in rows:
                    sample.db_connections = connections
                    sample.sync_queue_depth = depth
                    stats_writer.writerow(
                        {
                            "ts": round(sample.ts, 3),
                            "service": sample.service,
                            "cpu_percent": sample.cpu_percent,
                            "mem_mb": sample.mem_mb,
                            "mem_limit_mb": sample.mem_limit_mb,
                            "cpu_limit_cores": sample.cpu_limit_cores,
                            "db_connections": connections,
                            "sync_queue_depth": depth,
                        }
                    )
                    collected.append(sample)
                if connections >= 0:
                    db_writer.writerow([round(tick, 3), connections, depth])
                stats_file.flush()
                db_file.flush()

                if not rows:
                    print(
                        "no containers reported by docker stats — is the stand up?",
                        file=sys.stderr,
                        flush=True,
                    )
                elapsed = time.time() - started
                if args.duration and elapsed >= args.duration:
                    break
                # Subtract the sampling cost from the sleep, otherwise the
                # effective interval drifts by the psql/docker exec time.
                time.sleep(max(0.0, args.interval - (time.time() - tick)))
        except KeyboardInterrupt:
            print("\nstopped by Ctrl+C", flush=True)

    summary = {
        "started": started,
        "finished": time.time(),
        "interval": args.interval,
        "samples": len(collected),
        "containers": _summarize(collected),
    }
    (out_dir / "watch-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    for service, entry in sorted(summary["containers"].items()):
        print(
            f"{service:<32} cpu_peak={entry['cpu_peak']:>6.1f}%  "
            f"mem_peak={entry['mem_peak_mb']:>8.1f}MB / "
            f"{entry['mem_limit_mb']:.0f}MB  "
            f"db_conn_max={entry['db_connections_max']}  "
            f"queue_max={entry['sync_queue_depth_max']}"
        )
    print(f"csv           : {stats_path}, {db_path}")
    print(f"summary       : {out_dir / 'watch-summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
