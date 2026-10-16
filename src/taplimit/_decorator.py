"""The ``rate_limit`` decorator: the small, obvious entry point."""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from typing import Any, Literal, ParamSpec, TypeVar

from ._base import AsyncSleep
from ._keyed import KeyedRateLimiter
from ._limiter import RateLimiter

P = ParamSpec("P")
R = TypeVar("R")
Clock = Callable[[], float]
Sleep = Callable[[float], None]


def rate_limit(
    calls: int,
    period: float,
    *,
    on_limit: Literal["block", "raise"] = "block",
    timeout: float | None = None,
    key: Callable[..., Hashable] | None = None,
    clock: Clock = time.monotonic,
    sleep: Sleep = time.sleep,
    async_sleep: AsyncSleep | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Limit the decorated function to ``calls`` invocations per ``period`` seconds.

    With ``on_limit="block"`` (the default) a call over the limit waits until a slot
    frees, at most ``timeout`` seconds when one is given; with ``on_limit="raise"`` it
    raises RateLimitExceeded instead. Both plain and ``async def`` functions work.

    Without ``key`` all calls share one sliding window. With ``key``, a callable that
    receives the call's arguments, every distinct key gets its own window, for example
    ``key=lambda user, *_: user`` for a per-user limit. The decorated function keeps its
    exact signature; the key's own parameters are not checked against it (use
    KeyedRateLimiter.limit for that).

    Inject ``clock``, ``sleep`` and ``async_sleep`` to run it without real time.
    ``on_limit`` other than "block" or "raise", or a ``timeout`` with "raise", is a
    ValueError when the decorator is built.

    >>> @rate_limit(2, 60, on_limit="raise", clock=lambda: 0.0)
    ... def ping() -> str:
    ...     return "pong"
    >>> ping(), ping()
    ('pong', 'pong')
    >>> ping()
    Traceback (most recent call last):
    ...
    taplimit.RateLimitExceeded: rate limit exceeded, retry after 60.000s
    """
    if on_limit not in ("block", "raise"):
        raise ValueError('on_limit must be "block" or "raise"')
    blocking = on_limit == "block"
    if timeout is not None and not blocking:
        raise ValueError('timeout only applies when on_limit is "block"')
    if key is not None and not callable(key):
        raise TypeError("key must be a callable that receives the call's arguments")
    if key is None:
        limiter = RateLimiter(calls, period, clock=clock, sleep=sleep, async_sleep=async_sleep)
        return limiter.limit(blocking=blocking, timeout=timeout)
    keyed: KeyedRateLimiter[Any] = KeyedRateLimiter(
        calls, period, clock=clock, sleep=sleep, async_sleep=async_sleep
    )
    return keyed.limit(key, blocking=blocking, timeout=timeout)
