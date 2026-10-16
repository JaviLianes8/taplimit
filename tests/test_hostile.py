"""Hostile clocks, rounding, huge numbers and missing streams: documented errors, never damage."""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest
from _fakeclock import FakeClock

from taplimit import KeyedRateLimiter, RateLimiter, RateLimitExceeded
from taplimit._cli import main

SRC = str(Path(__file__).resolve().parent.parent / "src")


def test_rounding_never_lets_a_freed_slot_count_twice() -> None:
    now = [0.300000001]
    limiter = RateLimiter(1, 1.0, clock=lambda: now[0])
    assert limiter.try_acquire()
    now[0] += 1.0  # the slot frees exactly here, though now - 1.0 rounds below the grant
    assert limiter.retry_after() == 0.0
    assert limiter.try_acquire()
    assert limiter.available() == 0
    assert not limiter.try_acquire()


@pytest.mark.parametrize("reading", [math.nan, math.inf, -math.inf])
def test_a_non_finite_clock_reading_is_refused(reading: float) -> None:
    now = [0.0]
    limiter = RateLimiter(2, 1, clock=lambda: now[0])
    assert limiter.try_acquire()
    now[0] = reading
    for call in (limiter.try_acquire, limiter.available, limiter.retry_after, limiter.reset):
        with pytest.raises(ValueError, match=r"^the clock returned .*; it must return finite"):
            call()
    now[0] = 0.5
    assert limiter.available() == 1  # nothing was recorded at the bad reading


def test_keys_are_still_evicted_after_the_clock_steps_back() -> None:
    now = [1000.0]
    keyed: KeyedRateLimiter[int] = KeyedRateLimiter(1, 1.0, clock=lambda: now[0])
    keyed.acquire(-1)
    now[0] = 0.0
    for key in range(500):
        now[0] += 0.5
        keyed.acquire(key)
    assert len(keyed) <= 4


def test_waits_longer_than_a_day_sleep_in_steps() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 3 * 86400.0, clock=clock.time, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire()
    assert clock.slept == [86400.0, 86400.0, 86400.0]


def test_huge_numbers_keep_messages_short() -> None:
    limiter = RateLimiter(10**30, 1, clock=lambda: 0.0)
    with pytest.raises(ValueError) as info:
        limiter.try_acquire(10**5000)
    assert str(info.value) == "cost a 16610-bit number exceeds calls (a 100-bit number)"
    with pytest.raises(ValueError, match=r"^cost 4 exceeds calls \(3\)$"):
        RateLimiter(3, 1).try_acquire(4)
    assert str(RateLimitExceeded(1e300)) == "rate limit exceeded, retry after 1e+300s"
    assert (
        str(RateLimitExceeded(999_999_999.0)) == "rate limit exceeded, retry after 999999999.000s"
    )


def test_the_command_refuses_a_missing_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", None)
    with pytest.raises(SystemExit) as info:
        main(["5/s"])
    assert info.value.code == 2


def test_the_command_shortens_a_long_file_name(tmp_path: Path) -> None:
    name = str(tmp_path / ("x" * 120))
    result = subprocess.run(
        [sys.executable, "-m", "taplimit", "5/s", name],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": SRC, "SYSTEMROOT": "C:\\Windows"},
        timeout=60,
        check=False,
    )
    assert result.returncode == 2
    assert f"cannot open {name[:40]}...: " in result.stderr
    assert "x" * 100 not in result.stderr
