"""The ``taplimit`` command: pass input lines through at most a given rate."""

from __future__ import annotations

import argparse
import errno
import os
import sys
from collections.abc import Sequence
from typing import BinaryIO

from ._limiter import RateLimiter
from ._rate import parse_rate

_EPILOG = """\
examples:
  taplimit 5/s access.log
      replay a log at five lines per second
  tail -f app.log | taplimit 2/s
      follow a busy log without flooding the terminal
  taplimit 30/min urls.txt | xargs -n1 curl -sO
      fetch at most thirty URLs per minute
  journalctl -f | taplimit --drop 10/s
      keep at most ten lines per second, drop the rest

RATE is CALLS/UNIT or CALLS per UNIT with UNIT in s, m, h, d (or sec, min, hour,
day), optionally with a multiplier: 10/s, 100/min, 5/2s, "3 per hour".
Lines are passed through byte for byte.
Exit status: 0 on success (also when the reader closes the pipe), 2 on bad usage,
130 when interrupted with Ctrl-C.
"""

# Writing to a closed pipe raises EPIPE on POSIX and EINVAL on Windows.
_CLOSED_PIPE = (errno.EPIPE, errno.EINVAL)


def _parser() -> argparse.ArgumentParser:
    from . import __version__

    parser = argparse.ArgumentParser(
        prog="taplimit",
        description="Copy lines from FILE (or standard input) to standard output, "
        "at most RATE lines per period, waiting when the rate is reached.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("rate", metavar="RATE", help="the limit, for example 10/s or 100/min")
    parser.add_argument("file", metavar="FILE", nargs="?", help="input file (default: stdin)")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="drop lines over the limit instead of waiting; report the count on stderr",
    )
    parser.add_argument("--version", action="version", version=f"taplimit {__version__}")
    return parser


def pump(
    source: BinaryIO,
    sink: BinaryIO,
    limiter: RateLimiter,
    *,
    drop: bool,
    tally: list[int] | None = None,
) -> int:
    """Copy lines from ``source`` to ``sink`` through ``limiter``; return lines dropped.

    ``tally[0]``, when given, is kept up to date so the count survives an interruption.
    """
    counter = [0] if tally is None else tally
    for line in iter(source.readline, b""):
        if drop:
            if not limiter.try_acquire():
                counter[0] += 1
                continue
        else:
            limiter.acquire()
        sink.write(line)
        sink.flush()
    return counter[0]


def _silence_stdout() -> None:
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stdout.fileno())


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line tool and return its exit status."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        calls, period = parse_rate(args.rate)
    except ValueError as exc:
        parser.error(str(exc))
    limiter = RateLimiter(calls, period)
    tally = [0]
    status = 0
    try:
        if args.file is None:
            pump(sys.stdin.buffer, sys.stdout.buffer, limiter, drop=args.drop, tally=tally)
        else:
            try:
                source = open(args.file, "rb")  # noqa: SIM115
            except OSError as exc:
                parser.error(f"cannot open {args.file}: {exc.strerror}")
            with source:
                pump(source, sys.stdout.buffer, limiter, drop=args.drop, tally=tally)
    except KeyboardInterrupt:
        status = 130
    except OSError as exc:
        if not isinstance(exc, BrokenPipeError) and exc.errno not in _CLOSED_PIPE:
            raise
        # The reader went away (for example `| head`): stop quietly, as cat does.
        _silence_stdout()
    if tally[0]:
        print(f"taplimit: dropped {tally[0]} line(s)", file=sys.stderr)
    return status
