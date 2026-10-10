"""A deterministic clock and sleep pair so tests never wait on real time."""

from __future__ import annotations


class FakeClock:
    """A fake monotonic clock whose ``sleep`` simply advances the clock."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds
