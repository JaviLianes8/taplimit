"""The error raised when a call would exceed the configured rate."""

from __future__ import annotations


class RateLimitExceeded(Exception):
    """Raised when a call would exceed the rate and blocking is turned off.

    The ``retry_after`` attribute holds the seconds until the next slot frees,
    so a caller can decide how long to wait before trying again.
    """

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded, retry after {retry_after:.3f}s")
