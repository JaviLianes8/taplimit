"""Seeded fuzzing of parse_rate: generated meanings, random text and long hostile input."""

from __future__ import annotations

import math
import random

import pytest

from taplimit import parse_rate

UNITS = ["s", "sec", "secs", "second", "seconds", "m", "min", "mins", "minute", "minutes",
         "h", "hr", "hrs", "hour", "hours", "d", "day", "days"]  # fmt: skip
SECONDS = {"s": 1, "sec": 1, "second": 1, "m": 60, "min": 60, "minute": 60, "h": 3600,
           "hr": 3600, "hour": 3600, "d": 86400, "day": 86400}  # fmt: skip


@pytest.mark.parametrize("seed", range(20))
def test_generated_rate_strings_parse_to_their_meaning(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(200):
        calls, mult = rng.randint(1, 10**6), rng.choice(["", "2", "15", "0.5", ".25", "1.75"])
        unit = rng.choice(UNITS)
        sep = rng.choice(["/", " / ", "per ", " per ", " PER ", "Per "])
        cased = "".join(c.upper() if rng.random() < 0.3 else c for c in unit)
        lead, tail = rng.choice(["", " ", chr(9)]), rng.choice(["", " ", chr(10)])
        text = f"{lead}{calls}{sep}{mult}{cased}{tail}"
        base = SECONDS.get(unit, SECONDS.get(unit[:-1], 0))
        assert parse_rate(text) == (calls, float(mult or 1) * base), text


@pytest.mark.parametrize("seed", range(20))
def test_random_text_never_breaks_parse_rate(seed: int) -> None:
    rng = random.Random(seed)
    alphabet = "0123456789/. pPeErRsSmMhHdD\t\n" + chr(0x661) + chr(0xFF11) + chr(0x17F)
    for _ in range(500):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        try:
            calls, period = parse_rate(text)
        except ValueError as exc:
            assert str(exc).startswith("invalid rate ") and len(str(exc)) < 140
        else:
            assert calls >= 1 and 0 < period < math.inf


@pytest.mark.parametrize(
    "text",
    ["1" * 200_000 + "x", "1/" + "1" * 200_000 + "!", "1/s" + " " * 200_000 + "x",
     " " * 200_000 + "1/", "1/" + "s" * 200_000 + "1", "1" + " " * 200_000 + "/"],
    ids=[f"hostile{i}" for i in range(6)],
)  # fmt: skip
def test_long_hostile_strings_fail_fast(text: str) -> None:
    with pytest.raises(ValueError) as info:
        parse_rate(text)
    assert len(str(info.value)) < 140


@pytest.mark.parametrize(
    "text", ["10pers", "10persec", "10 pers", "10/pers", "5 super s", "5/1.s", "5/1. min", "5/.s"]
)
def test_per_must_stand_alone_and_a_multiplier_needs_digits(text: str) -> None:
    with pytest.raises(ValueError):
        parse_rate(text)


def test_per_may_touch_digits() -> None:
    assert parse_rate("5per2s") == (5, 2.0)
    assert parse_rate("10 PER minute") == (10, 60.0)
