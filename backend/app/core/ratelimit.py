"""In-process sliding-window rate limiting.

Single-process only: with multiple workers each process keeps its own counters. That is
acceptable for the Phase 2 deployment (one API process) and is recorded as a limitation;
a shared store (for example Redis) is only justified once the deployment model is agreed
(DR-010).
"""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Record an attempt. Returns ``(allowed, retry_after_seconds)``."""

        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(bucket[0] + window_seconds - now) + 1)
                return False, retry_after
            bucket.append(now)
            if len(self._events) > 10_000:
                self._prune(cutoff)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def _prune(self, cutoff: float) -> None:
        for key in [
            key for key, bucket in self._events.items() if not bucket or bucket[-1] <= cutoff
        ]:
            self._events.pop(key, None)


# Process-wide limiters keyed by concern, so a login attempt cannot consume a scan quota.
login_limiter = SlidingWindowLimiter()
device_token_limiter = SlidingWindowLimiter()
scan_limiter = SlidingWindowLimiter()
