"""Small, typed, thread-safe in-process rate limiter: N calls per period, sync or async.

>>> from taplimit import RateLimiter, parse_rate
>>> limiter = RateLimiter(*parse_rate("3/s"))
>>> [limiter.try_acquire() for _ in range(4)]
[True, True, True, False]
"""

from __future__ import annotations

from ._decorator import rate_limit
from ._errors import RateLimitExceeded
from ._keyed import KeyedRateLimiter
from ._limiter import RateLimiter
from ._rate import parse_rate

__version__ = "1.0.0"

# Report the public classes under the package name, in tracebacks and reprs alike.
for _cls in (KeyedRateLimiter, RateLimitExceeded, RateLimiter):
    _cls.__module__ = __name__
del _cls

__all__ = ["KeyedRateLimiter", "RateLimitExceeded", "RateLimiter", "parse_rate", "rate_limit"]
