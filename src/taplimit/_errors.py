"""The error raised when a call would exceed the configured rate."""

from __future__ import annotations


class RateLimitExceeded(Exception):
    """Raised when a call would exceed the rate and the caller chose not to wait.

    That happens with ``blocking=False``, ``on_limit="raise"``, or when the next slot
    is further away than ``timeout``. ``retry_after`` holds the seconds until the
    refused request could be granted, so a caller can decide how long to back off.
    ``key`` is the refused key for a keyed limiter and ``None`` otherwise. The message
    shows only the wait, never the key.

    >>> from taplimit import RateLimiter
    >>> limiter = RateLimiter(1, 60, clock=lambda: 0.0)
    >>> limiter.acquire()
    >>> try:
    ...     limiter.acquire(blocking=False)
    ... except RateLimitExceeded as exc:
    ...     print(exc, exc.retry_after, exc.key)
    rate limit exceeded, retry after 60.000s 60.0 None
    """

    def __init__(self, retry_after: float, key: object = None) -> None:
        self.retry_after = retry_after
        self.key = key
        super().__init__(f"rate limit exceeded, retry after {retry_after:.3f}s")

    def __reduce__(self) -> tuple[type[RateLimitExceeded], tuple[float, object]]:
        return (type(self), (self.retry_after, self.key))
