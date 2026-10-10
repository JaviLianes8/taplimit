"""A thread-safe, in-process, sliding-window rate limiter."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from functools import wraps
from types import TracebackType
from typing import ParamSpec, TypeVar

from ._errors import RateLimitExceeded

P = ParamSpec("P")
R = TypeVar("R")


class RateLimiter:
    """Allow at most ``calls`` acquisitions per ``period`` seconds.

    The window slides: a slot frees exactly ``period`` seconds after the call that
    took it, not on a shared clock boundary, so a burst never carries over. The
    limiter is safe to share across threads and across functions, which lets several
    callables draw on a single budget.

    Inject ``clock`` (returns seconds) and ``sleep`` (waits seconds) to drive the
    limiter from tests without real time passing.
    """

    def __init__(
        self,
        calls: int,
        period: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if calls < 1:
            raise ValueError("calls must be at least 1")
        if period <= 0:
            raise ValueError("period must be greater than 0")
        self._calls = calls
        self._period = period
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._hits: deque[float] = deque()

    def _purge(self, now: float) -> None:
        horizon = now - self._period
        hits = self._hits
        while hits and hits[0] <= horizon:
            hits.popleft()

    def try_acquire(self) -> bool:
        """Take a slot without waiting. Return True if one was free, else False."""
        with self._lock:
            now = self._clock()
            self._purge(now)
            if len(self._hits) < self._calls:
                self._hits.append(now)
                return True
            return False

    def acquire(self, *, blocking: bool = True) -> None:
        """Take a slot, waiting for one when ``blocking`` is True.

        When ``blocking`` is False and every slot is taken, raise RateLimitExceeded
        carrying the seconds until the next slot opens. A rejected call never
        consumes a slot.
        """
        while True:
            with self._lock:
                now = self._clock()
                self._purge(now)
                if len(self._hits) < self._calls:
                    self._hits.append(now)
                    return
                wait = self._hits[0] + self._period - now
            if not blocking:
                raise RateLimitExceeded(wait)
            self._sleep(wait if wait > 0 else 0.0)

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

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            self.acquire()
            return func(*args, **kwargs)

        return wrapper
