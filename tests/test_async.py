"""asyncio support: awaiting slots, async context managers and async decorators."""

from __future__ import annotations

import asyncio
import inspect

import pytest
from _fakeclock import FakeClock

from taplimit import RateLimiter, RateLimitExceeded, rate_limit


class AsyncFakeClock(FakeClock):
    async def async_sleep(self, seconds: float) -> None:
        self.sleep(seconds)


def _limiter(calls: int = 1, period: float = 10) -> tuple[RateLimiter, AsyncFakeClock]:
    clock = AsyncFakeClock()
    limiter = RateLimiter(
        calls, period, clock=clock.time, sleep=clock.sleep, async_sleep=clock.async_sleep
    )
    return limiter, clock


def test_acquire_async_waits_for_the_slot() -> None:
    limiter, clock = _limiter()

    async def main() -> None:
        await limiter.acquire_async()
        await limiter.acquire_async()

    asyncio.run(main())
    assert clock.slept == [10.0]


def test_acquire_async_honours_non_blocking_and_timeout() -> None:
    limiter, _ = _limiter()

    async def main() -> None:
        await limiter.acquire_async()
        with pytest.raises(RateLimitExceeded):
            await limiter.acquire_async(blocking=False)
        with pytest.raises(RateLimitExceeded):
            await limiter.acquire_async(timeout=1)

    asyncio.run(main())


def test_async_with_takes_a_slot() -> None:
    limiter, clock = _limiter()

    async def main() -> None:
        async with limiter:
            pass
        async with limiter as same:
            assert same is limiter

    asyncio.run(main())
    assert clock.slept == [10.0]


def test_decorating_a_coroutine_function_limits_each_await() -> None:
    limiter, clock = _limiter()

    @limiter
    async def fetch(x: int) -> int:
        return x * 2

    async def main() -> list[int]:
        return [await fetch(1), await fetch(2)]

    assert asyncio.run(main()) == [2, 4]
    assert clock.slept == [10.0]
    assert inspect.iscoroutinefunction(fetch)


def test_rate_limit_decorates_coroutines_too() -> None:
    clock = AsyncFakeClock()

    @rate_limit(1, 5, on_limit="raise", clock=clock.time, async_sleep=clock.async_sleep)
    async def ping() -> str:
        return "pong"

    async def main() -> None:
        assert await ping() == "pong"
        with pytest.raises(RateLimitExceeded):
            await ping()

    asyncio.run(main())


def test_a_cancelled_waiter_returns_its_reservation() -> None:
    limiter = RateLimiter(1, 60)  # real clock: the waiter is cancelled long before

    async def main() -> None:
        await limiter.acquire_async()
        waiter = asyncio.ensure_future(limiter.acquire_async())
        await asyncio.sleep(0.01)
        assert limiter.retry_after() > 60  # a newcomer would queue behind the waiter
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert limiter.retry_after() <= 60

    asyncio.run(main())


def test_threads_and_coroutines_share_one_budget() -> None:
    limiter, _ = _limiter(2)
    limiter.acquire()

    async def main() -> bool:
        await limiter.acquire_async()
        return limiter.try_acquire()

    assert asyncio.run(main()) is False
