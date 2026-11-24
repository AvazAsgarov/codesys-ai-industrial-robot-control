"""Client-side rate limit for the THX-02 free tier (spec 7.3: stay below 60 per minute)."""

import asyncio
import time
from collections.abc import Awaitable, Callable

_EPS = 1e-9


class TokenBucket:
    """Async token bucket: ``rate_per_min`` tokens per minute, at most ``burst`` saved up.

    Waiters are served one at a time in arrival order, so concurrent parts never overshoot.
    Waiting never blocks the event loop (it awaits ``sleep``).
    """

    def __init__(
        self,
        rate_per_min: float,
        *,
        burst: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Create a full bucket.

        Args:
            rate_per_min: Sustained rate (tokens per minute), > 0.
            burst: Capacity; also the largest single ``acquire`` cost.
            clock: Monotonic clock in seconds (tests pass a fake one).
            sleep: Awaitable sleep (tests pass a fake one).

        Raises:
            ValueError: If the rate or burst is not positive.
        """
        if rate_per_min <= 0:
            msg = f"rate must be positive, got {rate_per_min}"
            raise ValueError(msg)
        if burst <= 0:
            msg = f"burst must be positive, got {burst}"
            raise ValueError(msg)
        self._rate_per_s = rate_per_min / 60.0
        self._capacity = burst
        self._tokens = burst
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._paused_until = float("-inf")
        self._lock = asyncio.Lock()

    def _refill(self, now: float) -> None:
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate_per_s)
        self._last = now

    def pause(self, seconds: float) -> None:
        """Hand out no token for ``seconds`` (e.g. a 429's ``Retry-After``)."""
        self._paused_until = max(self._paused_until, self._clock() + seconds)

    async def acquire(self, cost: float = 1.0) -> None:
        """Wait until ``cost`` tokens are available and take them.

        Cancelling the wait (e.g. by a deadline) takes no tokens.

        Raises:
            ValueError: If ``cost`` exceeds the burst capacity (it could never be served).
        """
        if cost > self._capacity:
            msg = f"cost {cost} exceeds the burst capacity {self._capacity}"
            raise ValueError(msg)
        async with self._lock:
            while True:
                now = self._clock()
                self._refill(now)
                if now < self._paused_until:
                    await self._sleep(self._paused_until - now)
                    continue
                if self._tokens + _EPS >= cost:
                    self._tokens -= cost
                    return
                await self._sleep((cost - self._tokens) / self._rate_per_s)
