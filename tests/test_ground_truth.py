"""taplimit against established sliding-log limiters and their published documentation.

``fixtures/oracles.json`` holds real program output: the decisions of ``limits`` 5.8.0
(moving window, memory storage) and ``pyrate-limiter`` 4.5.0 (in-memory bucket) on 60
seeded schedules, captured by ``scripts/capture_oracles.py``. Both libraries keep a request
for the closed window ``[t - period, t]``; taplimit keeps it for ``(t - period, t]``. On
whole-number instants a half-open window of ``period + 0.5`` is exactly a closed window of
``period``, so that is how the decisions are compared. When the reference libraries are
installed, a fresh schedule is also run through them live.
"""

from __future__ import annotations

import importlib.util
import json
import random
import re
from pathlib import Path
from typing import Any

import pytest

from taplimit import RateLimiter, RateLimitExceeded

HERE = Path(__file__).resolve().parent
ORACLES = json.loads((HERE / "fixtures" / "oracles.json").read_text("utf-8"))
CASES: list[dict[str, Any]] = ORACLES["cases"]
DOC = HERE / "sources" / "limits-5.8.0-strategies.rst"

# The moving-window example of the limits documentation, 10 requests per minute, as
# (second, requests, allowed). Source:
# https://raw.githubusercontent.com/alisaifee/limits/cc5eafcc45488d9995d738e4de498e6d74dc6e9c/doc/source/strategies.rst
DOC_EXAMPLE = [
    (10, 1, True),
    (20, 2, True),
    (30, 4, True),
    (50, 3, True),
    (71, 1, True),
    (72, 1, False),
]


def _limiter(calls: int, period: float) -> tuple[RateLimiter, list[float]]:
    now = [0.0]
    return RateLimiter(calls, period, clock=lambda: now[0]), now


def _decisions(case: dict[str, Any], shift: float) -> list[bool]:
    limiter, now = _limiter(case["calls"], case["period"] + shift)
    out = []
    for t, cost in case["events"]:
        now[0] = t
        out.append(limiter.try_acquire(cost))
    return out


def test_the_fixture_records_where_it_came_from() -> None:
    assert ORACLES["libraries"] == {"limits": "5.8.0", "pyrate-limiter": "4.5.0"}
    assert len(CASES) == 60
    assert sum(case["limits"].count(False) for case in CASES) > 1000


@pytest.mark.parametrize("index", range(len(CASES)))
def test_decisions_equal_both_reference_limiters(index: int) -> None:
    case = CASES[index]
    assert case["limits"] == case["pyrate"]
    assert _decisions(case, 0.5) == case["limits"]


@pytest.mark.parametrize("index", range(len(CASES)))
def test_reported_waits_equal_pyrate_limiter(index: int) -> None:
    case = CASES[index]
    limiter, now = _limiter(case["calls"], case["period"] + 0.5)
    for (t, cost), wait in zip(case["events"], case["pyrate_wait"], strict=True):
        now[0] = t
        if wait is None:
            limiter.acquire(blocking=False, cost=cost)
            continue
        # pyrate-limiter adds one unit to step past its inclusive bound; taplimit adds 0.5.
        assert limiter.retry_after(cost) + 0.5 == wait
        with pytest.raises(RateLimitExceeded) as info:
            limiter.acquire(blocking=False, cost=cost)
        assert info.value.retry_after + 0.5 == wait


@pytest.mark.parametrize("index", range(len(CASES)))
def test_window_statistics_equal_limits(index: int) -> None:
    # limits counts its statistics over (t - period, t], taplimit's own window: replaying the
    # grants limits made, taplimit must accept each one and report the same numbers.
    case = CASES[index]
    limiter, now = _limiter(case["calls"], case["period"])
    rows = zip(
        case["events"], case["limits"], case["limits_remaining"], case["limits_reset"], strict=True
    )
    for (t, cost), granted, remaining, reset in rows:
        now[0] = t
        if granted:
            assert limiter.try_acquire(cost)
        assert limiter.available() == remaining
        if remaining == 0:
            assert limiter.retry_after() + t == reset


@pytest.mark.parametrize("index", range(len(CASES)))
def test_taplimit_differs_only_at_the_exact_boundary(index: int) -> None:
    case = CASES[index]
    ours, theirs = _decisions(case, 0.0), case["limits"]
    if ours == theirs:
        return
    first = next(i for i, (a, b) in enumerate(zip(ours, theirs, strict=True)) if a != b)
    t = case["events"][first][0]
    granted = [e[0] for e, ok in zip(case["events"][:first], theirs[:first], strict=True) if ok]
    assert ours[first] and not theirs[first]
    assert t - case["period"] in granted  # a slot exactly one period old: free in taplimit


def test_the_documented_example_replays_exactly() -> None:
    limiter, now = _limiter(10, 60)
    for second, requests, allowed in DOC_EXAMPLE:
        now[0] = second
        assert [limiter.try_acquire() for _ in range(requests)] == [allowed] * requests


def test_an_entry_exactly_one_period_old_has_expired() -> None:
    # Hand-derived from the documented rule: a request is allowed when the n-th newest entry
    # "is at least 60 seconds old".
    limiter, now = _limiter(10, 60)
    assert all(limiter.try_acquire() for _ in range(10))
    now[0] = 59.999
    assert not limiter.try_acquire()
    now[0] = 60
    assert limiter.try_acquire()


def test_the_fetched_documentation_states_the_same_example() -> None:
    if not DOC.is_file():
        pytest.skip("run scripts/fetch_sources.py to fetch the documentation")
    text = DOC.read_text("utf-8")
    section = text[text.index("Moving Window\n") :]
    bullets = " ".join(section.split("Sliding Window Counter")[0].split()).split("- At ")
    found = []
    for bullet in bullets[1:]:
        m = re.match(r"\*\*00:(\d\d):(\d\d)\*\*, (?:a|the) client sends (\d+) request", bullet)
        assert m is not None, bullet
        verdict = re.search(r"(allowed|rejected)", bullet)
        assert verdict is not None
        second = int(m[1]) * 60 + int(m[2])
        found.append((second, int(m[3]), verdict[1] == "allowed"))
    assert found == DOC_EXAMPLE
    assert "at least\n60 seconds old" in section or "at least 60 seconds old" in section


def _live_module() -> Any:
    pytest.importorskip("limits")
    pytest.importorskip("pyrate_limiter")
    path = HERE.parent / "scripts" / "capture_oracles.py"
    spec = importlib.util.spec_from_file_location("capture_oracles", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("seed", range(5))
def test_live_reference_limiters_agree_on_fresh_schedules(
    seed: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _live_module()
    fake = capture._FakeTime()
    monkeypatch.setattr(capture.limits_memory, "time", fake)
    rng = random.Random(seed)
    calls, period = rng.choice([1, 2, 4, 9]), rng.choice([5, 30, 600])
    case: dict[str, Any] = {"calls": calls, "period": period}
    case["events"] = capture._schedule(rng, calls, period)
    case.update(capture._run_limits(fake, calls, period, case["events"]))
    case.update(capture._run_pyrate(calls, period, case["events"]))
    assert case["limits"] == case["pyrate"] == _decisions(case, 0.5)
