"""The ``rate_limit`` decorator: the small, obvious entry point."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from ._limiter import RateLimiter

P = ParamSpec("P")
R = TypeVar("R")


def rate_limit(
    calls: int,
    period: float,
    *,
    on_limit: str = "block",
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Limit the decorated function to ``calls`` invocations per ``period`` seconds.

    With ``on_limit="block"`` (the default) a call over the limit waits until a slot
    frees; with ``on_limit="raise"`` it raises RateLimitExceeded instead. All calls
    to the decorated function share one sliding window. Inject ``clock`` and ``sleep``
    to drive it from tests without real time passing.
    """
    if on_limit not in ("block", "raise"):
        raise ValueError('on_limit must be "block" or "raise"')
    blocking = on_limit == "block"
    limiter = RateLimiter(calls, period, clock=clock, sleep=sleep)

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            limiter.acquire(blocking=blocking)
            return func(*args, **kwargs)

        return wrapper

    return decorator
