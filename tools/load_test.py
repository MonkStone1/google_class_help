#!/usr/bin/env python3
"""HTTP load test for the hosted deployment (migration stage 10, §88).

Measures what the acceptance criteria ask for — request rate, latency
distribution, HTTP status breakdown — against a RUNNING server, so the same
tool works for a local sanity run and for the production VPS behind
Cloudflare. It intentionally uses only the Python standard library: no
extra dependency ships with the image.

It does NOT replace ``docker stats`` for RAM/CPU: run both side by side
(see docs/DEPLOYMENT_CHECKLIST.md §8).

Usage (from the project root):

    # local sanity run against a dev server
    python tools/load_test.py --base-url http://127.0.0.1:8000 \\
        --path /api/health --path /api/ready --requests 300 --concurrency 10

    # authenticated pass on the VPS (session cookie from a real browser login)
    python tools/load_test.py --base-url https://monkstonecor.pp.ua \\
        --path /api/status --path /api/courses \\
        --cookie gch_session=<value> --requests 500 --concurrency 20

Exit code 0 = all thresholds met, 1 = a threshold was violated, 2 = usage.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field


@dataclass
class Result:
    statuses: Counter = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0


def _one_request(
    base_url: str, path: str, cookie: str | None, timeout: float
) -> tuple[int | None, float]:
    """Single GET; returns (status or None, latency in ms)."""
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", method="GET")
    request.add_header("User-Agent", "gch-load-test/1")
    if cookie:
        request.add_header("Cookie", cookie)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return response.status, (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, (time.perf_counter() - started) * 1000
    except Exception:  # noqa: BLE001 — network failures count as errors
        return None, (time.perf_counter() - started) * 1000


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def run(args: argparse.Namespace) -> Result:
    result = Result()
    work = [(args.paths[i % len(args.paths)]) for i in range(args.requests)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(_one_request, args.base_url, path, args.cookie, args.timeout)
            for path in work
        ]
        for future in futures:
            status, latency = future.result()
            if status is None:
                result.errors += 1
            else:
                result.statuses[status] += 1
                result.latencies_ms.append(latency)
    result_wall = time.perf_counter() - started
    result.statuses["__rps__"] = (
        round(args.requests / result_wall, 2) if result_wall else 0
    )
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--path",
        dest="paths",
        action="append",
        help="repeatable; default /api/health and /api/ready",
    )
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--cookie", default=None, help="raw Cookie header, e.g. gch_session=VALUE"
    )
    parser.add_argument("--max-p95-ms", type=float, default=500.0)
    parser.add_argument("--max-5xx", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.paths:
        args.paths = ["/api/health", "/api/ready"]
    if args.requests <= 0 or args.concurrency <= 0:
        print("--requests and --concurrency must be positive", file=sys.stderr)
        return 2

    result = run(args)
    ok = sum(
        count
        for status, count in result.statuses.items()
        if isinstance(status, int) and 200 <= status < 400
    )
    five_xx = sum(
        count
        for status, count in result.statuses.items()
        if isinstance(status, int) and status >= 500
    )
    p50 = _percentile(result.latencies_ms, 0.50)
    p95 = _percentile(result.latencies_ms, 0.95)
    p99 = _percentile(result.latencies_ms, 0.99)
    rps = result.statuses.pop("__rps__", 0)

    print(f"target        : {args.base_url} paths={args.paths}")
    print(f"requests      : {args.requests} @ concurrency {args.concurrency}")
    print(f"ok / errors   : {ok} / {result.errors}")
    print(f"throughput    : {rps} req/s")
    print(
        f"latency ms    : p50={p50:.1f} p95={p95:.1f} p99={p99:.1f} "
        f"max={max(result.latencies_ms, default=0):.1f} "
        f"mean={statistics.fmean(result.latencies_ms) if result.latencies_ms else 0:.1f}"
    )
    print(f"statuses      : {dict(sorted(result.statuses.items()))}")

    failures = []
    if p95 > args.max_p95_ms:
        failures.append(f"p95 {p95:.1f}ms > {args.max_p95_ms}ms")
    if five_xx > args.max_5xx:
        failures.append(f"{five_xx} 5xx > allowed {args.max_5xx}")
    if result.errors:
        failures.append(f"{result.errors} transport errors")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print(
        f"PASS: p95 <= {args.max_p95_ms}ms, 5xx <= {args.max_5xx}, no transport errors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
