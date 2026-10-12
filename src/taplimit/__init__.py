"""Small, typed, thread-safe in-process rate limiter: N calls per period, sync or async."""

from __future__ import annotations

from ._decorator import rate_limit
from ._errors import RateLimitExceeded
from ._keyed import KeyedRateLimiter
from ._limiter import RateLimiter
from ._rate import parse_rate

__version__ = "0.2.0"

__all__ = ["KeyedRateLimiter", "RateLimitExceeded", "RateLimiter", "parse_rate", "rate_limit"]
