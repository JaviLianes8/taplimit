"""Locking, waiting and refusal logic shared by the plain and the keyed limiter."""

from __future__ import annotations

import asyncio
import math
import numbers
import operator
import threading
from collections.abc import Awaitable, Callable, Hashable
from typing import SupportsIndex

from ._errors import RateLimitExceeded
from ._window import _Window

Clock = Callable[[], float]
Sleep = Callable[[float], None]
AsyncSleep = Callable[[float], Awaitable[None]]


# Waits longer than a day are taken in steps, which every platform's sleep accepts.
_LONGEST_SLEEP = 86400.0


def _shown(number: int) -> str:
    # Keep messages short however large the number (and below the int-to-str digit limit).
    return str(number) if abs(number) < 10**15 else f"a {number.bit_length()}-bit number"


def _kind(value: object) -> str:
    return type(value).__name__[:40]


def _as_count(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer, not bool")
    # 0.1.0 accepted whole floats such as 10.0 read from config; keep honouring them.
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, SupportsIndex):
        return operator.index(value)
    raise TypeError(f"{name} must be an integer, not {_kind(value)}")


def _as_seconds(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} must be a number of seconds, not {_kind(value)}")
    try:
        return float(value)
    except OverflowError:  # an int too large for a float
        return math.inf


def _check_config(calls: int, period: float) -> tuple[int, float]:
    calls = _as_count(calls, "calls")
    if calls < 1:
        raise ValueError("calls must be at least 1")
    period = _as_seconds(period, "period")
    if not 0 < period < math.inf:  # also rejects NaN
        raise ValueError("period must be a finite number of seconds greater than 0")
    return calls, period


def _check_timeout(blocking: bool, timeout: float | None) -> float | None:
    if timeout is None:
        return None
    if not blocking:
        raise ValueError("cannot specify a timeout for a non-blocking acquire")
    seconds = _as_seconds(timeout, "timeout")
    if not seconds >= 0:  # also rejects NaN
        raise ValueError("timeout must be 0 or more seconds")
    return seconds


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
        self._calls, self._period = _check_config(calls, period)
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

    def _now(self) -> float:
        now = self._clock()
        if not math.isfinite(now):
            raise ValueError(f"the clock returned {now!r}; it must return finite seconds")
        return now

    def _window(self, key: Hashable, now: float) -> _Window:
        raise NotImplementedError

    def _peek(self, key: Hashable, now: float) -> _Window:
        return self._window(key, now)

    def _check_cost(self, cost: int) -> int:
        cost = _as_count(cost, "cost")
        if cost < 1:
            raise ValueError("cost must be at least 1")
        if cost > self._calls:
            raise ValueError(f"cost {_shown(cost)} exceeds calls ({_shown(self._calls)})")
        return cost

    def _reserve(
        self, key: Hashable, cost: int, blocking: bool, timeout: float | None
    ) -> tuple[_Window, float, float, int]:
        """Grant or reserve slots under the lock; return (window, ready, wait, checked cost)."""
        cost = self._check_cost(cost)
        timeout = _check_timeout(blocking, timeout)
        with self._lock:
            now = self._now()
            window = self._window(key, now)
            ready = window.ready_at(now, cost)
            wait = ready - now
            if wait > 0 and (not blocking or (timeout is not None and wait > timeout)):
                raise RateLimitExceeded(wait, key=key)
            window.take(ready, cost)
            return window, ready, wait, cost

    def _give_back(self, window: _Window, ready: float, cost: int) -> None:
        with self._lock:
            window.give_back(ready, cost)

    def _acquire(self, key: Hashable, cost: int, blocking: bool, timeout: float | None) -> None:
        window, ready, wait, cost = self._reserve(key, cost, blocking, timeout)
        if wait <= 0:
            return
        try:
            while (remaining := ready - self._now()) > 0:
                self._sleep(min(remaining, _LONGEST_SLEEP))
        except BaseException:
            self._give_back(window, ready, cost)
            raise

    async def _acquire_async(
        self, key: Hashable, cost: int, blocking: bool, timeout: float | None
    ) -> None:
        window, ready, wait, cost = self._reserve(key, cost, blocking, timeout)
        if wait <= 0:
            return
        try:
            while (remaining := ready - self._now()) > 0:
                await self._async_sleep(min(remaining, _LONGEST_SLEEP))
        except BaseException:  # includes cancellation: the reserved slot is returned
            self._give_back(window, ready, cost)
            raise

    def _try(self, key: Hashable, cost: int) -> bool:
        cost = self._check_cost(cost)
        with self._lock:
            now = self._now()
            window = self._window(key, now)
            if window.ready_at(now, cost) > now:
                return False
            window.take(now, cost)
            return True

    def _available(self, key: Hashable) -> int:
        with self._lock:
            now = self._now()
            return self._peek(key, now).available(now)

    def _retry_after(self, key: Hashable, cost: int) -> float:
        cost = self._check_cost(cost)
        with self._lock:
            now = self._now()
            return max(0.0, self._peek(key, now).ready_at(now, cost) - now)
