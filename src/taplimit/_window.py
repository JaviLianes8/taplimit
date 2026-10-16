"""The sliding-window log behind every limiter, without any locking of its own."""

from __future__ import annotations

import math
from bisect import bisect_right


class _Window:
    """Grant times of slots, oldest first, as runs of slots sharing one instant.

    The invariant kept by every caller: at any instant ``t`` at most ``calls`` slots carry a
    time ``s`` with ``t < s + period`` and ``s <= t``. Times never decrease, which is what makes
    waiters first come, first served. Slots granted at the same instant share one run, so
    memory follows the number of acquisitions, not their cost. A Fenwick tree over the run
    counts finds the n-th slot and returns abandoned reservations in logarithmic time, so a
    long queue of waiters never costs quadratic work. The owner guards every method.
    """

    __slots__ = ("calls", "cleared", "counts", "head", "period", "stamps", "total", "tree")

    def __init__(self, calls: int, period: float) -> None:
        self.calls = calls
        self.period = period
        self.stamps: list[float] = []  # run times, never decreasing
        self.counts: list[int] = []  # slots per run; runs before ``head`` are spent
        self.tree: list[int] = [0]  # 1-based Fenwick tree over ``counts``
        self.head = 0
        self.total = 0
        self.cleared = -math.inf  # the latest instant up to which ``clear`` dropped grants

    def _add(self, index: int, delta: int) -> None:
        tree, i = self.tree, index + 1
        while i < len(tree):
            tree[i] += delta
            i += i & -i

    def _find(self, unit: int) -> int:
        """Return the index of the run that holds live slot ``unit`` (0 is the oldest)."""
        tree, pos = self.tree, 0
        step = 1 << (len(tree) - 1).bit_length()
        while step:
            nxt = pos + step
            if nxt < len(tree) and tree[nxt] <= unit:
                pos, unit = nxt, unit - tree[nxt]
            step >>= 1
        return pos

    def _compact(self) -> None:
        head = self.head
        self.stamps, self.counts, self.head = self.stamps[head:], self.counts[head:], 0
        tree = self.tree = [0, *self.counts]
        for i in range(1, len(tree)):
            parent = i + (i & -i)
            if parent < len(tree):
                tree[parent] += tree[i]

    def _drop(self, now: float, keep: float) -> None:
        stamps, counts, head = self.stamps, self.counts, self.head
        while head < len(stamps) and stamps[head] + keep <= now:
            if counts[head]:
                self._add(head, -counts[head])
                self.total -= counts[head]
                counts[head] = 0
            head += 1
        self.head = head
        if head > 64 and 2 * head > len(stamps):
            self._compact()

    def clear(self, now: float) -> None:
        """Forget past grants but keep reservations of callers still waiting."""
        self._drop(now, 0.0)
        self.cleared = max(self.cleared, now)

    def purge(self, now: float) -> None:
        self._drop(now, self.period)

    def _last(self) -> float:
        return self.stamps[self._find(self.total - 1)] if self.total else -math.inf

    def ready_at(self, now: float, cost: int) -> float:
        """Return the earliest instant at which ``cost`` slots can be granted."""
        self.purge(now)
        ready = max(now, self._last())  # queue behind earlier reservations
        blocker = self.total - self.calls + cost - 1
        if blocker >= 0:
            ready = max(ready, self.stamps[self._find(blocker)] + self.period)
        return ready

    def take(self, at: float, cost: int) -> None:
        stamps = self.stamps
        while len(stamps) > self.head and stamps[-1] > at:
            # Only abandoned reservations (empty runs) can lie later; drop them to keep order.
            stamps.pop()
            self.counts.pop()
            self.tree.pop()
        last = len(stamps) - 1
        if last >= self.head and stamps[last] == at:
            self.counts[last] += cost
            self._add(last, cost)
        else:
            stamps.append(at)
            self.counts.append(cost)
            tree, i = self.tree, len(self.tree)
            value, j, low = cost, i - 1, i - (i & -i)
            while j > low:  # the new node also covers the earlier slots in its range
                value += tree[j]
                j -= j & -j
            tree.append(value)
        self.total += cost

    def give_back(self, at: float, cost: int) -> None:
        """Drop ``cost`` slots granted at ``at``: an abandoned reservation."""
        if at <= self.cleared:
            return  # a reset already dropped it; a newer grant may share the instant
        index = bisect_right(self.stamps, at, self.head) - 1
        if index >= self.head and self.stamps[index] == at:
            taken = min(cost, self.counts[index])
            self.counts[index] -= taken
            self._add(index, -taken)
            self.total -= taken
        # Otherwise the reservation already aged out of the window.

    def available(self, now: float) -> int:
        self.purge(now)
        if self._last() > now:
            return 0
        return self.calls - self.total

    def idle(self, now: float) -> bool:
        self.purge(now)
        return not self.total

    def entries(self) -> int:
        """Return the number of runs that still hold slots."""
        return sum(1 for count in self.counts[self.head :] if count)
