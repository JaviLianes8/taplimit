"""One independent sliding window per key, with idle keys evicted automatically."""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from typing import Generic, ParamSpec, TypeVar

from ._base import AsyncSleep, Clock, Sleep, _Base, _check_timeout
from ._window import _Window
from ._wrap import wrap

K = TypeVar("K", bound=Hashable)
P = ParamSpec("P")
R = TypeVar("R")


class KeyedRateLimiter(_Base, Generic[K]):
    """Allow at most ``calls`` acquisitions per ``period`` seconds for each key.

    Every key (a user id, a host, an API token) gets its own sliding window with the
    same semantics as RateLimiter, and keys never affect each other. A key whose
    window has emptied is forgotten during a sweep that runs at most once per
    ``period``, so memory is bounded by the keys active in the last period or two.
    All keys share one lock; only the short bookkeeping runs under it, never a wait.

    >>> limiter: KeyedRateLimiter[str] = KeyedRateLimiter(1, 60, clock=lambda: 0.0)
    >>> limiter.try_acquire("alice"), limiter.try_acquire("bob"), limiter.try_acquire("alice")
    (True, True, False)
    >>> limiter.retry_after("alice"), limiter.available("carol"), len(limiter)
    (60.0, 1, 2)
    """

    def __init__(
        self,
        calls: int,
        period: float,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = time.sleep,
        async_sleep: AsyncSleep | None = None,
    ) -> None:
        super().__init__(calls, period, clock, sleep, async_sleep)
        self._windows: dict[Hashable, _Window] = {}
        self._last_sweep = clock()

    def _window(self, key: Hashable, now: float) -> _Window:
        if now - self._last_sweep >= self._period:
            self._last_sweep = now
            idle = [k for k, w in self._windows.items() if w.idle(now)]
            for k in idle:
                del self._windows[k]
        window = self._windows.get(key)
        if window is None:
            window = self._windows[key] = _Window(self._calls, self._period)
        return window

    def _peek(self, key: Hashable, now: float) -> _Window:
        # Read-only queries must not start tracking a key nobody has used.
        window = self._windows.get(key)
        return _Window(self._calls, self._period) if window is None else window

    def acquire(
        self, key: K, *, blocking: bool = True, timeout: float | None = None, cost: int = 1
    ) -> None:
        """Take ``cost`` slots for ``key``, with the options of RateLimiter.acquire.

        A refusal raises RateLimitExceeded whose ``key`` is the refused key.
        """
        self._acquire(key, cost, blocking, timeout, key)

    async def acquire_async(
        self, key: K, *, blocking: bool = True, timeout: float | None = None, cost: int = 1
    ) -> None:
        """Like ``acquire`` but waits with ``await``; cancellation returns the slots."""
        await self._acquire_async(key, cost, blocking, timeout, key)

    def try_acquire(self, key: K, cost: int = 1) -> bool:
        """Take ``cost`` slots for ``key`` without waiting. Return True on success."""
        return self._try(key, cost)

    def available(self, key: K) -> int:
        """Return how many slots a ``try_acquire`` for ``key`` could take right now."""
        return self._available(key)

    def retry_after(self, key: K, cost: int = 1) -> float:
        """Return the seconds until ``cost`` slots for ``key`` could be taken."""
        return self._retry_after(key, cost)

    def reset(self, key: K | None = None) -> None:
        """Forget past grants of ``key``, or of every key when it is None.

        As with RateLimiter.reset, callers already waiting keep their reserved slots.
        """
        with self._lock:
            now = self._clock()
            for k in list(self._windows) if key is None else [key]:
                window = self._windows.get(k)
                if window is not None:
                    window.clear(now)
                    if not window.runs:
                        del self._windows[k]

    def __len__(self) -> int:
        """Return the number of keys currently tracked."""
        with self._lock:
            return len(self._windows)

    def __repr__(self) -> str:
        return f"KeyedRateLimiter(calls={self._calls}, period={self._period})"

    def limit(
        self,
        key: Callable[P, K],
        *,
        blocking: bool = True,
        timeout: float | None = None,
        cost: int = 1,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Return a decorator that limits each call under the key ``key(*args, **kwargs)``.

        ``key`` receives exactly the arguments of the decorated call. Plain and
        ``async def`` functions are both supported and keep their signature.
        """
        cost = self._check_cost(cost)
        timeout = _check_timeout(blocking, timeout)

        def before(*args: P.args, **kwargs: P.kwargs) -> None:
            k = key(*args, **kwargs)
            self._acquire(k, cost, blocking, timeout, k)

        async def before_async(*args: P.args, **kwargs: P.kwargs) -> None:
            k = key(*args, **kwargs)
            await self._acquire_async(k, cost, blocking, timeout, k)

        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            return wrap(func, before, before_async)

        return decorator
