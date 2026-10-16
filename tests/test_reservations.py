"""Reservations that share an instant, cancelled waiters, and where coroutines take slots."""

from __future__ import annotations

import asyncio
import inspect

import pytest
from _fakeclock import FakeClock

from taplimit import RateLimiter


async def _parked(seconds: float) -> None:
    await asyncio.Event().wait()  # never set: only cancellation ends this wait


def test_acquisitions_at_one_instant_share_one_entry() -> None:
    limiter = RateLimiter(1000, 1, clock=lambda: 0.0)
    assert all(limiter.try_acquire() for _ in range(1000))
    assert len(limiter._win.runs) == 1 and limiter._win.total == 1000


def test_cancelling_one_of_two_waiters_at_the_same_instant_keeps_the_other() -> None:
    limiter = RateLimiter(3, 10, clock=lambda: 0.0, async_sleep=_parked)

    async def main() -> None:
        assert limiter.try_acquire(3)
        first = asyncio.ensure_future(limiter.acquire_async(cost=2))
        second = asyncio.ensure_future(limiter.acquire_async(cost=1))
        await asyncio.sleep(0)
        assert len(limiter._win.runs) == 2  # both reserved at 10.0, in one entry
        assert limiter.available() == 0
        assert limiter.retry_after(3) == 20.0
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert limiter.available() == 0  # the second waiter still holds its slot
        assert limiter.retry_after(2) == 10.0
        assert limiter.retry_after(3) == 20.0
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        assert limiter.retry_after(3) == 10.0
        assert len(limiter._win.runs) == 1

    asyncio.run(main())


def test_an_async_callable_object_takes_its_slot_when_awaited() -> None:
    limiter = RateLimiter(1, 60, clock=lambda: 0.0)

    class Fetcher:
        async def __call__(self, x: int) -> int:
            return x

    guarded = limiter(Fetcher())
    assert inspect.iscoroutinefunction(guarded)

    async def main() -> None:
        pending = guarded(3)
        assert limiter.available() == 1  # creating the coroutine takes nothing
        assert await pending == 3
        assert limiter.available() == 0

    asyncio.run(main())


def test_async_with_waits_with_the_async_sleep() -> None:
    clock = FakeClock()
    awaited: list[float] = []

    async def async_sleep(seconds: float) -> None:
        awaited.append(seconds)
        clock.advance(seconds)

    limiter = RateLimiter(1, 5, clock=clock.time, sleep=clock.sleep, async_sleep=async_sleep)

    async def main() -> None:
        async with limiter:
            pass
        async with limiter:
            pass

    asyncio.run(main())
    assert awaited == [5.0] and clock.slept == []
