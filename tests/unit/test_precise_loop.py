"""The runner's event loop keeps time with perf_counter (Windows' monotonic clock is 15.6 ms)."""

import asyncio
import statistics
import time

from airc.runner import run_precise


def test_sleep_is_accurate_on_the_precise_loop() -> None:
    async def lateness() -> list[float]:
        late: list[float] = []
        for _ in range(50):
            start = time.perf_counter()
            await asyncio.sleep(0.012)
            late.append((time.perf_counter() - start - 0.012) * 1000.0)
        return late

    late = run_precise(lateness())
    assert statistics.fmean(late) < 5.0  # default loop on Windows: 8-15 ms
    assert max(late) < 15.0  # below the 15.6 ms tick of the default clock
