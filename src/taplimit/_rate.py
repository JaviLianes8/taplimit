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
    # "per" must stand alone: "10 per s" and "5per2s" parse, "10pers" does not.
    r"^\s*(?P<calls>\d+)\s*(?:/|(?<![a-z])per(?![a-z]))"
    r"\s*(?P<mult>\d+(?:\.\d+)?|\.\d+)?\s*(?P<unit>[a-z]+)\s*$",
    re.IGNORECASE | re.ASCII,
)


def _shown(text: str) -> str:
    # Echo at most 40 characters so a huge or hostile string never floods a log line.
    return repr(text) if len(text) <= 40 else repr(text[:40]) + "..."


def parse_rate(text: str) -> tuple[int, float]:
    """Parse a rate string into ``(calls, period_seconds)``.

    Accepted forms are ``CALLS/UNIT`` or ``CALLS per UNIT``, where UNIT is one of
    ``s``, ``sec``, ``second``, ``m``, ``min``, ``minute``, ``h``, ``hr``, ``hour``,
    ``d`` or ``day`` (plurals allowed) and may carry a multiplier, as in ``5/2s`` or
    ``100/15min``. ``RateLimiter(*parse_rate("100/min"))`` builds a limiter from one.
    Raise ValueError for anything else or for a zero count or period, and TypeError
    when ``text`` is not a string.

    >>> parse_rate("100/min")
    (100, 60.0)
    >>> parse_rate("5 per 2s")
    (5, 2.0)
    >>> parse_rate("10/ms")
    Traceback (most recent call last):
    ...
    ValueError: invalid rate '10/ms': unknown unit 'ms'
    """
    if not isinstance(text, str):
        raise TypeError(f"rate must be a string, not {type(text).__name__[:40]}")
    match = _RATE.match(text)
    if match is None:
        raise ValueError(
            f"invalid rate {_shown(text)}: expected a form such as '10/s' or '100/min'"
        )
    unit = match["unit"].lower()
    # Plurals only for multi-letter units, so "ms" is refused instead of read as minutes.
    if unit not in _UNITS and unit.endswith("s") and len(unit) > 2 and unit[:-1] in _UNITS:
        unit = unit[:-1]
    if unit not in _UNITS:
        raise ValueError(f"invalid rate {_shown(text)}: unknown unit {_shown(match['unit'])}")
    try:
        calls = int(match["calls"])
    except ValueError:  # more digits than the interpreter converts
        raise ValueError(f"invalid rate {_shown(text)}: count too large") from None
    period = float(match["mult"] or 1) * _UNITS[unit]
    if calls < 1 or not 0 < period < math.inf:
        raise ValueError(
            f"invalid rate {_shown(text)}: count and period must be positive and finite"
        )
    return calls, period
