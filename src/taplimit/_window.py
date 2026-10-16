"""The sliding-window log behind every limiter, without any locking of its own."""

from __future__ import annotations

from collections import deque


class _Run:
    """``count`` slots granted (or reserved) at the same instant ``stamp``."""

    __slots__ = ("count", "stamp")

    def __init__(self, stamp: float, count: int) -> None:
        self.stamp = stamp
        self.count = count


class _Window:
    """Grant times of slots, oldest first, as runs of slots sharing one instant.

    The invariant kept by every caller: at any instant ``t`` at most ``calls`` slots carry a
    time in ``(t - period, t]``. Times never decrease, which is what makes waiters first come,
    first served. Slots granted at the same instant share one run, so memory follows the
    number of acquisitions, not their cost. The owner guards every method with its own lock.
    """

    __slots__ = ("calls", "period", "runs", "total")

    def __init__(self, calls: int, period: float) -> None:
        self.calls = calls
        self.period = period
        self.runs: deque[_Run] = deque()
        self.total = 0

    def _drop_until(self, limit: float) -> None:
        runs = self.runs
        while runs and runs[0].stamp <= limit:
            self.total -= runs.popleft().count

    def clear(self, now: float) -> None:
        """Forget past grants but keep reservations of callers still waiting."""
        self._drop_until(now)

    def purge(self, now: float) -> None:
        self._drop_until(now - self.period)

    def _unit_time(self, index: int) -> float:
        """Return the time of the slot at ``index`` (0 is the oldest) without expanding runs."""
        runs = self.runs
        if index < self.total - index:
            for run in runs:
                index -= run.count
                if index < 0:
                    return run.stamp
        else:
            index = self.total - 1 - index  # position counted from the newest slot
            for run in reversed(runs):
                index -= run.count
                if index < 0:
                    return run.stamp
        raise IndexError(index)  # pragma: no cover - callers pass an index below total

    def ready_at(self, now: float, cost: int) -> float:
        """Return the earliest instant at which ``cost`` slots can be granted."""
        self.purge(now)
        runs = self.runs
        ready = now
        if runs and runs[-1].stamp > ready:
            ready = runs[-1].stamp  # queue behind earlier reservations
        blocker = self.total - self.calls + cost - 1
        if blocker >= 0:
            ready = max(ready, self._unit_time(blocker) + self.period)
        return ready

    def take(self, at: float, cost: int) -> None:
        runs = self.runs
        if runs and runs[-1].stamp == at:
            runs[-1].count += cost
        else:
            runs.append(_Run(at, cost))
        self.total += cost

    def give_back(self, at: float, cost: int) -> None:
        """Drop ``cost`` slots granted at ``at``: an abandoned reservation."""
        # Equal times are always adjacent and merged by ``take``, so one run holds them all.
        runs = self.runs
        for offset, run in enumerate(reversed(runs)):
            if run.stamp == at:
                taken = min(cost, run.count)
                run.count -= taken
                self.total -= taken
                if not run.count:
                    del runs[len(runs) - 1 - offset]
                return
        # Not found: the reservation already aged out of the window.

    def available(self, now: float) -> int:
        self.purge(now)
        runs = self.runs
        if runs and runs[-1].stamp > now:
            return 0
        return self.calls - self.total

    def idle(self, now: float) -> bool:
        self.purge(now)
        return not self.runs
