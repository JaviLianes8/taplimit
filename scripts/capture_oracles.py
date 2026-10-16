"""Record what two established sliding-log limiters decide on seeded request schedules.

Run in a throwaway virtual environment that has the reference libraries installed:

    python -m pip install limits==5.8.0 pyrate-limiter==4.5.0
    python scripts/capture_oracles.py

It writes ``tests/fixtures/oracles.json``: for every schedule, the decision of
``limits.strategies.MovingWindowRateLimiter`` over ``limits.storage.MemoryStorage`` and of
``pyrate_limiter.InMemoryBucket`` for each request, plus the window statistics of
``limits`` and the wait ``pyrate_limiter`` reports after each refusal. Both libraries are
driven at whole-number instants: ``limits`` through a patched ``time.time`` and
``pyrate_limiter`` through the item timestamps. Nothing of taplimit is imported here.
"""

from __future__ import annotations

import json
import platform
import random
import sys
from datetime import date
from importlib.metadata import version
from pathlib import Path

import limits
import limits.storage.memory as limits_memory
from pyrate_limiter import InMemoryBucket, Rate, RateItem

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "oracles.json"
SEED = 20261016
CASES = 60
EVENTS = 80


class _FakeTime:
    """Stands in for the ``time`` module inside ``limits.storage.memory``."""

    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now


def _schedule(rng: random.Random, calls: int, period: int) -> list[list[int]]:
    t = rng.randint(0, 3) * period
    events = []
    for _ in range(EVENTS):
        gap = rng.choice([0, 0, 1, period - 1, period, period + 1, period // 2])
        t += gap if rng.random() < 0.8 else rng.randint(0, 2 * period)
        cost = 1 if rng.random() < 0.6 else rng.randint(1, calls)
        events.append([t, cost])
    return events


def _run_limits(
    fake: _FakeTime, calls: int, period: int, events: list[list[int]]
) -> dict[str, list[object]]:
    storage = limits.storage.MemoryStorage()
    limiter = limits.strategies.MovingWindowRateLimiter(storage)
    item = limits.RateLimitItemPerSecond(calls, period)
    granted, remaining, reset = [], [], []
    for t, cost in events:
        fake.now = float(t)
        granted.append(limiter.hit(item, "k", cost=cost))
        stats = limiter.get_window_stats(item, "k")
        remaining.append(stats.remaining)
        reset.append(stats.reset_time)
    return {"limits": granted, "limits_remaining": remaining, "limits_reset": reset}


def _run_pyrate(calls: int, period: int, events: list[list[int]]) -> dict[str, list[object]]:
    bucket = InMemoryBucket([Rate(calls, period)])
    granted, waits = [], []
    for t, cost in events:
        item = RateItem("k", t, cost)
        ok = bucket.put(item)
        granted.append(ok)
        waits.append(None if ok else bucket.waiting(item))
    return {"pyrate": granted, "pyrate_wait": waits}


def main() -> int:
    fake = _FakeTime()
    limits_memory.time = fake  # type: ignore[assignment]
    rng = random.Random(SEED)
    cases = []
    for _ in range(CASES):
        calls = rng.choice([1, 2, 3, 5, 8])
        period = rng.choice([7, 60, 250, 1000])
        events = _schedule(rng, calls, period)
        case: dict[str, object] = {"calls": calls, "period": period, "events": events}
        case.update(_run_limits(fake, calls, period, events))
        case.update(_run_pyrate(calls, period, events))
        cases.append(case)
    doc = {
        "captured": date.today().isoformat(),
        "python": platform.python_version(),
        "libraries": {"limits": version("limits"), "pyrate-limiter": version("pyrate-limiter")},
        "seed": SEED,
        "note": "Times and periods are whole numbers in an arbitrary unit.",
        "cases": cases,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, separators=(",", ":")) + "\n"
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(cases)} schedules to {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
