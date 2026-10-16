"""Seeded fuzzing against an independent brute-force model, and bounded work at scale."""

from __future__ import annotations

import random
import tracemalloc
from collections import deque
from collections.abc import Iterator
from typing import Any

import pytest
from _fakeclock import FakeClock

from taplimit import KeyedRateLimiter, RateLimiter, RateLimitExceeded


def _earliest(stamps: list[float], now: float, cost: int, calls: int, period: float) -> float:
    """Brute force: the first candidate instant where ``cost`` more slots fit the window."""
    floor = max([now, *stamps])
    candidates = sorted({floor, *(s + period for s in stamps if s + period >= floor)})
    for t in candidates:
        if sum(1 for s in stamps if t - period < s <= t) + cost <= calls:
            return t
    raise AssertionError("no candidate fits")  # pragma: no cover


class _Interrupt(Exception):
    pass


@pytest.mark.parametrize("seed", range(40))
def test_every_operation_matches_a_brute_force_model(seed: int) -> None:
    rng = random.Random(seed)
    calls, period = rng.randint(1, 6), rng.choice([1.0, 2.5, 7.0])
    clock, interrupt = FakeClock(), [False]

    def sleep(seconds: float) -> None:
        if interrupt[0]:
            raise _Interrupt
        clock.sleep(seconds)

    limiter = RateLimiter(calls, period, clock=clock.time, sleep=sleep)
    stamps: list[float] = []
    for _ in range(250):
        # Steps of period / 16 keep every sum exact in binary floating point.
        clock.advance(rng.choice([0.0, 0.0, 0.5, 1.0, period, rng.randrange(32) * period / 16]))
        cost, op = rng.randint(1, calls), rng.randrange(6)
        ready = _earliest(stamps, clock.now, cost, calls, period)
        assert limiter.retry_after(cost) == ready - clock.now
        assert limiter.available() == (
            0
            if any(s > clock.now for s in stamps)
            else calls - len([s for s in stamps if clock.now - period < s <= clock.now])
        )
        if op == 0:
            assert limiter.try_acquire(cost) is (ready == clock.now)
            stamps += [clock.now] * cost if ready == clock.now else []
        elif op == 1:
            if ready == clock.now:
                limiter.acquire(blocking=False, cost=cost)
                stamps += [ready] * cost
            else:
                with pytest.raises(RateLimitExceeded) as info:
                    limiter.acquire(blocking=False, cost=cost)
                assert info.value.retry_after == ready - clock.now
        elif op == 2:
            limiter.acquire(cost=cost)
            assert clock.now == ready
            stamps += [ready] * cost
        elif op == 3:
            interrupt[0] = True
            try:
                limiter.acquire(cost=cost)
                stamps += [ready] * cost  # granted at once, no wait to interrupt
                assert ready == clock.now
            except _Interrupt:
                assert ready > clock.now
            interrupt[0] = False
        elif op == 4:
            limiter.reset()
            stamps = [s for s in stamps if s > clock.now]
        else:
            timeout = rng.choice([0.0, 0.5, period])
            if ready - clock.now <= timeout:
                limiter.acquire(cost=cost, timeout=timeout)
                assert clock.now == ready
                stamps += [ready] * cost
            else:
                with pytest.raises(RateLimitExceeded) as info:
                    limiter.acquire(cost=cost, timeout=timeout)
                assert info.value.retry_after == ready - clock.now


@pytest.mark.parametrize("seed", range(10))
def test_keyed_windows_each_match_the_model(seed: int) -> None:
    rng = random.Random(seed)
    clock = FakeClock()
    keyed: KeyedRateLimiter[int] = KeyedRateLimiter(3, 2.0, clock=clock.time, sleep=clock.sleep)
    stamps: dict[int, list[float]] = {}
    for _ in range(300):
        clock.advance(rng.choice([0.0, 0.25, 1.0, 2.0, 5.0]))
        key, cost = rng.randrange(4), rng.randint(1, 3)
        mine = stamps.setdefault(key, [])
        fits = _earliest(mine, clock.now, cost, 3, 2.0) == clock.now
        assert keyed.try_acquire(key, cost) is fits
        mine += [clock.now] * cost if fits else []
        live = {k for k, v in stamps.items() if any(clock.now - 2.0 < s for s in v)}
        assert live <= set(keyed._windows) and len(keyed) <= 4


class _CountingDeque(deque[Any]):
    steps = 0

    def __iter__(self) -> Iterator[Any]:
        for item in super().__iter__():
            _CountingDeque.steps += 1
            yield item

    def __reversed__(self) -> Iterator[Any]:
        for item in super().__reversed__():
            _CountingDeque.steps += 1
            yield item


def test_queueing_many_waiters_does_linear_work() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 1.0, clock=clock.time, sleep=lambda s: None)
    limiter._win.runs = _CountingDeque()
    _CountingDeque.steps = 0
    waiters = 5000
    for _ in range(waiters):
        limiter._reserve(None, 1, True, None, None)  # what each blocking caller does first
    assert limiter.retry_after() == waiters
    assert _CountingDeque.steps <= 3 * waiters


def test_a_huge_cost_takes_constant_memory_and_time() -> None:
    clock = FakeClock()
    calls = 10**12  # one slot per byte, for instance
    limiter = RateLimiter(calls, 1.0, clock=clock.time, sleep=clock.sleep)
    tracemalloc.start()
    try:
        assert limiter.try_acquire(calls)
        clock.advance(0.5)
        assert limiter.retry_after(calls) == 0.5
        limiter.acquire(cost=calls)
        assert clock.now == 1.0
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 100_000


def test_an_abandoned_huge_reservation_is_returned_in_one_step() -> None:
    clock = FakeClock()
    calls = 10**12
    limiter = RateLimiter(
        calls, 1.0, clock=clock.time, sleep=lambda s: (_ for _ in ()).throw(_Interrupt())
    )
    limiter.try_acquire(calls)
    with pytest.raises(_Interrupt):
        limiter.acquire(cost=calls)
    assert limiter.retry_after(calls) == 1.0
    assert len(limiter._win.runs) == 1
