"""Context managers, async decorator paths, the give-back lock and two command-line paths."""

from __future__ import annotations

import asyncio
import errno
import io
import sys
from typing import Any

import pytest
from _fakeclock import FakeClock

from taplimit import KeyedRateLimiter, RateLimiter, rate_limit
from taplimit._cli import main
from taplimit._window import _Window


class _Clock(FakeClock):
    def __init__(self) -> None:
        super().__init__()
        self.awaited: list[float] = []

    async def async_sleep(self, seconds: float) -> None:
        self.awaited.append(seconds)
        self.advance(seconds)


def _forbidden(seconds: float) -> None:
    raise AssertionError("a coroutine must never block in the sync sleep")


def test_with_waits_for_a_slot_and_takes_it() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 5, clock=clock.time, sleep=clock.sleep)
    with limiter:
        pass
    with limiter:
        assert clock.slept == [5.0]
    assert limiter.available() == 0


def test_exceptions_inside_with_reach_the_caller() -> None:
    limiter = RateLimiter(5, 1, clock=lambda: 0.0)
    with pytest.raises(KeyError), limiter:
        raise KeyError("inside")

    async def main_() -> None:
        async with limiter:
            raise KeyError("inside async")

    with pytest.raises(KeyError):
        asyncio.run(main_())


def test_a_decorated_coroutine_waits_with_the_async_sleep() -> None:
    clock = _Clock()
    limiter = RateLimiter(1, 5, clock=clock.time, sleep=_forbidden, async_sleep=clock.async_sleep)

    @limiter.limit()
    async def ping() -> str:
        return "pong"

    @rate_limit(1, 5, clock=clock.time, sleep=_forbidden, async_sleep=clock.async_sleep)
    async def pong() -> str:
        return "ping"

    async def main_() -> None:
        assert [await ping(), await ping()] == ["pong", "pong"]
        assert [await pong(), await pong()] == ["ping", "ping"]

    asyncio.run(main_())
    assert clock.awaited == [5.0, 5.0]


def test_a_keyed_coroutine_takes_its_full_cost() -> None:
    clock = _Clock()
    keyed: KeyedRateLimiter[str] = KeyedRateLimiter(
        4, 5, clock=clock.time, sleep=_forbidden, async_sleep=clock.async_sleep
    )

    @keyed.limit(lambda user: user, cost=2)
    async def post(user: str) -> str:
        return user

    async def main_() -> None:
        await post("ann")
        assert keyed.available("ann") == 2
        await post("ann")
        await post("ann")

    asyncio.run(main_())
    assert clock.awaited == [5.0]


def test_giving_back_a_reservation_holds_the_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter(1, 10, clock=lambda: 0.0)
    held: list[bool] = []
    original = _Window.give_back

    def spy(self: _Window, at: float, cost: int) -> None:
        held.append(limiter._lock.locked())
        original(self, at, cost)

    monkeypatch.setattr(_Window, "give_back", spy)
    assert limiter.try_acquire()
    window, ready, _, _ = limiter._reserve(None, 1, True, None)
    limiter._give_back(window, ready, 1)
    assert held == [True]
    assert limiter.retry_after() == 10.0


class _Stream:
    def __init__(self, buffer: Any) -> None:
        self.buffer = buffer


class _BrokenDisk(io.BytesIO):
    def write(self, data: Any) -> int:
        raise OSError(errno.EIO, "input/output error")


def test_dropping_a_single_line_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", _Stream(io.BytesIO(b"a\nb\n")))
    monkeypatch.setattr(sys, "stdout", _Stream(out))
    assert main(["--drop", "1/h"]) == 0
    assert out.getvalue() == b"a\n"
    assert capsys.readouterr().err == "taplimit: dropped 1 line(s)\n"


def test_an_output_error_other_than_a_closed_pipe_is_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdin", _Stream(io.BytesIO(b"a\n")))
    monkeypatch.setattr(sys, "stdout", _Stream(_BrokenDisk()))
    with pytest.raises(OSError) as info:
        main(["5/s"])
    assert info.value.errno == errno.EIO
