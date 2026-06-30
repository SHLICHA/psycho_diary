"""Token bucket rate limiter for MAX transport API calls."""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    """Simple async token bucket limiter with configurable RPS and burst."""

    def __init__(self, rate_per_second: float, burst: int):
        self.rate_per_second = max(float(rate_per_second), 0.001)
        self.capacity = max(int(burst), 1)
        self.tokens = float(self.capacity)
        self._lock = asyncio.Lock()
        self._last_refill = time.monotonic()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = max(now - self._last_refill, 0.0)
                refill = elapsed * self.rate_per_second
                if refill > 0:
                    self.tokens = min(self.capacity, self.tokens + refill)
                    self._last_refill = now

                if self.tokens >= 1:
                    self.tokens -= 1
                    return

                wait_seconds = (1 - self.tokens) / self.rate_per_second

            await asyncio.sleep(max(wait_seconds, 0.001))
