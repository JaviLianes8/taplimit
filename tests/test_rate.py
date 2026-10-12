"""Parsing of human rate strings."""

from __future__ import annotations

import pytest

from taplimit import RateLimiter, parse_rate


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10/s", (10, 1.0)),
        ("10/sec", (10, 1.0)),
        ("100/min", (100, 60.0)),
        ("100 per minute", (100, 60.0)),
        ("5/2s", (5, 2.0)),
        ("3 per 1.5 seconds", (3, 1.5)),
        ("1000/h", (1000, 3600.0)),
        ("7/DAY", (7, 86400.0)),
        ("2/15mins", (2, 900.0)),
        (" 1 / m ", (1, 60.0)),
    ],
)
def test_parses_accepted_forms(text: str, expected: tuple[int, float]) -> None:
    assert parse_rate(text) == expected


@pytest.mark.parametrize("text", ["", "10", "s/10", "0/s", "10/0s", "10/fortnight", "-1/s"])
def test_rejects_invalid_rates(text: str) -> None:
    with pytest.raises(ValueError):
        parse_rate(text)


def test_feeds_a_limiter_directly() -> None:
    limiter = RateLimiter(*parse_rate("4/2s"))
    assert (limiter.calls, limiter.period) == (4, 2.0)
