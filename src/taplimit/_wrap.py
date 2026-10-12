"""Wrap a sync or async callable so every call first passes through a limiter."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")


def wrap(
    func: Callable[P, R],
    before: Callable[P, None],
    before_async: Callable[P, Awaitable[None]],
) -> Callable[P, R]:
    """Return ``func`` guarded by ``before`` (or ``before_async`` for coroutines).

    The guard receives the call's arguments, which lets keyed limiters derive a key.
    The signature, name and docstring of ``func`` are preserved.
    """
    if inspect.iscoroutinefunction(func):
        target = cast(Callable[P, Awaitable[Any]], func)

        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            await before_async(*args, **kwargs)
            return await target(*args, **kwargs)

        return cast(Callable[P, R], async_wrapper)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        before(*args, **kwargs)
        return func(*args, **kwargs)

    return wrapper
