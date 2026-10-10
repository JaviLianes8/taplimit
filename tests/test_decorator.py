"""Behaviour tests for the rate_limit decorator."""

from __future__ import annotations

import pytest
from _fakeclock import FakeClock

from taplimit import RateLimitExceeded, rate_limit


def test_blocks_by_default_until_a_slot_frees() -> None:
    clock = FakeClock()

    @rate_limit(2, 10, clock=clock.time, sleep=clock.sleep)
    def work() -> str:
        return "ok"

    assert work() == "ok"
    assert work() == "ok"
    assert work() == "ok"  # third call waits
    assert clock.slept == [10.0]


def test_raise_mode_raises_instead_of_waiting() -> None:
    clock = FakeClock()

    @rate_limit(1, 10, on_limit="raise", clock=clock.time, sleep=clock.sleep)
    def work() -> str:
        return "ok"

    assert work() == "ok"
    with pytest.raises(RateLimitExceeded):
        work()
    assert clock.slept == []


def test_preserves_arguments_and_return_value() -> None:
    clock = FakeClock()

    @rate_limit(10, 10, clock=clock.time, sleep=clock.sleep)
    def add(a: int, b: int = 0) -> int:
        return a + b

    assert add(2, b=3) == 5


def test_preserves_the_wrapped_name_and_docstring() -> None:
    @rate_limit(1, 1)
    def greet() -> str:
        """Say hello."""
        return "hi"

    assert greet.__name__ == "greet"
    assert greet.__doc__ == "Say hello."


def test_rejects_an_unknown_on_limit_value() -> None:
    with pytest.raises(ValueError):
        rate_limit(1, 10, on_limit="explode")
