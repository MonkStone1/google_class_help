#!/usr/bin/env python3
"""HTTP load test for the hosted deployment (migration stage 10, §88).

Measures what the acceptance criteria ask for — request rate, latency
distribution, HTTP status breakdown — against a RUNNING server, so the same
tool works for a local sanity run, for the resource-capped local Docker stand
(``compose.loadtest.yml``) and for the production VPS behind Cloudflare. It
intentionally uses only the Python standard library: no extra dependency ships
with the image.

It does NOT replace ``docker stats`` for RAM/CPU: run both side by side (see
docs/DEPLOYMENT_CHECKLIST.md §8 and tools/loadtest_watch.py).

Usage (from the project root):

    # local sanity run against a dev server (the original smoke run)
    python tools/load_test.py --base-url http://127.0.0.1:8000 \\
        --path /api/health --path /api/ready --requests 300 --concurrency 10

    # authenticated pass on the VPS (session cookie from a real browser login)
    python tools/load_test.py --base-url https://classroomhelp.pp.ua \\
        --path /api/status --path /api/courses \\
        --cookie gch_session=<value> --requests 500 --concurrency 20

    # many synthetic users against the local Docker stand (cookie file written
    # by tools/loadtest_seed.py, one `name=value` per line):
    python tools/load_test.py --base-url http://127.0.0.1:8000 \\
        --cookie-file loadtest/session-cookies.txt --per-path \\
        --path /api/status --path /api/courses --path /api/grades \\
        --requests 2000 --concurrency 20 --json-out loadtest/run.json

    # open-loop (fixed arrival rate) instead of closed-loop, with a warmup:
    python tools/load_test.py --rate 20 --duration 60 --warmup 100 \\
        --cookie-file loadtest/session-cookies.txt --path /api/status

    # rate-limit surface (POST/DELETE carry the CSRF fetch metadata §38 needs):
    python tools/load_test.py --method POST --path /api/sync \\
        --cookie-file loadtest/session-cookies.txt --requests 100 --concurrency 5

Exit code 0 = all thresholds met, 1 = a threshold was violated, 2 = usage.

Reading the output: statuses are NOT collapsed into "ok". 401/403/409/429 are
the API's own documented answers (session gate §50, teacher gate §23, queued
sync §19, rate limits §39); they are reported separately so a run cannot look
green while actually measuring rejections. Transport failures, 5xx and a p95
above the threshold are what make a run fail.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The API's own documented answers for a request the server refuses on
# purpose. They are NOT failures of the server, but they must never be
# collapsed into "ok" either: a run that mostly got 429 measured the rate
# limiter, not the service, and must not look green (§39/§59).
EXPECTED_CLIENT_STATUSES = (401, 403, 409, 429)
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
# Local stand default. The CSRF check (main.py, §38/ADR-0026) accepts an
# unsafe request when it carries the exact Origin OR a same-origin
# Sec-Fetch-Site header, so the tool presents itself as the origin it calls —
# without it every POST/DELETE would be a 403 and the run would measure the
# guard instead of the endpoint.
DEFAULT_COOKIE_NAME = "gch_session"
# A transport reason is a free-form exception string (it can embed a whole
# nested chain), so it is trimmed before it goes into the report. Long enough
# to keep the useful part — the errno or the TLS verify message — short enough
# that one failing path cannot bury the rest of the run.
MAX_ERROR_REASON_CHARS = 120


@dataclass
class PathResult:
    """Status/latency sample of a single path (S2-S4 need per-path numbers)."""

    statuses: Counter = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    # Why the transport failed, counted by reason: "N transport errors" alone
    # cannot be acted on (a TLS trust problem and a dead server read the same).
    error_reasons: Counter = field(default_factory=Counter)


@dataclass
class Result:
    statuses: Counter = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    # Transport failure reasons across the whole run; printed so a red run
    # states its cause (expired certificate, refused connection, DNS) instead
    # of only counting failures.
    error_reasons: Counter = field(default_factory=Counter)
    # Retry-After values of throttled responses, in seconds: the limit is only
    # useful if the header is actually present (§39/§59).
    retry_after: list[float] = field(default_factory=list)
    per_path: dict[str, PathResult] = field(default_factory=dict)
    rps: float = 0.0
    # Open-loop only: how many arrivals had to wait for a free slot because
    # the concurrency budget was exhausted (0 in a healthy run).
    scheduler_lag: int = 0
    # Per-repetition latency summary when --repeat > 1, so a reader can see
    # the spread instead of one number that hides it.
    run_summaries: list[dict[str, float]] = field(default_factory=list)


@dataclass(frozen=True)
class RequestSpec:
    """One fully built request; shared read-only between worker threads."""

    url: str
    method: str
    cookie: str | None
    headers: tuple[tuple[str, str], ...]
    body: bytes | None
    timeout: float
    path: str
    # Origin the tool claims to be: the base URL without its path, e.g.
    # http://127.0.0.1:8000. main.py compares it to the configured origins on
    # unsafe methods (§38), so a wrong value would mean 403 instead of the
    # status actually under test.
    origin: str


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def _summarize(values: list[float]) -> dict[str, float]:
    """p50/p95/p99/mean/max of one latency sample (empty sample = zeros)."""
    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "max": 0.0}
    return {
        "p50": round(_percentile(values, 0.50), 1),
        "p95": round(_percentile(values, 0.95), 1),
        "p99": round(_percentile(values, 0.99), 1),
        "mean": round(statistics.fmean(values), 1),
        "max": round(max(values), 1),
    }


def _read_cookie_file(path: Path, cookie_name: str) -> list[str]:
    """Cookie header values from ``loadtest_seed.py`` output, one per line.

    Accepts both ``name=value`` (what the seeder writes) and a bare token, and
    skips blanks and ``#`` comments so a hand-edited file still works. With
    many synthetic users the tool round-robins over the list, so a read-heavy
    run spreads across users instead of hammering one row in the cache.
    """
    cookies: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cookies.append(line if "=" in line else f"{cookie_name}={line}")
    return cookies


def _build_specs(args: argparse.Namespace) -> list[RequestSpec]:
    """Round-robin the (path, cookie) pairs into one spec per request.

    Two requests for the same path with different cookies stay separate
    entries on purpose: per-path statistics must not be split by user, only
    the cookie differs.
    """
    cookies: list[str | None] = [args.cookie]
    if args.cookie_file:
        loaded = _read_cookie_file(Path(args.cookie_file), args.cookie_name)
        if not loaded:
            print(
                f"--cookie-file {args.cookie_file} contains no cookies",
                file=sys.stderr,
            )
            raise SystemExit(2)
        cookies = list(loaded)
    base = args.base_url.rstrip("/")
    method = args.method.upper()
    extra = tuple(args.header or ())
    body = args.body.encode("utf-8") if args.body else None
    return [
        RequestSpec(
            url=f"{base}{args.paths[index % len(args.paths)]}",
            method=method,
            cookie=cookies[index % len(cookies)],
            headers=extra,
            body=body,
            timeout=args.timeout,
            path=args.paths[index % len(args.paths)],
            origin=_origin_of(base),
        )
        for index in range(args.requests)
    ]


def _origin_of(base_url: str) -> str:
    """scheme://host[:port] of the base URL, without a trailing slash."""
    parts = urllib.parse.urlsplit(base_url)
    return f"{parts.scheme}://{parts.netloc}"


def _retry_after(value: str | None) -> float | None:
    """Parse a numeric ``Retry-After`` (the §39 answers use plain seconds)."""
    if not value:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _error_reason(exc: BaseException) -> str:
    """Short, stable label for a transport failure.

    A run that never gets past the TLS handshake and a run against a dead
    server look identical in the report without this: both are "N transport
    errors", so the cause (an expired cross-signed root in the operator's
    trust store, a proxy, a refused connection) was invisible and the run
    was indistinguishable from a saturated VPS. The reason is unwrapped
    (``URLError.reason``) so the interesting exception is the one printed,
    then trimmed so one failure cannot flood the report.
    """
    inner = getattr(exc, "reason", exc)
    text = str(inner).strip() or type(inner).__name__
    if len(text) > MAX_ERROR_REASON_CHARS:
        text = text[: MAX_ERROR_REASON_CHARS - 3] + "..."
    return f"{type(inner).__name__}: {text}"


def _one_request(
    spec: RequestSpec,
) -> tuple[int | None, float, float | None, str | None]:
    """Issue one request; returns (status or None, latency ms, Retry-After, reason).

    ``reason`` is set only for transport failures and feeds the error-reason
    breakdown, so a failed run states what failed instead of only how often.
    """
    request = urllib.request.Request(spec.url, data=spec.body, method=spec.method)
    request.add_header("User-Agent", "gch-load-test/2")
    if spec.cookie:
        request.add_header("Cookie", spec.cookie)
    if spec.method not in SAFE_METHODS:
        # §38: an unsafe method needs the exact Origin OR same-origin fetch
        # metadata. main.py also lets a request with BOTH headers absent
        # through (non-browser client), but presenting as the origin we call
        # is the honest measurement — a plain 302/200 is what a browser does.
        request.add_header("Sec-Fetch-Site", "same-origin")
        request.add_header("Origin", spec.origin)
    for name, value in spec.headers:
        request.add_header(name, value)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=spec.timeout) as response:
            response.read()
            return (
                response.status,
                (time.perf_counter() - started) * 1000,
                _retry_after(response.headers.get("Retry-After")),
                None,
            )
    except urllib.error.HTTPError as exc:
        exc.read()
        return (
            exc.code,
            (time.perf_counter() - started) * 1000,
            _retry_after(exc.headers.get("Retry-After")),
            None,
        )
    except Exception as exc:  # noqa: BLE001 — network failures count as errors
        # Counted AND explained: a bare "N transport errors" cannot be acted
        # on, and this branch is where an expired certificate, an unreachable
        # host or a refused connection all land.
        return (
            None,
            (time.perf_counter() - started) * 1000,
            None,
            _error_reason(exc),
        )


def _record(result: Result, spec: RequestSpec, outcome: tuple) -> None:
    """Fold one request's outcome into the totals and the per-path bucket."""
    status, latency, retry_after, reason = outcome
    bucket = result.per_path.setdefault(spec.path, PathResult())
    if status is None:
        result.errors += 1
        bucket.errors += 1
        result.error_reasons[reason or "unknown error"] += 1
        bucket.error_reasons[reason or "unknown error"] += 1
        return
    result.statuses[status] += 1
    result.latencies_ms.append(latency)
    bucket.statuses[status] += 1
    bucket.latencies_ms.append(latency)
    if retry_after is not None:
        result.retry_after.append(retry_after)


def _run_closed_loop(specs: list[RequestSpec], concurrency: int) -> Result:
    """Original mode: N requests, at most ``concurrency`` in flight.

    A closed loop hides saturation — a slow server simply means fewer requests
    per second instead of a growing queue — so it answers "how fast is one
    request, and are there 5xx/transport failures", nothing about capacity.
    """
    result = Result()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_one_request, spec) for spec in specs]
        for future, spec in zip(futures, specs, strict=True):
            _record(result, spec, future.result())
    wall = time.perf_counter() - started
    result.rps = round(len(specs) / wall, 2) if wall else 0.0
    return result


def _run_open_loop(
    specs: list[RequestSpec], concurrency: int, rate: float, duration: float
) -> Result:
    """Fixed arrival rate: one request every 1/rate seconds for ``duration``.

    This is the mode that exposes queueing: once responses are slower than the
    arrival interval the pool saturates and ``scheduler_lag`` grows, which a
    closed loop can never show. ``duration <= 0`` issues exactly as many
    arrivals as there are specs, at the requested rate.
    """
    result = Result()
    interval = 1.0 / rate
    total = max(1, round(rate * duration)) if duration > 0 else len(specs)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        pending: list[tuple[RequestSpec, Any]] = []
        for index in range(total):
            delay = started + index * interval - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                # The arrival was due in the past: the pool or the server is
                # the bottleneck. Counted, never hidden.
                result.scheduler_lag += 1
            spec = specs[index % len(specs)]
            pending.append((spec, pool.submit(_one_request, spec)))
        for spec, future in pending:
            _record(result, spec, future.result())
    wall = time.perf_counter() - started
    issued = sum(result.statuses.values()) + result.errors
    result.rps = round(issued / wall, 2) if wall else 0.0
    return result


def _run_once(args: argparse.Namespace) -> Result:
    """One complete measurement (warmup included), as before."""
    specs = _build_specs(args)
    if args.warmup > 0:
        # Cold caches, the first DB connect and first-touch page reads would
        # otherwise land in the sample and inflate p95.
        _run_closed_loop(specs[: args.warmup], args.concurrency)
    if args.rate > 0:
        return _run_open_loop(specs, args.concurrency, args.rate, args.duration)
    return _run_closed_loop(specs, args.concurrency)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def run(args: argparse.Namespace) -> Result:
    """Measure, repeating the whole run when ``--repeat`` is given.

    Repetition is not a tolerance band: the threshold stays exactly as strict,
    it is applied to the MEDIAN of N independent runs instead of to one noisy
    sample. Statuses and errors are summed (a single 5xx in any repetition
    still fails), while latency percentiles are per-run and then median, since
    a percentile cannot be averaged across runs.
    """
    if args.repeat <= 1:
        return _run_once(args)

    runs = [_run_once(args) for _ in range(args.repeat)]
    merged = Result()
    for one in runs:
        merged.statuses.update(one.statuses)
        merged.errors += one.errors
        merged.error_reasons.update(one.error_reasons)
        merged.retry_after.extend(one.retry_after)
        merged.scheduler_lag += one.scheduler_lag
    # The headline numbers describe the MEDIAN run — a real measurement, not a
    # synthetic mixture of runs (percentiles cannot be pooled).
    representative = runs[len(runs) // 2]
    merged.latencies_ms = representative.latencies_ms
    merged.per_path = representative.per_path
    merged.rps = round(_median([one.rps for one in runs]), 2)
    merged.run_summaries = [
        {
            "p50": _summarize(one.latencies_ms)["p50"],
            "p95": _summarize(one.latencies_ms)["p95"],
            "p99": _summarize(one.latencies_ms)["p99"],
            "rps": one.rps,
            "errors": one.errors,
        }
        for one in runs
    ]
    return merged


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HTTP load test for the hosted deployment (§88)."
    )
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
    # --- extensions for the local Docker stand (docs/LOAD_TEST_LOCAL.md) ---
    parser.add_argument(
        "--cookie-file",
        default=None,
        help="file with one `name=value` cookie per line (loadtest_seed.py "
        "output); requests round-robin over the sessions",
    )
    parser.add_argument(
        "--cookie-name",
        default=DEFAULT_COOKIE_NAME,
        help=f"cookie name for bare tokens in --cookie-file (default: "
        f"{DEFAULT_COOKIE_NAME})",
    )
    parser.add_argument(
        "--method", default="GET", help="HTTP method (GET/POST/DELETE), default GET"
    )
    parser.add_argument(
        "--header", action="append", help="extra header 'Name: value', repeatable"
    )
    parser.add_argument("--body", default=None, help="request body for unsafe methods")
    parser.add_argument(
        "--rate",
        type=float,
        default=0.0,
        help="open-loop arrival rate in req/s; 0 = closed loop (default)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="seconds to sustain --rate; 0 = exactly --requests arrivals",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=0,
        help="requests to issue and discard before measuring",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="run the whole measurement N times and judge the MEDIAN p95; a "
        "single run's p95 moves by tens of milliseconds between repetitions, "
        "so a strict verdict on one sample is a coin flip near the threshold",
    )
    parser.add_argument(
        "--per-path", action="store_true", help="print per-path latency/statuses"
    )
    parser.add_argument(
        "--json-out", default=None, help="write the machine-readable report here"
    )
    parser.add_argument(
        "--expect-status",
        type=int,
        default=0,
        help="treat exactly this status as the expected answer (e.g. 429 in the "
        "rate-limit scenario S6); 0 = 2xx/3xx count as ok",
    )
    return parser


def _print_report(args: argparse.Namespace, result: Result, ok: int) -> None:
    """Human-readable report; the JSON payload is assembled in ``main``."""
    overall = _summarize(result.latencies_ms)
    refused = {
        status: count
        for status, count in sorted(result.statuses.items())
        if status in EXPECTED_CLIENT_STATUSES
    }

    print(f"target        : {args.base_url} paths={args.paths}")
    mode = (
        f"open-loop {args.rate} req/s for {args.duration}s"
        if args.rate > 0
        else f"closed-loop {args.requests} @ concurrency {args.concurrency}"
    )
    print(f"mode          : {mode} method={args.method.upper()}")
    if args.warmup:
        print(f"warmup        : {args.warmup} discarded requests")
    print(f"ok / errors   : {ok} / {result.errors}")
    print(f"throughput    : {result.rps} req/s")
    if result.scheduler_lag:
        print(f"scheduler lag : {result.scheduler_lag} late arrivals (pool saturated)")
    print(
        f"latency ms    : p50={overall['p50']:.1f} p95={overall['p95']:.1f} "
        f"p99={overall['p99']:.1f} max={overall['max']:.1f} "
        f"mean={overall['mean']:.1f}"
    )
    print(f"statuses      : {dict(sorted(result.statuses.items()))}")
    if refused:
        print(f"refused       : {refused} (documented API answers, not errors)")
    if result.error_reasons:
        # The whole point: a run of pure transport errors names the cause, so
        # the reader can tell a local TLS/proxy problem from a dead server
        # instead of re-running curl to find out which one it was.
        for reason, count in result.error_reasons.most_common():
            print(f"error reason  : n={count:<5} {reason}")
    if result.retry_after:
        print(
            f"retry-after   : n={len(result.retry_after)} "
            f"max={max(result.retry_after):.0f}s (throttling active, §39)"
        )
    if result.run_summaries:
        runs = result.run_summaries
        p95s = [one["p95"] for one in runs]
        print(f"runs          : {len(runs)} repetitions, judged on the median")
        print(
            f"  p95 spread  : min={min(p95s):.1f} median={_median(p95s):.1f} "
            f"max={max(p95s):.1f} ms"
        )
        print("  per run     : " + ", ".join(f"p95={one['p95']:.0f}" for one in runs))
    if args.per_path:
        print("per path      :")
        for path, bucket in sorted(result.per_path.items()):
            summary = _summarize(bucket.latencies_ms)
            statuses = dict(sorted(bucket.statuses.items()))
            print(
                f"  {path:<44} n={sum(statuses.values()) + bucket.errors:<5} "
                f"p50={summary['p50']:>7.1f} p95={summary['p95']:>7.1f} "
                f"p99={summary['p99']:>7.1f} {statuses}"
            )


def _verdict(
    args: argparse.Namespace, result: Result, ok: int, five_xx: int
) -> list[str]:
    """Threshold check of §88. Empty list = the run passed."""
    overall = _summarize(result.latencies_ms)
    failures: list[str] = []
    if overall["p95"] > args.max_p95_ms:
        failures.append(f"p95 {overall['p95']:.1f}ms > {args.max_p95_ms}ms")
    if five_xx > args.max_5xx:
        failures.append(f"{five_xx} 5xx > allowed {args.max_5xx}")
    if result.errors:
        failures.append(f"{result.errors} transport errors")
    if result.errors and result.error_reasons:
        # Naming the cause in the verdict line too: this is the one line the
        # operator reads when scrolling CI-style output, and "1000 transport
        # errors" alone is not an action.
        top_reason, top_count = result.error_reasons.most_common(1)[0]
        failures.append(f"top cause: {top_count}x {top_reason}")
    if args.expect_status:
        # Scenario S6: a throttled surface is EXPECTED to answer 429, so the
        # run passes only if the limiter actually fired and nothing 5xx'd.
        if not result.statuses.get(args.expect_status):
            failures.append(f"expected {args.expect_status} responses, got none")
    elif ok == 0:
        failures.append("no 2xx/3xx responses at all")
    return failures


def _payload(
    args: argparse.Namespace, result: Result, ok: int, five_xx: int
) -> dict[str, Any]:
    """The machine-readable report consumed by tools/loadtest_report.py."""
    sessions = 0
    if args.cookie_file:
        sessions = len(_read_cookie_file(Path(args.cookie_file), args.cookie_name))
    elif args.cookie:
        sessions = 1
    return {
        "base_url": args.base_url,
        "paths": list(args.paths),
        "method": args.method.upper(),
        "mode": "open-loop" if args.rate > 0 else "closed-loop",
        "rate": args.rate,
        "duration": args.duration,
        "concurrency": args.concurrency,
        "requests": args.requests,
        "warmup": args.warmup,
        "repeat": args.repeat,
        "runs": result.run_summaries,
        "cookie_file": args.cookie_file,
        "sessions_used": sessions,
        "ok": ok,
        "errors": result.errors,
        "error_reasons": dict(result.error_reasons.most_common()),
        "five_xx": five_xx,
        "rps": result.rps,
        "scheduler_lag": result.scheduler_lag,
        "latency_ms": _summarize(result.latencies_ms),
        "statuses": {
            str(status): count for status, count in sorted(result.statuses.items())
        },
        "refused": {
            str(status): count
            for status, count in sorted(result.statuses.items())
            if status in EXPECTED_CLIENT_STATUSES
        },
        "retry_after_max": max(result.retry_after) if result.retry_after else None,
        "thresholds": {
            "max_p95_ms": args.max_p95_ms,
            "max_5xx": args.max_5xx,
            "expect_status": args.expect_status,
        },
        "per_path": {
            path: {
                "requests": sum(bucket.statuses.values()) + bucket.errors,
                "errors": bucket.errors,
                "error_reasons": dict(bucket.error_reasons.most_common()),
                "latency_ms": _summarize(bucket.latencies_ms),
                "statuses": {
                    str(status): count
                    for status, count in sorted(bucket.statuses.items())
                },
            }
            for path, bucket in sorted(result.per_path.items())
        },
    }


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.paths:
        args.paths = ["/api/health", "/api/ready"]
    if args.requests <= 0 or args.concurrency <= 0:
        print("--requests and --concurrency must be positive", file=sys.stderr)
        return 2
    if args.rate < 0 or (args.rate > 0 and args.duration <= 0):
        print("--rate requires a positive --duration", file=sys.stderr)
        return 2
    if args.repeat <= 0:
        print("--repeat must be positive", file=sys.stderr)
        return 2

    result = run(args)
    ok = sum(count for status, count in result.statuses.items() if 200 <= status < 400)
    five_xx = sum(count for status, count in result.statuses.items() if status >= 500)
    failures = _verdict(args, result, ok, five_xx)
    _print_report(args, result, ok)

    if failures:
        print("FAIL: " + "; ".join(failures))
    else:
        print(
            f"PASS: p95 <= {args.max_p95_ms}ms, 5xx <= {args.max_5xx}, "
            "no transport errors"
        )

    if args.json_out:
        payload = _payload(args, result, ok, five_xx)
        payload["failures"] = failures
        payload["passed"] = not failures
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        # loadtest/ is git-ignored: a report may name the cookie file it used.
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"json          : {out}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
