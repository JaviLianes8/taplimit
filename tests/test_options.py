"""Timeouts, weighted acquisition, introspection and interruption of RateLimiter."""

from __future__ import annotations

import pickle

import pytest
from _fakeclock import FakeClock

from taplimit import RateLimiter, RateLimitExceeded


def _limiter(calls: int = 2, period: float = 10) -> tuple[RateLimiter, FakeClock]:
    clock = FakeClock()
    return RateLimiter(calls, period, clock=clock.time, sleep=clock.sleep), clock


def test_timeout_waits_when_the_slot_comes_in_time() -> None:
    limiter, clock = _limiter(1)
    limiter.acquire()
    clock.advance(4)
    limiter.acquire(timeout=6)
    assert clock.slept == [6.0]


def test_timeout_raises_at_once_when_the_slot_is_too_far() -> None:
    limiter, clock = _limiter(1)
    limiter.acquire()
    with pytest.raises(RateLimitExceeded) as info:
        limiter.acquire(timeout=5)
    assert info.value.retry_after == pytest.approx(10.0)
    assert clock.slept == []
    assert limiter.retry_after() == pytest.approx(10.0)  # nothing was reserved


def test_timeout_zero_acts_like_a_non_blocking_attempt() -> None:
    limiter, _ = _limiter(1)
    limiter.acquire(timeout=0)
    with pytest.raises(RateLimitExceeded):
        limiter.acquire(timeout=0)


def test_invalid_timeout_combinations_are_rejected() -> None:
    limiter, _ = _limiter()
    with pytest.raises(ValueError):
        limiter.acquire(blocking=False, timeout=1)
    with pytest.raises(ValueError):
        limiter.acquire(timeout=-1)


def test_cost_takes_several_slots_at_once() -> None:
    limiter, clock = _limiter(3)
    limiter.acquire(cost=2)
    assert limiter.available() == 1
    assert limiter.try_acquire(2) is False
    assert limiter.try_acquire(1) is True
    limiter.acquire(cost=3)
    assert clock.slept == [10.0]


def test_cost_outside_the_budget_is_rejected() -> None:
    limiter, _ = _limiter(3)
    for bad in (0, 4):
        with pytest.raises(ValueError):
            limiter.acquire(cost=bad)
        with pytest.raises(ValueError):
            limiter.try_acquire(bad)
        with pytest.raises(ValueError):
            limiter.retry_after(bad)


def test_available_and_retry_after_track_the_window() -> None:
    limiter, clock = _limiter(2)
    assert limiter.available() == 2
    assert limiter.retry_after() == 0.0
    limiter.acquire()
    clock.advance(3)
    limiter.acquire()
    assert limiter.available() == 0
    assert limiter.retry_after() == pytest.approx(7.0)
    assert limiter.retry_after(2) == pytest.approx(10.0)


def test_reset_frees_the_whole_budget() -> None:
    limiter, _ = _limiter(2)
    limiter.acquire(cost=2)
    limiter.reset()
    assert limiter.available() == 2


def test_an_interrupted_wait_gives_its_slot_back() -> None:
    clock = FakeClock()

    def interrupted(_seconds: float) -> None:
        raise KeyboardInterrupt

    limiter = RateLimiter(1, 10, clock=clock.time, sleep=interrupted)
    limiter.acquire()
    with pytest.raises(KeyboardInterrupt):
        limiter.acquire()
    assert limiter.retry_after() == pytest.approx(10.0)  # the reservation is gone


def test_sleep_returning_early_does_not_grant_early() -> None:
    clock = FakeClock()
    naps: list[float] = []

    def short_nap(seconds: float) -> None:
        naps.append(seconds)
        clock.advance(max(seconds / 2, 0.5))

    limiter = RateLimiter(1, 8, clock=clock.time, sleep=short_nap)
    limiter.acquire()
    limiter.acquire()
    assert clock.now >= 8.0
    assert len(naps) > 1


def test_properties_and_repr() -> None:
    limiter, _ = _limiter(5, 2.5)
    assert (limiter.calls, limiter.period) == (5, 2.5)
    assert repr(limiter) == "RateLimiter(calls=5, period=2.5)"


def test_limit_decorator_applies_its_options() -> None:
    limiter, clock = _limiter(2)

    @limiter.limit(cost=2, blocking=False)
    def heavy() -> str:
        return "done"

    assert heavy() == "done"
    with pytest.raises(RateLimitExceeded):
        heavy()
    clock.advance(10)
    assert heavy() == "done"


def test_the_error_pickles_with_its_fields() -> None:
    error = pickle.loads(pickle.dumps(RateLimitExceeded(1.5, key="alice")))
    assert (error.retry_after, error.key) == (1.5, "alice")
    assert "1.500" in str(error)
