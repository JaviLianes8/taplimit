"""Real-clock stress: many threads and coroutines never push the rate past the limit.

The checks cannot flake on a slow machine. A sliding window of ``calls`` per
``period`` implies that the k-th grant (0-based) happens at least
``(k // calls) * period`` after the first one. Every caller records the time *after*
its acquire returns, which is never earlier than its grant, so the sorted records
must satisfy the same bound. Scheduling delays can only make the records later.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable

from taplimit import KeyedRateLimiter, RateLimiter

EPS = 1e-6


def _assert_never_faster(start: float, records: list[float], calls: int, period: float) -> None:
    for k, t in enumerate(sorted(records)):
        assert t - start >= (k // calls) * period - EPS, (k, t - start)


def _run_threads(target: Callable[[], None], count: int) -> None:
    threads = [threading.Thread(target=target) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
        assert not thread.is_alive()


def test_blocking_threads_never_exceed_the_rate() -> None:
    calls, period, per_thread, workers = 5, 0.05, 6, 8
    limiter = RateLimiter(calls, period)
    records: list[float] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(per_thread):
            limiter.acquire()
            now = time.monotonic()
            with lock:
                records.append(now)

    start = time.monotonic()
    _run_threads(worker, workers)
    assert len(records) == per_thread * workers
    _assert_never_faster(start, records, calls, period)


def test_mixed_try_and_blocking_threads_never_exceed_the_rate() -> None:
    calls, period = 4, 0.05
    limiter = RateLimiter(calls, period)
    records: list[float] = []
    lock = threading.Lock()
    deadline = time.monotonic() + 0.4

    def worker(blocking: bool) -> None:
        while time.monotonic() < deadline:
            if blocking:
                limiter.acquire(cost=1)
            elif not limiter.try_acquire():
                time.sleep(0.001)
                continue
            now = time.monotonic()
            with lock:
                records.append(now)

    start = time.monotonic()
    threads = [threading.Thread(target=worker, args=(i % 2 == 0,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert records
    _assert_never_faster(start, records, calls, period)


def test_coroutines_never_exceed_the_rate() -> None:
    calls, period = 3, 0.05
    limiter = RateLimiter(calls, period)
    records: list[float] = []

    async def worker() -> None:
        for _ in range(4):
            await limiter.acquire_async()
            records.append(time.monotonic())

    async def main() -> None:
        await asyncio.gather(*(worker() for _ in range(6)))

    start = time.monotonic()
    asyncio.run(main())
    assert len(records) == 24
    _assert_never_faster(start, records, calls, period)


def test_keyed_threads_never_exceed_the_rate_per_key() -> None:
    calls, period = 3, 0.05
    limiter: KeyedRateLimiter[str] = KeyedRateLimiter(calls, period)
    records: dict[str, list[float]] = {"a": [], "b": []}
    lock = threading.Lock()

    def worker(key: str) -> None:
        for _ in range(5):
            limiter.acquire(key)
            now = time.monotonic()
            with lock:
                records[key].append(now)

    start = time.monotonic()
    threads = [threading.Thread(target=worker, args=("ab"[i % 2],)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    for key in records:
        assert len(records[key]) == 15
        _assert_never_faster(start, records[key], calls, period)
