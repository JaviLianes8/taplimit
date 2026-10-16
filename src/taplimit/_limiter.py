"""A thread-safe, asyncio-aware, in-process, sliding-window rate limiter."""

from __future__ import annotations

import time
from collections.abc import Callable
from types import TracebackType
from typing import Any, ParamSpec, TypeVar

from ._base import AsyncSleep, Clock, Sleep, _Base, _check_timeout
from ._window import _Window
from ._wrap import wrap

P = ParamSpec("P")
R = TypeVar("R")


class RateLimiter(_Base):
    """Allow at most ``calls`` acquisitions per ``period`` seconds.

    The window slides: at every instant ``t`` at most ``calls`` slots carry a grant
    time in ``(t - period, t]``, so a slot frees exactly ``period`` seconds after the
    call that took it and a burst never carries over a fixed boundary. Up to ``calls``
    acquisitions succeed at once (the burst); after that the sustained rate is
    ``calls / period``.

    One limiter is safe to share across threads, coroutines and functions. Blocking
    callers reserve their slot under the lock and then wait for it, so they are served
    first come, first served and a ``try_acquire`` never jumps the queue.

    Inject ``clock`` (returns seconds), ``sleep`` (waits seconds) and ``async_sleep``
    (awaits seconds, default ``asyncio.sleep``) to run it from tests without real time.

    >>> now = [0.0]
    >>> def sleep(seconds: float) -> None:
    ...     now[0] += seconds
    >>> limiter = RateLimiter(2, 10, clock=lambda: now[0], sleep=sleep)
    >>> [limiter.try_acquire() for _ in range(3)]
    [True, True, False]
    >>> limiter.available(), limiter.retry_after()
    (0, 10.0)
    >>> limiter.acquire()  # waits ten seconds on the injected clock
    >>> now[0]
    10.0
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
        self._win = _Window(self._calls, self._period)

    def _window(self, key: object, now: float) -> _Window:
        return self._win

    def acquire(
        self, *, blocking: bool = True, timeout: float | None = None, cost: int = 1
    ) -> None:
        """Take ``cost`` slots, waiting for them when ``blocking`` is True.

        With ``timeout`` the call waits at most that many seconds; if the slots cannot
        be granted in time it raises RateLimitExceeded at once rather than sleeping in
        vain. With ``blocking=False`` it raises as soon as the slots are not free. The
        exception's ``retry_after`` says how long until they would be. A refused call
        never consumes a slot, and a wait interrupted by an exception gives it back.
        """
        self._acquire(None, cost, blocking, timeout)

    async def acquire_async(
        self, *, blocking: bool = True, timeout: float | None = None, cost: int = 1
    ) -> None:
        """Like ``acquire`` but waits with ``await``; cancellation returns the slots."""
        await self._acquire_async(None, cost, blocking, timeout)

    def try_acquire(self, cost: int = 1) -> bool:
        """Take ``cost`` slots without waiting. Return True if they were free."""
        return self._try(None, cost)

    def available(self) -> int:
        """Return how many slots a ``try_acquire`` could take right now."""
        return self._available(None)

    def retry_after(self, cost: int = 1) -> float:
        """Return the seconds until ``cost`` slots could be taken; 0.0 if now."""
        return self._retry_after(None, cost)

    def reset(self) -> None:
        """Forget past grants, freeing the budget for new callers.

        Callers already waiting keep their reserved slots, so new callers still queue
        behind them and the limit holds across a reset.
        """
        with self._lock:
            self._win.clear(self._clock())

    def __repr__(self) -> str:
        return f"RateLimiter(calls={self._calls}, period={self._period})"

    def __enter__(self) -> RateLimiter:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def __aenter__(self) -> RateLimiter:
        await self.acquire_async()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        """Decorate a function or coroutine function so each call takes one slot."""
        return self.limit()(func)

    def limit(
        self, *, blocking: bool = True, timeout: float | None = None, cost: int = 1
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Return a decorator whose calls each ``acquire`` with these options.

        Works on plain and ``async def`` functions alike and preserves the signature.

        >>> limiter = RateLimiter(1, 60, clock=lambda: 0.0)
        >>> @limiter.limit(blocking=False)
        ... def ping() -> str:
        ...     return "pong"
        >>> ping()
        'pong'
        >>> limiter.reset()  # forget the grant
        >>> ping()
        'pong'
        """
        cost = self._check_cost(cost)
        timeout = _check_timeout(blocking, timeout)

        def before(*_args: Any, **_kwargs: Any) -> None:
            self._acquire(None, cost, blocking, timeout)

        async def before_async(*_args: Any, **_kwargs: Any) -> None:
            await self._acquire_async(None, cost, blocking, timeout)

        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            return wrap(func, before, before_async)

        return decorator
