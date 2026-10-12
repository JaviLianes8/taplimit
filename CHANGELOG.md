# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0]

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
- The `taplimit` command (also `python -m taplimit`) throttles lines in a pipeline.
- GUIDE.md states the algorithm and every guarantee.

## [0.1.0]

- First release: `rate_limit` decorator, `RateLimiter` object, and `RateLimitExceeded`.
- Sliding-window algorithm, thread-safe, zero dependencies.
- Block-or-raise behaviour, with injectable clock and sleep for tests.
