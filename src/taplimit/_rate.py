"""Parse human rate strings such as ``"10/s"`` or ``"100 per minute"``."""

from __future__ import annotations

import math
import re

_UNITS = {
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "m": 60.0,
    "min": 60.0,
    "minute": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hour": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
}

_RATE = re.compile(
    r"^\s*(?P<calls>\d+)\s*(?:/|per)\s*(?P<mult>\d+(?:\.\d+)?|\.\d+)?\s*(?P<unit>[a-z]+)\s*$",
    re.IGNORECASE,
)


def parse_rate(text: str) -> tuple[int, float]:
    """Parse a rate string into ``(calls, period_seconds)``.

    Accepted forms are ``CALLS/UNIT`` or ``CALLS per UNIT``, where UNIT is one of
    ``s``, ``sec``, ``second``, ``m``, ``min``, ``minute``, ``h``, ``hr``, ``hour``,
    ``d`` or ``day`` (plurals allowed) and may carry a multiplier, as in ``5/2s`` or
    ``100/15min``. ``RateLimiter(*parse_rate("100/min"))`` builds a limiter from one.
    Raise ValueError for anything else or for a zero count or period.
    """
    match = _RATE.match(text)
    if match is None:
        raise ValueError(f"invalid rate {text!r}: expected a form such as '10/s' or '100/min'")
    unit = match["unit"].lower()
    if unit not in _UNITS and unit.endswith("s") and unit[:-1] in _UNITS:
        unit = unit[:-1]
    if unit not in _UNITS:
        raise ValueError(f"invalid rate {text!r}: unknown unit {match['unit']!r}")
    calls = int(match["calls"])
    period = float(match["mult"] or 1) * _UNITS[unit]
    if calls < 1 or not period > 0 or not math.isfinite(period):
        raise ValueError(f"invalid rate {text!r}: count and period must be positive")
    return calls, period
