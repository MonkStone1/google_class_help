"""In-memory request throttling for the hosted service (stage 9, §39).

A token-bucket limiter keyed by an arbitrary string (client IP, user id,
endpoint name). It is hosted-only infrastructure by design:

- the desktop build never enables it (single local user, no abuse
  surface — callers must pass ``enabled=request.app.state.hosted``);
- the module holds NO request state at import time: every bucket lives in
  the registry passed by the caller (``main.py`` owns one process-wide
  registry), so unit tests stay isolated and two app instances in one
  process cannot share quota;
- the clock is injectable (``now`` parameter) so tests do not sleep.

Limits are conservative first-production values from the capacity note
(ADR-0027): login/callback attempts are the credential-adjacent surface,
manual sync is the Google-API fan-out surface, destructive cache clears
are the foot-gun surface.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """Leaky-free token bucket: ``capacity`` tokens, refilled linearly."""

    capacity: int
    refill_per_second: float
    tokens: float = field(init=False)
    updated_at: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)
        self.updated_at = time.monotonic()


class RateLimiter:
    """Thread-safe registry of named token buckets with injectable clock."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._buckets: dict[str, TokenBucket] = {}

    def allow(
        self,
        key: str,
        *,
        capacity: int,
        refill_per_second: float,
        now: float | None = None,
    ) -> bool:
        """Consume one token for ``key``; False means the request is over limit."""
        moment = time.monotonic() if now is None else now
        with self._guard:
            bucket = self._buckets.get(key)
            if bucket is None or (
                bucket.capacity != capacity
                or bucket.refill_per_second != refill_per_second
            ):
                bucket = TokenBucket(
                    capacity=capacity, refill_per_second=refill_per_second
                )
                bucket.updated_at = moment
                self._buckets[key] = bucket
            elapsed = max(0.0, moment - bucket.updated_at)
            bucket.tokens = min(
                float(bucket.capacity),
                bucket.tokens + elapsed * bucket.refill_per_second,
            )
            bucket.updated_at = moment
            if bucket.tokens < 1.0:
                return False
            bucket.tokens -= 1.0
            return True

    def reset(self, key: str | None = None) -> None:
        """Drop one bucket (or the whole registry) — used by tests only."""
        with self._guard:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)
