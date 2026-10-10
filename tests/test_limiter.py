"""Behaviour tests for the RateLimiter primitive."""

from __future__ import annotations

import threading

import pytest
from _fakeclock import FakeClock

from taplimit import RateLimiter, RateLimitExceeded


def test_allows_up_to_the_limit_without_waiting() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3, 60, clock=clock.time, sleep=clock.sleep)

    for _ in range(3):
        limiter.acquire()

    assert clock.slept == []


def test_blocks_until_the_oldest_slot_frees() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, 10, clock=clock.time, sleep=clock.sleep)

    limiter.acquire()  # t=0
    clock.advance(4)
    limiter.acquire()  # t=4, window now full
    limiter.acquire()  # must wait for the t=0 slot to free at t=10

    assert clock.slept == [6.0]
    assert clock.now == 10.0


def test_try_acquire_reports_free_and_full() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 10, clock=clock.time, sleep=clock.sleep)

    assert limiter.try_acquire() is True
    assert limiter.try_acquire() is False
    clock.advance(10)
    assert limiter.try_acquire() is True


def test_try_acquire_does_not_wait() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 10, clock=clock.time, sleep=clock.sleep)

    limiter.try_acquire()
    limiter.try_acquire()

    assert clock.slept == []


def test_non_blocking_acquire_raises_with_retry_after() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 10, clock=clock.time, sleep=clock.sleep)

    limiter.acquire()
    clock.advance(3)
    with pytest.raises(RateLimitExceeded) as info:
        limiter.acquire(blocking=False)

    assert info.value.retry_after == pytest.approx(7.0)


def test_rejected_call_does_not_consume_a_slot() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 10, clock=clock.time, sleep=clock.sleep)

    limiter.acquire()
    with pytest.raises(RateLimitExceeded):
        limiter.acquire(blocking=False)
    clock.advance(10)

    assert limiter.try_acquire() is True


def test_window_slides_rather_than_resetting() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, 10, clock=clock.time, sleep=clock.sleep)

    limiter.acquire()  # t=0
    limiter.acquire()  # t=0
    clock.advance(10)  # the two slots free exactly now
    assert limiter.try_acquire() is True
    assert limiter.try_acquire() is True


def test_works_as_a_decorator() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 10, clock=clock.time, sleep=clock.sleep)
    calls = 0

    @limiter
    def ping() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert ping() == 1
    clock.advance(10)
    assert ping() == 2


def test_works_as_a_context_manager() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 10, clock=clock.time, sleep=clock.sleep)

    with limiter:
        pass
    clock.advance(10)
    with limiter:
        pass

    assert clock.slept == []


def test_rejects_non_positive_configuration() -> None:
    with pytest.raises(ValueError):
        RateLimiter(0, 10)
    with pytest.raises(ValueError):
        RateLimiter(1, 0)


def test_is_thread_safe_under_contention() -> None:
    clock = FakeClock()
    # Real sleep of zero keeps the test fast while exercising the lock.
    limiter = RateLimiter(50, 1000, clock=clock.time)
    taken = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal taken
        if limiter.try_acquire():
            with lock:
                taken += 1

    threads = [threading.Thread(target=worker) for _ in range(200)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert taken == 50
