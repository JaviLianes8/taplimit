"""Long runs, odd costs and clock ranges: compaction, give-back of converted costs, boundaries."""

from __future__ import annotations

import asyncio
import random

import pytest
from _fakeclock import FakeClock

from taplimit import RateLimiter, RateLimitExceeded
from taplimit._base import _shown


class _Stop(Exception):
    pass


def _stop(seconds: float) -> None:
    raise _Stop


class _Index:
    def __init__(self, value: int) -> None:
        self.value = value

    def __index__(self) -> int:
        return self.value


@pytest.mark.parametrize("cost", [5.0, _Index(5)])
def test_an_interrupted_wait_returns_the_converted_cost(cost: object) -> None:
    limiter = RateLimiter(10, 60, clock=lambda: 0.0, sleep=_stop)
    assert limiter.try_acquire(10)
    with pytest.raises(_Stop):
        limiter.acquire(cost=cost)  # type: ignore[arg-type]
    assert limiter.available() == 0 and type(limiter.available()) is int
    assert limiter.retry_after(10) == 60.0  # the reservation is gone, the grants remain
    assert limiter._win.total == 10


@pytest.mark.parametrize("cost", [5.0, _Index(5)])
def test_a_cancelled_async_wait_returns_the_converted_cost(cost: object) -> None:
    async def parked(seconds: float) -> None:
        await asyncio.Event().wait()

    limiter = RateLimiter(10, 60, clock=lambda: 0.0, async_sleep=parked)

    async def main() -> None:
        assert limiter.try_acquire(10)
        waiter = asyncio.ensure_future(limiter.acquire_async(cost=cost))  # type: ignore[arg-type]
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

    asyncio.run(main())
    assert limiter.available() == 0 and type(limiter.available()) is int
    assert limiter.retry_after(10) == 60.0
    assert limiter._win.total == 10


@pytest.mark.parametrize("seed", range(6))
def test_compaction_keeps_every_live_slot(seed: int) -> None:
    rng = random.Random(seed)
    calls, period = rng.randint(3, 40), 8.0
    clock = FakeClock()
    limiter = RateLimiter(calls, period, clock=clock.time, sleep=clock.sleep)
    grants: list[float] = []
    longest = 0
    for _ in range(3000):
        clock.advance(rng.choice([0.0, 0.125, 0.25, 1.0]))
        cost = rng.randint(1, calls)
        live = [g for g in grants if clock.now - period < g <= clock.now]
        fits = len(live) + cost <= calls
        assert limiter.try_acquire(cost) is fits
        grants += [clock.now] * cost if fits else []
        live = [g for g in grants if clock.now - period < g <= clock.now]
        assert limiter.available() == calls - len(live)
        longest = max(longest, len(limiter._win.stamps))
    assert longest <= 2 * (64 + 8 / 0.125 + 1)  # spent runs are dropped, memory stays bounded


def test_a_clock_below_zero_works_like_any_other() -> None:
    now = [-1000.0]
    limiter = RateLimiter(1, 10, clock=lambda: now[0])
    assert limiter.available() == 1 and limiter.retry_after() == 0.0
    assert limiter.try_acquire()
    now[0] = -990.0
    assert limiter.try_acquire()


def test_after_a_reset_a_newcomer_still_queues_behind_a_waiter() -> None:
    now = [0.0]
    limiter = RateLimiter(2, 10, clock=lambda: now[0], sleep=_stop)
    assert limiter.try_acquire(2)
    window, ready, _, _ = limiter._reserve(None, 1, True, None)  # a waiter holds t = 10
    assert ready == 10.0
    now[0] = 5.0
    limiter.reset()
    assert not limiter.try_acquire()
    assert limiter.retry_after() == 5.0
    with pytest.raises(RateLimitExceeded):
        limiter.acquire(blocking=False)
    assert window.entries() == 1


def test_async_waits_longer_than_a_day_await_in_steps() -> None:
    clock = FakeClock()
    awaited: list[float] = []

    async def async_sleep(seconds: float) -> None:
        awaited.append(seconds)
        clock.advance(seconds)

    limiter = RateLimiter(1, 2.5 * 86400, clock=clock.time, async_sleep=async_sleep)

    async def main() -> None:
        await limiter.acquire_async()
        await limiter.acquire_async()

    asyncio.run(main())
    assert awaited == [86400.0, 86400.0, 43200.0]


def test_message_number_thresholds() -> None:
    assert _shown(10**15 - 1) == "999999999999999"
    assert _shown(10**15) == "a 50-bit number"
    assert str(RateLimitExceeded(999_999_999.9994)).endswith("after 999999999.999s")
    assert str(RateLimitExceeded(1e9)).endswith("after 1e+09s")
