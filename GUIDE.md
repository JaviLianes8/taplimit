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
- **Memory.** One entry per acquisition granted in the last period plus one per waiting
  caller; slots taken together share an entry, so `cost=1_000_000` costs no more than
  `cost=1`. Each operation does constant work on average, plus a walk over the entries that
  is bounded by the number of acquisitions in the window.

A token bucket with capacity `calls` refilling at `calls / period` allows the same burst
but refills continuously; the sliding window is stricter and easier to reason about,
which is why taplimit uses it.

### The boundary instant

The window is half open: a slot granted at `g` counts for every instant up to, but not
including, `g + period`. This is the rule the documentation of `limits` states for its
moving window (a request is allowed once the n-th newest entry "is at least" a period
old). The in-memory implementations of `limits` 5.8.0 and `pyrate-limiter` 4.5.0 instead
count the entry at that exact instant too. The test suite replays 60 seeded schedules
captured from both libraries: taplimit makes every one of their decisions when given a
period half a unit longer on whole-number times (which turns its half-open window into
their closed one), reports the same waits less that half unit, and with the same period
differs only at instants exactly one period after a grant.

### Clocks

`clock` must never go backwards; the default `time.monotonic` does not. Any unit works as
long as `period`, `timeout` and the values `clock` returns use the same one.

## Acquiring

| Call | Slot free | Slot not free |
| --- | --- | --- |
| `acquire()` | returns | waits for it |
| `acquire(timeout=s)` | returns | waits if it comes within `s`, else raises at once |
| `acquire(blocking=False)` | returns | raises `RateLimitExceeded` |
| `try_acquire()` | returns `True` | returns `False` |
| `await acquire_async(...)` | returns | like `acquire`, but awaits |

Every form takes `cost=n` to claim `n` slots in one step (`1 <= n <= calls`).
`timeout=math.inf` waits as long as needed, like no timeout at all.

`RateLimitExceeded.retry_after` is the exact number of seconds until the refused request
would be granted; `retry_after(cost)` and `available()` answer the same questions without
trying. A refused call never consumes a slot. With a timeout, taplimit computes the wait
first and refuses straight away when it is too long, rather than sleeping in vain.

## Arguments and errors

Arguments are checked when they are given: a limiter's when it is built, a decorator's
when the decorator is created (`limit(...)`, `rate_limit(...)`), and those of `acquire`,
`try_acquire` and `retry_after` on every call.

| Argument | Accepted | Otherwise |
| --- | --- | --- |
| `calls`, `cost` | an integer (`int`, or anything with `__index__`) or a whole `float` such as `10.0`; `calls >= 1`, `1 <= cost <= calls` | `TypeError` for other types, `bool` included; `ValueError` for values out of range |
| `period` | a real number of seconds (`int`, `float`, `Fraction`), finite and greater than 0; stored as a `float` | `TypeError` for other types, `bool` and `Decimal` included; `ValueError` for 0, negatives, NaN and infinities |
| `timeout` | `None` or a real number of seconds, 0 or more (`math.inf` included), only with blocking | `TypeError` for other types; `ValueError` for negatives, NaN, or a timeout without blocking |
| `on_limit` | `"block"` or `"raise"`; a timeout only with `"block"` | `ValueError` |
| rate strings | see [Rate strings](#rate-strings) | `ValueError`, or `TypeError` for a non-string |

`RateLimitExceeded` is the only error a well-formed call raises, when it chose not to wait
(`blocking=False`, `on_limit="raise"`) or the wait would exceed `timeout`. It subclasses
`Exception`, carries `retry_after` and `key`, and pickles with both. Messages are short and
never echo a key; a rate string is quoted to at most 40 characters and a type name to 40.

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

The key function receives exactly the decorated call's arguments, and with `limit` type
checkers verify that its parameters match the function's. `rate_limit(..., key=...)`
builds the same thing in one line; there the decorated function keeps its exact signature
but the key's parameters are not checked against it. A key that is not callable is a
`TypeError` when the decorator is created. `reset(key)` forgets one key and `reset()` every key,
so a key that is literally `None` can only be reset together with the others.

## Rate strings

`parse_rate` accepts `CALLS/UNIT` or `CALLS per UNIT`; the unit is `s`, `m`, `h` or `d`
(also `sec`, `second`, `min`, `minute`, `hr`, `hour`, `day` and plurals) and may carry a
multiplier. Only ASCII digits, letters and spaces are read, case does not matter, and
`ms` is refused rather than read as minutes. `per` must not touch a letter, so `10pers` is
refused while `5per2s` reads as five per two seconds:

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
