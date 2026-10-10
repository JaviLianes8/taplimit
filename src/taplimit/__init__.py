"""Small, typed, thread-safe in-process rate-limit decorator: N calls per period."""

from __future__ import annotations

from ._decorator import rate_limit
from ._errors import RateLimitExceeded
from ._limiter import RateLimiter

__version__ = "0.1.0"

__all__ = ["RateLimitExceeded", "RateLimiter", "rate_limit"]
