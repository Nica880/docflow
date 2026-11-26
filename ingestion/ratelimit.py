"""Thread-safe token-bucket rate limiter (SEC fair access: <= 10 requests/second)."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, rate_per_s: float, burst: int = 1) -> None:
        if rate_per_s <= 0:
            raise ValueError("rate_per_s must be > 0")
        self.rate = rate_per_s
        self.capacity = max(1, burst)
        self._tokens = float(self.capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a token is available. Returns seconds waited."""
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return waited
                sleep_for = (1 - self._tokens) / self.rate
            time.sleep(sleep_for)
            waited += sleep_for
