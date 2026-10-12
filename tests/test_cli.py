"""The taplimit command: the pump under a fake clock, then the real process."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

from _fakeclock import FakeClock

from taplimit import RateLimiter
from taplimit._cli import pump

SRC = str(Path(__file__).resolve().parent.parent / "src")


def _run(*args: str, stdin: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "PYTHONPATH": SRC}
    return subprocess.run(
        [sys.executable, "-m", "taplimit", *args],
        input=stdin,
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )


def test_pump_waits_to_keep_the_rate() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, 1, clock=clock.time, sleep=clock.sleep)
    sink = io.BytesIO()
    dropped = pump(io.BytesIO(b"a\nb\nc\nd\ne\n"), sink, limiter, drop=False)
    assert sink.getvalue() == b"a\nb\nc\nd\ne\n"
    assert dropped == 0
    assert clock.slept == [1.0, 1.0]


def test_pump_drop_mode_samples_without_waiting() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, 1, clock=clock.time, sleep=clock.sleep)
    sink = io.BytesIO()
    dropped = pump(io.BytesIO(b"1\n2\n3\n4\n"), sink, limiter, drop=True)
    assert sink.getvalue() == b"1\n2\n"
    assert dropped == 2
    assert clock.slept == []


def test_pump_passes_bytes_through_untouched() -> None:
    limiter = RateLimiter(10, 1)
    payload = "café\r\n".encode() + b"\xff\xfe raw\nno newline at end"
    sink = io.BytesIO()
    pump(io.BytesIO(payload), sink, limiter, drop=False)
    assert sink.getvalue() == payload


def test_cli_copies_stdin_at_the_rate() -> None:
    result = _run("1000/s", stdin=b"x\ny\nz\n")
    assert result.returncode == 0
    assert result.stdout.replace(b"\r\n", b"\n") == b"x\ny\nz\n"


def test_cli_reads_a_file_and_reports_drops(tmp_path: Path) -> None:
    source = tmp_path / "in.txt"
    source.write_bytes(b"".join(b"%d\n" % i for i in range(10)))
    result = _run("--drop", "3/h", str(source))
    assert result.returncode == 0
    assert result.stdout.splitlines() == [b"0", b"1", b"2"]
    assert b"dropped 7 line(s)" in result.stderr


def test_cli_rejects_a_bad_rate_with_status_2() -> None:
    result = _run("fast")
    assert result.returncode == 2
    assert b"invalid rate" in result.stderr


def test_cli_rejects_a_missing_file_with_status_2(tmp_path: Path) -> None:
    result = _run("1/s", str(tmp_path / "nope.txt"))
    assert result.returncode == 2
    assert b"cannot open" in result.stderr


def test_cli_help_shows_runnable_examples() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert b"taplimit 5/s access.log" in result.stdout
    assert b"--drop" in result.stdout


def test_cli_version_matches_the_package() -> None:
    import taplimit

    result = _run("--version")
    assert result.stdout.strip() == f"taplimit {taplimit.__version__}".encode()
