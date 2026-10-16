"""Every argument is checked when it is given, with the documented error and message."""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest
from _fakeclock import FakeClock

from taplimit import KeyedRateLimiter, RateLimiter, RateLimitExceeded, parse_rate, rate_limit

BUILDERS: list[Any] = [RateLimiter, KeyedRateLimiter, rate_limit]


@pytest.mark.parametrize("build", BUILDERS)
@pytest.mark.parametrize("calls", [True, False, 2.5, "3", None, math.nan, math.inf, Decimal(3)])
def test_calls_must_be_an_integer(build: Any, calls: object) -> None:
    with pytest.raises(TypeError, match=r"^calls must be an integer, not "):
        build(calls, 1)


@pytest.mark.parametrize("build", BUILDERS)
@pytest.mark.parametrize("calls", [0, -1, 0.0])
def test_calls_must_be_at_least_one(build: Any, calls: object) -> None:
    with pytest.raises(ValueError, match=r"^calls must be at least 1$"):
        build(calls, 1)


@pytest.mark.parametrize("build", BUILDERS)
@pytest.mark.parametrize("period", [True, "1", None, Decimal("1.5"), 1j])
def test_period_must_be_a_real_number(build: Any, period: object) -> None:
    with pytest.raises(TypeError, match=r"^period must be a number of seconds, not "):
        build(1, period)


@pytest.mark.parametrize("build", BUILDERS)
@pytest.mark.parametrize("period", [0, -0.0, -1, math.nan, math.inf, -math.inf, 10**400])
def test_period_must_be_finite_and_positive(build: Any, period: object) -> None:
    with pytest.raises(ValueError, match=r"^period must be a finite number of seconds greater"):
        build(1, period)


def test_period_is_stored_as_float_seconds() -> None:
    assert RateLimiter(2, 10).period == 10.0
    assert isinstance(RateLimiter(2, 10).period, float)
    quarter: object = Fraction(1, 4)
    assert RateLimiter(3, quarter).period == 0.25  # type: ignore[arg-type]
    assert repr(KeyedRateLimiter(3, 2)) == "KeyedRateLimiter(calls=3, period=2.0)"
    assert RateLimiter(10.0, 1).calls == 10  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout", [True, "1", Decimal(1)])
def test_timeout_must_be_a_real_number(timeout: object) -> None:
    limiter = RateLimiter(1, 1)
    with pytest.raises(TypeError, match=r"^timeout must be a number of seconds, not "):
        limiter.acquire(timeout=timeout)  # type: ignore[arg-type]


def test_timeout_is_checked_when_a_decorator_is_built() -> None:
    limiter, keyed = RateLimiter(1, 1), KeyedRateLimiter[str](1, 1)
    with pytest.raises(ValueError, match=r"non-blocking"):
        limiter.limit(blocking=False, timeout=1)
    with pytest.raises(ValueError, match=r"^timeout must be 0 or more seconds$"):
        keyed.limit(lambda: "k", timeout=-1)
    with pytest.raises(ValueError, match=r"^timeout must be 0 or more seconds$"):
        rate_limit(1, 1, timeout=math.nan)
    with pytest.raises(ValueError, match='only applies when on_limit is "block"'):
        rate_limit(1, 1, on_limit="raise", timeout=1)


def test_a_timeout_too_large_for_a_float_waits_like_no_limit() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 30, clock=clock.time, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire(timeout=10**400)
    assert clock.now == 30.0

    @rate_limit(1, 30, timeout=10**400, clock=clock.time, sleep=clock.sleep)
    def ping() -> str:
        return "pong"

    assert (ping(), ping()) == ("pong", "pong")
    assert clock.now == 60.0


def test_a_key_must_be_callable_when_the_decorator_is_built() -> None:
    message = r"^key must be a callable that receives the call's arguments$"
    with pytest.raises(TypeError, match=message):
        rate_limit(1, 1, key="user")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=message):
        KeyedRateLimiter[str](1, 1).limit("user")  # type: ignore[arg-type]


def test_an_infinite_timeout_waits_as_long_as_needed() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 30, clock=clock.time, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire(timeout=math.inf)
    assert clock.now == 30.0


@pytest.mark.parametrize("cost", [True, 1.5, "1", None])
def test_cost_must_be_an_integer(cost: object) -> None:
    limiter = RateLimiter(3, 1)
    with pytest.raises(TypeError, match=r"^cost must be an integer, not "):
        limiter.try_acquire(cost)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"^cost must be an integer, not "):
        limiter.limit(cost=cost)  # type: ignore[arg-type]


def test_type_names_in_messages_are_bounded() -> None:
    odd = type("X" * 500, (), {})()
    with pytest.raises(TypeError) as info:
        RateLimiter(odd, 1)
    assert len(str(info.value)) < 80
    with pytest.raises(TypeError) as info:
        parse_rate(odd)
    assert str(info.value) == "rate must be a string, not " + "X" * 40


def test_rate_messages_show_at_most_forty_characters() -> None:
    with pytest.raises(ValueError) as info:
        parse_rate("x" * 10_000)
    assert (
        str(info.value)
        == f"invalid rate '{'x' * 40}'...: expected a form such as '10/s' or '100/min'"
    )
    with pytest.raises(ValueError, match=r"^invalid rate '10/ms': unknown unit 'ms'$"):
        parse_rate("10/ms")


@pytest.mark.parametrize("text", [b"10/s", None, 10, ["10/s"]])
def test_parse_rate_wants_a_string(text: object) -> None:
    with pytest.raises(TypeError, match=r"^rate must be a string, not "):
        parse_rate(text)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "text",
    [
        chr(0x661) + chr(0x660) + "/s",  # Arabic-Indic digits
        "10/" + chr(0x17F),  # long s, which folds to "s" outside ASCII mode
        "10" + chr(0x2003) + "/s",  # em space
        chr(0xFF11) + "/s",  # fullwidth digit one
        "10/s" + chr(0xA0),  # no-break space
    ],
)
def test_parse_rate_reads_ascii_only(text: str) -> None:
    with pytest.raises(ValueError, match=r"^invalid rate "):
        parse_rate(text)


def test_parse_rate_refuses_a_count_beyond_conversion_and_an_infinite_period() -> None:
    with pytest.raises(ValueError, match=r"count too large$"):
        parse_rate("9" * 5000 + "/s")
    with pytest.raises(ValueError, match=r"positive and finite$"):
        parse_rate("1/" + "9" * 400 + "d")
    assert parse_rate("1" + "0" * 30 + "/s") == (10**30, 1.0)


def test_the_error_message_never_names_the_key() -> None:
    keyed: KeyedRateLimiter[str] = KeyedRateLimiter(1, 60, clock=lambda: 0.0)
    keyed.acquire("secret-token-123")
    with pytest.raises(RateLimitExceeded) as info:
        keyed.acquire("secret-token-123", blocking=False)
    assert info.value.key == "secret-token-123"
    assert "secret" not in str(info.value) and "secret" not in repr(info.value)
