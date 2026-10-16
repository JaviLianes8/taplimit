"""The public surface of 1.0.0: names, signatures, defaults and the module they report."""

from __future__ import annotations

import importlib.resources
import inspect
import pickle
import time
from typing import Any

import pytest

import taplimit
from taplimit import KeyedRateLimiter, RateLimiter, RateLimitExceeded

PUBLIC_API: list[str] = [
    "KeyedRateLimiter",
    "RateLimitExceeded",
    "RateLimiter",
    "parse_rate",
    "rate_limit",
]

KW = inspect.Parameter.KEYWORD_ONLY
POS = inspect.Parameter.POSITIONAL_OR_KEYWORD
EMPTY = inspect.Parameter.empty
Spec = list[tuple[str, Any, object]]
INJECT: Spec = [("clock", KW, time.monotonic), ("sleep", KW, time.sleep), ("async_sleep", KW, None)]
ACQUIRE: Spec = [("blocking", KW, True), ("timeout", KW, None), ("cost", KW, 1)]
SIGNATURES: dict[str, Spec] = {
    "RateLimiter": [("calls", POS, EMPTY), ("period", POS, EMPTY), *INJECT],
    "KeyedRateLimiter": [("calls", POS, EMPTY), ("period", POS, EMPTY), *INJECT],
    "RateLimitExceeded": [("retry_after", POS, EMPTY), ("key", POS, None)],
    "parse_rate": [("text", POS, EMPTY)],
    "rate_limit": [
        ("calls", POS, EMPTY),
        ("period", POS, EMPTY),
        ("on_limit", KW, "block"),
        ("timeout", KW, None),
        ("key", KW, None),
        *INJECT,
    ],
    "RateLimiter.acquire": ACQUIRE,
    "RateLimiter.acquire_async": ACQUIRE,
    "RateLimiter.limit": ACQUIRE,
    "RateLimiter.try_acquire": [("cost", POS, 1)],
    "RateLimiter.available": [],
    "RateLimiter.retry_after": [("cost", POS, 1)],
    "RateLimiter.reset": [],
    "RateLimiter.__call__": [("func", POS, EMPTY)],
    "KeyedRateLimiter.acquire": [("key", POS, EMPTY), *ACQUIRE],
    "KeyedRateLimiter.acquire_async": [("key", POS, EMPTY), *ACQUIRE],
    "KeyedRateLimiter.limit": [("key", POS, EMPTY), *ACQUIRE],
    "KeyedRateLimiter.try_acquire": [("key", POS, EMPTY), ("cost", POS, 1)],
    "KeyedRateLimiter.available": [("key", POS, EMPTY)],
    "KeyedRateLimiter.retry_after": [("key", POS, EMPTY), ("cost", POS, 1)],
    "KeyedRateLimiter.reset": [("key", POS, None)],
}


def test_all_lists_exactly_the_public_api() -> None:
    assert sorted(taplimit.__all__) == sorted(PUBLIC_API)
    public = {n for n in dir(taplimit) if not n.startswith("_")}
    assert public - set(PUBLIC_API) <= {"annotations"}


def test_every_exported_name_resolves() -> None:
    for name in taplimit.__all__:
        assert hasattr(taplimit, name)


def test_version_is_1_0_0() -> None:
    assert taplimit.__version__ == "1.0.0"


def test_the_package_ships_type_information() -> None:
    assert importlib.resources.files("taplimit").joinpath("py.typed").is_file()


@pytest.mark.parametrize("name", sorted(SIGNATURES))
def test_signatures_are_frozen(name: str) -> None:
    target: Any = taplimit
    for part in name.split("."):
        target = getattr(target, part)
    params = [
        (p.name, p.kind, p.default)
        for p in inspect.signature(target).parameters.values()
        if p.name != "self"
    ]
    assert params == SIGNATURES[name]


@pytest.mark.parametrize("name", PUBLIC_API)
def test_every_public_name_documents_a_runnable_example(name: str) -> None:
    doc = getattr(taplimit, name).__doc__
    assert doc and ">>> " in doc


def test_classes_report_the_package_as_their_module() -> None:
    for cls in (KeyedRateLimiter, RateLimitExceeded, RateLimiter):
        assert cls.__module__ == "taplimit"
    assert repr(RateLimiter(2, 1)) == "RateLimiter(calls=2, period=1.0)"


def test_the_error_is_an_exception_with_its_fields_and_pickles() -> None:
    exc = RateLimitExceeded(1.5, key=("user", 7))
    assert isinstance(exc, Exception) and not isinstance(exc, ValueError)
    assert (exc.retry_after, exc.key) == (1.5, ("user", 7))
    assert str(exc) == "rate limit exceeded, retry after 1.500s"
    copy = pickle.loads(pickle.dumps(exc))
    assert type(copy) is RateLimitExceeded
    assert (copy.retry_after, copy.key, str(copy)) == (1.5, ("user", 7), str(exc))
    assert RateLimitExceeded(2).key is None


def test_properties_are_read_only() -> None:
    limiter = RateLimiter(3, 2)
    assert (limiter.calls, limiter.period) == (3, 2.0)
    with pytest.raises(AttributeError):
        limiter.calls = 4  # type: ignore[misc]
    with pytest.raises(AttributeError):
        limiter.period = 1.0  # type: ignore[misc]
