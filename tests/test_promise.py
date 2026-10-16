"""The complete promise, checked against a brute-force model under an injected clock."""

from __future__ import annotations

import random
import threading

import pytest
from _fakeclock import FakeClock

from taplimit import RateLimiter, RateLimitExceeded


def _in_window(grants: list[float], t: float, period: float) -> int:
    return sum(1 for g in grants if t - period < g <= t)


@pytest.mark.parametrize("seed", range(25))
def test_try_acquire_grants_exactly_what_the_window_allows(seed: int) -> None:
    rng = random.Random(seed)
    calls, period = rng.randint(1, 6), rng.choice([1.0, 2.5, 10.0])
    clock = FakeClock()
    limiter = RateLimiter(calls, period, clock=clock.time, sleep=clock.sleep)
    grants: list[float] = []
    for _ in range(300):
        clock.advance(rng.choice([0.0, 0.0, 0.125, 0.25, 0.5, 1.0, period]))
        cost = rng.randint(1, calls)
        expected = _in_window(grants, clock.now, period) + cost <= calls
        assert limiter.try_acquire(cost) is expected
        if expected:
            grants.extend([clock.now] * cost)
        assert limiter.available() == calls - _in_window(grants, clock.now, period)
    for t in grants:
        assert _in_window(grants, t, period) <= calls


@pytest.mark.parametrize("seed", range(15))
def test_blocking_grants_never_exceed_the_window_and_wait_minimally(seed: int) -> None:
    rng = random.Random(seed)
    calls, period = rng.randint(1, 5), rng.choice([1.0, 3.0])
    clock = FakeClock()
    limiter = RateLimiter(calls, period, clock=clock.time, sleep=clock.sleep)
    grants: list[float] = []
    for _ in range(120):
        clock.advance(rng.choice([0.0, 0.0, 0.375, 1.0]))
        cost = rng.randint(1, calls)
        before = clock.now
        predicted = limiter.retry_after(cost)
        limiter.acquire(cost=cost)
        assert clock.now - before == pytest.approx(predicted)
        grants.extend([clock.now] * cost)
        # minimal: an instant earlier the request would not have fit
        if predicted > 0:
            assert _in_window(grants[:-cost], clock.now - 1e-9, period) + cost > calls
    for t in grants:
        assert _in_window(grants, t, period) <= calls


def test_burst_is_exactly_calls_then_rate_is_calls_per_period() -> None:
    clock = FakeClock()
    limiter = RateLimiter(4, 10, clock=clock.time, sleep=clock.sleep)
    for _ in range(4):
        assert limiter.try_acquire()
    assert not limiter.try_acquire()
    for _ in range(8):
        limiter.acquire()
    assert clock.now == 20.0
    assert clock.slept == [10.0, 10.0]


def test_retry_after_is_exact_on_refusal() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3, 10, clock=clock.time, sleep=clock.sleep)
    for step in (0.0, 2.0, 5.0):
        clock.advance(step)
        limiter.acquire()
    clock.advance(1.0)  # t = 8, stamps at 0, 2, 7
    with pytest.raises(RateLimitExceeded) as one:
        limiter.acquire(blocking=False)
    assert one.value.retry_after == pytest.approx(2.0)
    with pytest.raises(RateLimitExceeded) as two:
        limiter.acquire(blocking=False, cost=2)
    assert two.value.retry_after == pytest.approx(4.0)
    assert limiter.retry_after(3) == pytest.approx(9.0)
    assert one.value.key is None


def test_a_slot_frees_exactly_one_period_after_it_was_taken() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 10, clock=clock.time, sleep=clock.sleep)
    limiter.acquire()
    clock.advance(9.999)
    assert not limiter.try_acquire()
    clock.advance(0.001)
    assert limiter.try_acquire()


def test_waiters_are_served_first_come_first_served() -> None:
    clock = FakeClock()
    entered: dict[str, threading.Event] = {}
    release: dict[str, threading.Event] = {}

    def gated_sleep(seconds: float) -> None:
        name = threading.current_thread().name
        entered[name].set()
        release[name].wait(5)

    limiter = RateLimiter(1, 10, clock=clock.time, sleep=gated_sleep)
    limiter.acquire()  # t = 0
    threads = {}
    for name in ("first", "second"):
        entered[name], release[name] = threading.Event(), threading.Event()
        threads[name] = threading.Thread(target=limiter.acquire, name=name, daemon=True)
        threads[name].start()
        assert entered[name].wait(5)
    assert limiter.retry_after() == 30.0  # a newcomer queues behind both reservations
    clock.advance(10)
    assert not limiter.try_acquire()  # cannot jump ahead of "second"
    release["first"].set()
    threads["first"].join(5)
    assert not threads["first"].is_alive()
    clock.advance(10)
    release["second"].set()
    threads["second"].join(5)
    assert not threads["second"].is_alive()
    assert limiter.try_acquire() is False
    clock.advance(10)
    assert limiter.try_acquire() is True
