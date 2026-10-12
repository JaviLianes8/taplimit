"""Edge cases: resets during waits, odd arguments, closed pipes and interruptions."""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from _fakeclock import FakeClock

from taplimit import KeyedRateLimiter, RateLimiter, RateLimitExceeded, parse_rate
from taplimit._cli import main

SRC = str(Path(__file__).resolve().parent.parent / "src")


def test_reset_during_a_wait_keeps_the_limit() -> None:
    clock = FakeClock()
    entered, release = threading.Event(), threading.Event()

    def gated_sleep(_seconds: float) -> None:
        entered.set()
        release.wait(5)

    limiter = RateLimiter(1, 10, clock=clock.time, sleep=gated_sleep)
    limiter.acquire()  # t = 0
    waiter = threading.Thread(target=limiter.acquire)
    waiter.start()
    assert entered.wait(5)  # the waiter holds a reservation for t = 10
    clock.advance(9)
    limiter.reset()
    assert not limiter.try_acquire()  # a newcomer still queues behind the waiter
    assert limiter.retry_after() == pytest.approx(11.0)
    clock.advance(1)
    release.set()
    waiter.join(5)
    assert not waiter.is_alive()


def test_keyed_reset_keeps_reservations_and_drops_idle_keys() -> None:
    clock = FakeClock()
    limiter: KeyedRateLimiter[str] = KeyedRateLimiter(1, 10, clock=clock.time)
    limiter.acquire("a")
    limiter.reset()
    assert len(limiter) == 0
    assert limiter.try_acquire("a")


def test_whole_float_counts_are_accepted_others_rejected() -> None:
    limiter = RateLimiter(2.0, 10)  # type: ignore[arg-type]
    assert limiter.calls == 2
    assert limiter.try_acquire(1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        RateLimiter(2.5, 10)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        limiter.try_acquire("1")  # type: ignore[arg-type]


def test_nan_timeout_and_period_are_rejected() -> None:
    limiter = RateLimiter(1, 10)
    with pytest.raises(ValueError):
        limiter.acquire(timeout=float("nan"))
    with pytest.raises(ValueError):
        RateLimiter(1, float("nan"))


def test_milliseconds_are_not_mistaken_for_minutes() -> None:
    for text in ("10/ms", "10/hs", "10/ds"):
        with pytest.raises(ValueError):
            parse_rate(text)
    assert parse_rate("10/secs") == (10, 1.0)
    assert parse_rate("10/hrs") == (10, 3600.0)


def test_keyed_queries_do_not_track_unknown_keys() -> None:
    limiter: KeyedRateLimiter[int] = KeyedRateLimiter(1, 10)
    for k in range(100):
        assert limiter.available(k) == 1
        assert limiter.retry_after(k) == 0.0
    assert len(limiter) == 0


def test_an_object_with_an_async_call_is_awaited() -> None:
    limiter = RateLimiter(1, 60)

    class Fetcher:
        async def __call__(self, x: int) -> int:
            return x

    guarded = limiter(Fetcher())

    async def run() -> None:
        assert await guarded(3) == 3
        with pytest.raises(RateLimitExceeded):
            await limiter.acquire_async(blocking=False)

    asyncio.run(run())


class _Stream:
    def __init__(self, buffer: Any) -> None:
        self.buffer = buffer


class _InterruptedInput(io.BytesIO):
    def readline(self, size: int | None = -1) -> bytes:
        line = super().readline()
        if not line:
            raise KeyboardInterrupt
        return line


def test_ctrl_c_reports_dropped_lines_and_exits_130(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", _Stream(_InterruptedInput(b"a\nb\nc\n")))
    monkeypatch.setattr(sys, "stdout", _Stream(out))
    assert main(["--drop", "1/h"]) == 130
    assert out.getvalue() == b"a\n"
    assert "dropped 2 line(s)" in capsys.readouterr().err


def test_a_closed_pipe_ends_quietly() -> None:
    env = {**os.environ, "PYTHONPATH": SRC}
    proc = subprocess.Popen(
        [sys.executable, "-m", "taplimit", "100000/s"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        bufsize=0,  # no buffered flush of unsent input when the pipe is gone
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    feeder = threading.Thread(target=_feed, args=(proc.stdin,))
    feeder.start()
    assert proc.stdout.readline() == b"line\n"
    proc.stdout.close()  # the reader goes away, like `| head -1`
    feeder.join(60)
    err = proc.stderr.read()
    assert proc.wait(60) == 0, err
    assert err == b""


def _feed(stdin: Any) -> None:
    try:
        for _ in range(200_000):
            stdin.write(b"line\n")
        stdin.close()
    except OSError:
        pass  # taplimit exited first, which is the point
