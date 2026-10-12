"""The sliding-window log behind every limiter, without any locking of its own."""

from __future__ import annotations

from collections import deque


class _Window:
    """Timestamps of granted slots, oldest first, possibly reserved in the future.

    The invariant kept by every caller: at any instant ``t`` at most ``calls`` stamps lie
    in ``(t - period, t]``. Stamps never decrease, which is what makes waiters first
    come, first served. The owner guards every method with its own lock.
    """

    __slots__ = ("calls", "hits", "period")

    def __init__(self, calls: int, period: float) -> None:
        self.calls = calls
        self.period = period
        self.hits: deque[float] = deque()

    def clear(self, now: float) -> None:
        """Forget past grants but keep reservations of callers still waiting."""
        hits = self.hits
        while hits and hits[0] <= now:
            hits.popleft()

    def purge(self, now: float) -> None:
        horizon = now - self.period
        hits = self.hits
        while hits and hits[0] <= horizon:
            hits.popleft()

    def ready_at(self, now: float, cost: int) -> float:
        """Return the earliest instant at which ``cost`` slots can be granted."""
        self.purge(now)
        hits = self.hits
        ready = now
        if hits and hits[-1] > ready:
            ready = hits[-1]  # queue behind earlier reservations
        blocker = len(hits) - self.calls + cost - 1
        if blocker >= 0:
            ready = max(ready, hits[blocker] + self.period)
        return ready

    def take(self, at: float, cost: int) -> None:
        self.hits.extend([at] * cost)

    def give_back(self, at: float, cost: int) -> None:
        """Drop ``cost`` stamps equal to ``at``: an abandoned reservation."""
        for _ in range(cost):
            try:
                self.hits.remove(at)
            except ValueError:  # already aged out of the window
                return

    def available(self, now: float) -> int:
        self.purge(now)
        hits = self.hits
        if hits and hits[-1] > now:
            return 0
        return self.calls - len(hits)

    def idle(self, now: float) -> bool:
        self.purge(now)
        return not self.hits
