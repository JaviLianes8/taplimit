# taplimit guide

This guide states exactly what taplimit promises and shows how to use each part.

## The algorithm

taplimit keeps a **sliding-window log**: the grant time of every slot handed out in the
last `period` seconds. Its one invariant is:

> At every instant `t`, at most `calls` slots have a grant time in `(t - period, t]`.

Consequences:

- **Burst.** Up to `calls` acquisitions succeed at once on an idle limiter.
- **Sustained rate.** After the burst, slots free one by one, each exactly `period`
  seconds after the call that took it, so the long-run rate is `calls / period`.
- **No boundary effect.** Unlike a fixed window that resets every minute, a burst at the
  end of one window cannot be followed by another at the start of the next.
- **Memory.** One float per slot granted in the last period plus one per slot reserved
  by a waiting caller, so `O(calls + waiters)` per window.

A token bucket with capacity `calls` refilling at `calls / period` allows the same burst
but refills continuously; the sliding window is stricter and easier to reason about,
which is why taplimit uses it.

## Acquiring

| Call | Slot free | Slot not free |
| --- | --- | --- |
| `acquire()` | returns | waits for it |
| `acquire(timeout=s)` | returns | waits if it comes within `s`, else raises at once |
| `acquire(blocking=False)` | returns | raises `RateLimitExceeded` |
| `try_acquire()` | returns `True` | returns `False` |
| `await acquire_async(...)` | returns | like `acquire`, but awaits |

Every form takes `cost=n` to claim `n` slots in one step (`1 <= n <= calls`).

`RateLimitExceeded.retry_after` is the exact number of seconds until the refused request
would be granted; `retry_after(cost)` and `available()` answer the same questions without
trying. A refused call never consumes a slot. With a timeout, taplimit computes the wait
first and refuses straight away when it is too long, rather than sleeping in vain.

## Fairness and thread safety

All bookkeeping happens under one lock and never while waiting. A caller that must wait
**reserves** its future slot under the lock and then sleeps until that instant, so:

- waiters are served first come, first served (in the order they took the lock);
- there is no thundering herd: each waiter wakes once, at its own time;
- a `try_acquire` cannot steal a slot already reserved by a waiter.

If a wait is interrupted (an exception in `sleep`, `KeyboardInterrupt`, or cancellation
of a coroutine), the reservation is given back. `reset()` forgets past grants but keeps
the slots reserved by callers still waiting, so newcomers queue behind them and the
limit holds across a reset.

## Threads and coroutines together

One `RateLimiter` can serve both: threads call `acquire`, coroutines call
`acquire_async` or use `async with limiter`. Decorating an `async def` makes each call
await its slot; so does decorating an object whose class defines `async def __call__`.
The lock is held only for a few operations, so it never stalls the
event loop.

```python
import asyncio
from taplimit import RateLimiter

limiter = RateLimiter(calls=3, period=1)


@limiter
async def fetch(n: int) -> int:
    return n


async def main() -> None:
    print(await asyncio.gather(*(fetch(n) for n in range(6))))  # takes about a second


asyncio.run(main())
```

## Per-key limits

`KeyedRateLimiter` keeps an independent window per key. Keys that have been idle for a
full period are dropped during a sweep that runs at most once per period, so memory
follows the active keys. Methods take the key first:

```python
from taplimit import KeyedRateLimiter, RateLimitExceeded

limits: KeyedRateLimiter[str] = KeyedRateLimiter(calls=3, period=60)


@limits.limit(key=lambda user, text: user, blocking=False)
def post(user: str, text: str) -> None: ...


try:
    post("alice", "hello")
except RateLimitExceeded as exc:
    print(f"{exc.key} must wait {exc.retry_after:.0f}s")
```

The key function receives exactly the decorated call's arguments, and its parameters
must match the function's so that type checkers can verify it. `rate_limit(..., key=...)`
builds the same thing in one line.

## Rate strings

`parse_rate` accepts `CALLS/UNIT` or `CALLS per UNIT`; the unit is `s`, `m`, `h` or `d`
(also `sec`, `min`, `hour`, `day` and plurals) and may carry a multiplier:

```python
from taplimit import parse_rate

assert parse_rate("100/min") == (100, 60.0)
assert parse_rate("5/2s") == (5, 2.0)
assert parse_rate("3 per hour") == (3, 3600.0)
```

## Testing with a fake clock

Every limiter accepts `clock`, `sleep` and `async_sleep`. A fake `sleep` that advances a
fake clock makes tests instant and exact:

```python
from taplimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


clock = FakeClock()
limiter = RateLimiter(2, 10, clock=clock.time, sleep=clock.sleep)
for _ in range(3):
    limiter.acquire()
assert clock.now == 10.0
```

## The command-line tool

`taplimit RATE [FILE]` copies lines from FILE or standard input to standard output at
most RATE lines per period, byte for byte and flushed line by line. `--drop` discards
lines over the limit instead of waiting and reports how many on standard error, also
when stopped with Ctrl-C. It exits with 0 on success, 2 on bad usage and 130 when
interrupted; a closed pipe (`| head`) ends it quietly. `python -m taplimit` runs the
same tool.
