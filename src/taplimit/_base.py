"""Locking, waiting and refusal logic shared by the plain and the keyed limiter."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable, Hashable

from ._errors import RateLimitExceeded
from ._window import _Window

Clock = Callable[[], float]
Sleep = Callable[[float], None]
AsyncSleep = Callable[[float], Awaitable[None]]


def _check_config(calls: int, period: float) -> None:
    if calls < 1:
        raise ValueError("calls must be at least 1")
    if period <= 0:
        raise ValueError("period must be greater than 0")


class _Base:
    """Owns the lock and the clock; subclasses decide which window a key maps to."""

    def __init__(
        self,
        calls: int,
        period: float,
        clock: Clock,
        sleep: Sleep,
        async_sleep: AsyncSleep | None,
    ) -> None:
        _check_config(calls, period)
        self._calls = calls
        self._period = period
        self._clock = clock
        self._sleep = sleep
        self._async_sleep: AsyncSleep = asyncio.sleep if async_sleep is None else async_sleep
        self._lock = threading.Lock()

    @property
    def calls(self) -> int:
        """The number of slots granted per period."""
        return self._calls

    @property
    def period(self) -> float:
        """The length of the sliding window, in seconds."""
        return self._period

    def _window(self, key: Hashable, now: float) -> _Window:
        raise NotImplementedError

    def _check_cost(self, cost: int) -> None:
        if cost < 1:
            raise ValueError("cost must be at least 1")
        if cost > self._calls:
            raise ValueError(f"cost {cost} exceeds the {self._calls} slots per period")

    def _reserve(
        self, key: Hashable, cost: int, blocking: bool, timeout: float | None, refused_key: object
    ) -> tuple[_Window, float, float, int]:
        """Grant or reserve slots under the lock; return (window, ready, wait, epoch)."""
        self._check_cost(cost)
        if timeout is not None:
            if not blocking:
                raise ValueError("cannot specify a timeout for a non-blocking acquire")
            if timeout < 0:
                raise ValueError("timeout must not be negative")
        with self._lock:
            now = self._clock()
            window = self._window(key, now)
            ready = window.ready_at(now, cost)
            wait = ready - now
            if wait > 0 and (not blocking or (timeout is not None and wait > timeout)):
                raise RateLimitExceeded(wait, key=refused_key)
            window.take(ready, cost)
            return window, ready, wait, window.epoch

    def _give_back(self, window: _Window, ready: float, cost: int, epoch: int) -> None:
        with self._lock:
            window.give_back(ready, cost, epoch)

    def _acquire(
        self, key: Hashable, cost: int, blocking: bool, timeout: float | None, refused: object
    ) -> None:
        window, ready, wait, epoch = self._reserve(key, cost, blocking, timeout, refused)
        if wait <= 0:
            return
        try:
            while (remaining := ready - self._clock()) > 0:
                self._sleep(remaining)
        except BaseException:
            self._give_back(window, ready, cost, epoch)
            raise

    async def _acquire_async(
        self, key: Hashable, cost: int, blocking: bool, timeout: float | None, refused: object
    ) -> None:
        window, ready, wait, epoch = self._reserve(key, cost, blocking, timeout, refused)
        if wait <= 0:
            return
        try:
            while (remaining := ready - self._clock()) > 0:
                await self._async_sleep(remaining)
        except BaseException:  # includes cancellation: the reserved slot is returned
            self._give_back(window, ready, cost, epoch)
            raise

    def _try(self, key: Hashable, cost: int) -> bool:
        self._check_cost(cost)
        with self._lock:
            now = self._clock()
            window = self._window(key, now)
            if window.ready_at(now, cost) > now:
                return False
            window.take(now, cost)
            return True

    def _available(self, key: Hashable) -> int:
        with self._lock:
            now = self._clock()
            return self._window(key, now).available(now)

    def _retry_after(self, key: Hashable, cost: int) -> float:
        self._check_cost(cost)
        with self._lock:
            now = self._clock()
            return max(0.0, self._window(key, now).ready_at(now, cost) - now)
