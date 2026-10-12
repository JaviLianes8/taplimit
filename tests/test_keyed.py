"""Per-key limiting: independent windows, eviction, decorators and refusals."""

from __future__ import annotations

import asyncio

import pytest
from _fakeclock import FakeClock

from taplimit import KeyedRateLimiter, RateLimitExceeded, rate_limit


def _keyed(calls: int = 1, period: float = 10) -> tuple[KeyedRateLimiter[str], FakeClock]:
    clock = FakeClock()
    return KeyedRateLimiter(calls, period, clock=clock.time, sleep=clock.sleep), clock


def test_keys_have_independent_windows() -> None:
    limiter, clock = _keyed()
    assert limiter.try_acquire("alice")
    assert limiter.try_acquire("bob")
    assert not limiter.try_acquire("alice")
    limiter.acquire("bob")
    assert clock.slept == [10.0]


def test_refusal_carries_the_key_and_retry_after() -> None:
    limiter, clock = _keyed()
    limiter.acquire("alice")
    clock.advance(4)
    with pytest.raises(RateLimitExceeded) as info:
        limiter.acquire("alice", blocking=False)
    assert info.value.key == "alice"
    assert info.value.retry_after == pytest.approx(6.0)
    assert limiter.retry_after("alice") == pytest.approx(6.0)
    assert limiter.available("alice") == 0
    assert limiter.available("carol") == 1


def test_idle_keys_are_evicted_after_a_period() -> None:
    limiter, clock = _keyed()
    for name in ("a", "b", "c"):
        limiter.acquire(name)
    assert len(limiter) == 3
    clock.advance(10)
    limiter.try_acquire("d")
    assert len(limiter) == 1


def test_eviction_never_forgets_an_active_window() -> None:
    limiter, clock = _keyed(1, 10)
    limiter.acquire("a")
    clock.advance(9)
    limiter.acquire("b")
    clock.advance(1)  # "a" is idle now and gets swept, "b" is still busy
    assert not limiter.try_acquire("b")
    assert len(limiter) == 1
    assert limiter.try_acquire("a")


def test_reset_one_key_or_all() -> None:
    limiter, _ = _keyed()
    limiter.acquire("a")
    limiter.acquire("b")
    limiter.reset("a")
    assert limiter.try_acquire("a")
    assert not limiter.try_acquire("b")
    limiter.reset()
    assert len(limiter) == 0
    assert limiter.try_acquire("b")


def test_limit_derives_the_key_from_the_arguments() -> None:
    limiter, _ = _keyed()

    @limiter.limit(key=lambda user, msg: user, blocking=False)
    def send(user: str, msg: str) -> str:
        return f"{user}:{msg}"

    assert send("alice", "hi") == "alice:hi"
    assert send("bob", "hi") == "bob:hi"
    with pytest.raises(RateLimitExceeded) as info:
        send("alice", "again")
    assert info.value.key == "alice"


def test_limit_works_on_coroutines() -> None:
    limiter, _ = _keyed()

    @limiter.limit(key=lambda host: host, timeout=0)
    async def get(host: str) -> str:
        return host

    async def main() -> None:
        assert await get("x") == "x"
        with pytest.raises(RateLimitExceeded):
            await get("x")
        await limiter.acquire_async("y")
        assert limiter.available("y") == 0

    asyncio.run(main())


def test_rate_limit_with_key_builds_a_keyed_limit() -> None:
    clock = FakeClock()

    @rate_limit(1, 10, on_limit="raise", key=lambda user: user, clock=clock.time)
    def login(user: str) -> str:
        return user

    assert login("a") == "a"
    assert login("b") == "b"
    with pytest.raises(RateLimitExceeded):
        login("a")


def test_repr_and_validation() -> None:
    limiter, _ = _keyed(3, 2.0)
    assert repr(limiter) == "KeyedRateLimiter(calls=3, period=2.0)"
    with pytest.raises(ValueError):
        KeyedRateLimiter(0, 1)
    with pytest.raises(ValueError):
        limiter.limit(key=str, cost=4)
