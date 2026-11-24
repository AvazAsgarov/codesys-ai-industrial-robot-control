"""Async token bucket: spacing, burst, cost per request, pause after a 429."""

import asyncio

import pytest

from airc.decision.ratelimit import TokenBucket
from tests.unit.decision.conftest import FakeSleep


def _bucket(fake: FakeSleep, per_min: float = 60.0, burst: float = 1.0) -> TokenBucket:
    return TokenBucket(per_min, burst=burst, clock=fake.clock, sleep=fake)


def test_requests_are_spaced_at_the_rate(fake_sleep: FakeSleep):
    bucket = _bucket(fake_sleep, per_min=60.0, burst=1.0)
    times: list[float] = []

    async def scenario():
        for _ in range(4):
            await bucket.acquire()
            times.append(fake_sleep.now)

    asyncio.run(scenario())
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0])


def test_burst_is_served_at_once_then_spaced(fake_sleep: FakeSleep):
    bucket = _bucket(fake_sleep, per_min=30.0, burst=3.0)
    times: list[float] = []

    async def scenario():
        for _ in range(4):
            await bucket.acquire()
            times.append(fake_sleep.now)

    asyncio.run(scenario())
    assert times == pytest.approx([0.0, 0.0, 0.0, 2.0])


def test_cost_counts_decisions_per_request(fake_sleep: FakeSleep):
    bucket = _bucket(fake_sleep, per_min=50.0, burst=2.0)
    times: list[float] = []

    async def scenario():
        for _ in range(3):
            await bucket.acquire(2)
            times.append(fake_sleep.now)

    asyncio.run(scenario())
    assert times == pytest.approx([0.0, 2.4, 4.8])  # 2 decisions at 50/min = 2.4 s


def test_rate_never_exceeds_the_limit_over_a_minute(fake_sleep: FakeSleep):
    bucket = _bucket(fake_sleep, per_min=50.0, burst=2.0)
    times: list[float] = []

    async def scenario():
        for _ in range(40):
            await bucket.acquire()
            times.append(fake_sleep.now)

    asyncio.run(scenario())
    for i, t in enumerate(times):
        in_window = [u for u in times[: i + 1] if u > t - 60.0]
        assert len(in_window) <= 50 + 2


def test_pause_blocks_until_retry_after(fake_sleep: FakeSleep):
    bucket = _bucket(fake_sleep, per_min=600.0, burst=5.0)

    async def scenario():
        await bucket.acquire()
        bucket.pause(7.0)
        await bucket.acquire()

    asyncio.run(scenario())
    assert fake_sleep.now == pytest.approx(7.0)


def test_concurrent_waiters_are_served_one_by_one(fake_sleep: FakeSleep):
    bucket = _bucket(fake_sleep, per_min=60.0, burst=1.0)
    done: list[float] = []

    async def one():
        await bucket.acquire()
        done.append(fake_sleep.now)

    async def scenario():
        await asyncio.gather(*(one() for _ in range(3)))

    asyncio.run(scenario())
    assert sorted(done) == pytest.approx([0.0, 1.0, 2.0])


def test_cost_above_capacity_is_rejected(fake_sleep: FakeSleep):
    bucket = _bucket(fake_sleep, burst=1.0)
    with pytest.raises(ValueError, match="burst"):
        asyncio.run(bucket.acquire(2))


def test_invalid_rate_is_rejected():
    with pytest.raises(ValueError, match="rate"):
        TokenBucket(0.0)
