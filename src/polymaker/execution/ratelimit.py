"""Async token-bucket rate budgeter.

The CLOB API throttles (queues) excess requests rather than 429-ing, so the real
risk is silent latency injection when the market is moving. We self-limit to a
fraction of the documented ceilings and expose pressure as a signal so the
engine can shed low-edge reprices first.
"""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    def __init__(self, rate_per_s: float, burst: float | None = None) -> None:
        self.rate = max(rate_per_s, 0.001)
        self.capacity = burst if burst is not None else max(1.0, rate_per_s)
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
        self._last = now

    async def acquire(self, n: float = 1.0) -> None:
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= n:
                    self._tokens -= n
                    return
                deficit = n - self._tokens
                await asyncio.sleep(deficit / self.rate)

    @property
    def pressure(self) -> float:
        """0 = plenty of budget, 1 = empty (callers about to wait)."""
        self._refill()
        return 1.0 - min(1.0, self._tokens / self.capacity)
