# Improvement round

Ranked list of substantial improvements for this round. Everything is additive: the
0.1.0 API (`rate_limit`, `RateLimiter`, `RateLimitExceeded`, `acquire(blocking=...)`,
`try_acquire()`, decorator and context-manager use) keeps working unchanged.

## Ranked improvements

1. **State the algorithm precisely and make it fair.** taplimit is a sliding-window log:
   at every instant `t`, at most `calls` grants carry a timestamp in `(t - period, t]`.
   Blocking callers now *reserve* their future slot under the lock and then sleep until
   it, so waiters are served first come, first served (in lock order), there is no
   thundering herd of retries, and a later `try_acquire` cannot jump the queue.
2. **Timeouts on blocking acquisition.** `acquire(timeout=...)` waits at most that long.
   When the next slot is further away than the timeout it raises `RateLimitExceeded`
   immediately, carrying the exact `retry_after`, instead of sleeping in vain.
3. **Weighted acquisition.** `cost=n` takes `n` slots at once (a batch request, a large
   upload). A cost above `calls` can never succeed and is rejected with `ValueError`.
4. **asyncio support on the same limiter.** `await limiter.acquire_async(...)`,
   `async with limiter`, and decorating an `async def` all work, so one budget can be
   shared by threads and coroutines. A cancelled waiter gives its reservation back.
5. **Per-key limiters.** `KeyedRateLimiter` keeps one independent window per key (a user,
   a host, an API token), evicts idle keys automatically so memory stays bounded by the
   active keys, and offers `limit(key=...)` to derive the key from the call arguments.
   `rate_limit(..., key=...)` exposes the same thing from the one-line decorator.
6. **Introspection.** `available()`, `retry_after(cost=...)`, `reset()`, read-only
   `calls` / `period`, and a useful `repr`, for dashboards, health checks and back-off.
7. **Richer refusal.** `RateLimitExceeded` keeps `retry_after` and gains `key` (the
   refused key for keyed limiters, else `None`), so handlers can report precisely.
8. **Human rate strings.** `parse_rate("100/min")` returns `(calls, period)`; it accepts
   `s`, `m`, `h`, `d` units in short and long forms and a multiplier such as `5/2s`.
9. **A command-line tool.** `taplimit RATE [FILE]` passes input lines through at most
   RATE, byte for byte. It earns its place: throttling a log replay, a list of URLs fed
   to `xargs`, or a flood of notifications is a common shell need that `pv -L` (bytes,
   not lines) does not cover. `--drop` samples instead of waiting.
10. **Guarantees proven by tests.** A model-based contract over the complete promise with
    an injected clock (exact counts in every window, burst, retry-after, cost, timeout,
    fairness), a real-clock multi-thread stress test whose bound cannot be flaky, and an
    end-to-end test that installs the built wheel into a fresh virtual environment and
    drives the library and the CLI as an outside consumer.
11. **GUIDE.md.** Semantics, guarantees, sharing between threads and coroutines, keyed
    limits, testing with a fake clock, and the CLI, with runnable snippets.

## Considered and deferred

- **A token-bucket mode.** A sliding-window log with `calls` per `period` already gives a
  burst of exactly `calls` and a sustained rate of `calls / period`, which is the shape
  this library promises. A second algorithm with a different parameter pair would blur
  the one-obvious-way design. Memory is `O(calls)` per window, documented in the guide.
- **Cross-process or distributed limits.** Out of scope: taplimit is deliberately
  in-process. Backends belong to heavier libraries.
