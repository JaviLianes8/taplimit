# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-16

The first stable release. From here on the public names, their signatures and defaults,
the error types and the documented behaviour change only with a new major version.

### Stable surface

- `rate_limit(calls, period, *, on_limit="block", timeout=None, key=None, clock, sleep,
  async_sleep)`: the decorator, for plain and `async def` functions.
- `RateLimiter(calls, period, *, clock, sleep, async_sleep)`: `acquire`, `acquire_async`,
  `try_acquire`, `available`, `retry_after`, `reset`, `limit`, use as a decorator and as a
  sync or async context manager, read-only `calls` and `period`.
- `KeyedRateLimiter(calls, period, ...)`: the same per key, with idle keys forgotten, and
  `len()` for the number of tracked keys.
- `RateLimitExceeded(retry_after, key=None)` and `parse_rate(text)`.
- The `taplimit` command (also `python -m taplimit`) and its exit codes 0, 2 and 130.
- The algorithm: a sliding-window log, half open, first come first served; see GUIDE.md.

### Added (since 0.1.0)

- Blocking callers reserve their slot and are served first come, first served; a
  `try_acquire` can no longer jump ahead of a waiter.
- `acquire(timeout=...)` waits at most that long and refuses at once when the slot is
  further away. `cost=n` takes several slots in one step.
- asyncio support: `acquire_async`, `async with limiter`, and decorating `async def`
  functions. A cancelled or interrupted wait gives its reservation back.
- `KeyedRateLimiter` for per-key limits with automatic eviction of idle keys, and
  `rate_limit(..., key=..., timeout=...)`.
- `available()`, `retry_after()`, `reset()`, `limit(...)`, `calls` / `period` and a
  readable `repr` on limiters; `RateLimitExceeded.key`, and the error pickles cleanly.
- `parse_rate("100/min")` turns a human rate string into `(calls, period)`.
- The `taplimit` command throttles lines in a pipeline.
- GUIDE.md states the algorithm, every guarantee and every error; docstrings carry
  examples that run as tests.

### Changed (upgrading from 0.1.0)

- Decorating an `async def` function now takes the slot when the call is awaited, waiting
  with `asyncio.sleep`, instead of blocking the event loop with `time.sleep` when the
  coroutine is created. A coroutine that is never awaited no longer takes a slot.
- `calls` must be an integer or a whole float such as `10.0`: `2.5`, `True`, `Decimal`
  and `Fraction` counts, which 0.1.0 accepted, raise `TypeError` when the limiter is built.
- `period` must be a finite real number of seconds greater than 0: NaN and `inf`,
  which 0.1.0 accepted, raise `ValueError`; `bool`, `Decimal` and strings raise `TypeError`.
  The period is stored as a `float`, so `limiter.period` is `10.0` for `period=10`.
- `RateLimitExceeded`, `RateLimiter` and `KeyedRateLimiter` report `taplimit` as their
  module, so tracebacks and reprs show `taplimit.RateLimitExceeded`.
- Slots taken together are stored together: memory follows the number of acquisitions,
  not their cost, and returning an abandoned reservation is a single step.
- An injected `clock` that returns NaN or an infinity raises `ValueError`; waits longer
  than a day sleep in steps of a day. Error messages show large numbers by their size.
- `rate_limit`'s `on_limit` is typed `Literal["block", "raise"]`.
- `parse_rate` reads ASCII only (no other digits or spaces), quotes at most 40 characters
  of a bad string in its message, and raises `TypeError` for a non-string.
- Python 3.10 or later, as in 0.1.0; classifiers now list 3.10 to 3.14.

## [0.1.0]

- First release: `rate_limit` decorator, `RateLimiter` object, and `RateLimitExceeded`.
- Sliding-window algorithm, thread-safe, zero dependencies.
- Block-or-raise behaviour, with injectable clock and sleep for tests.
