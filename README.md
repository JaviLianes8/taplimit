# taplimit

Small, typed, thread-safe in-process rate limiter: N calls per period, block or raise,
sync or async, globally or per key.

You call an API that allows 15 requests a minute, a mail server that wants a pause between
messages, or a scraper that must stay polite. taplimit keeps one process under that rate with
one decorator, or a limiter object you share between functions, threads and coroutines.
It has no dependencies, its clock and sleep are injectable so tests never wait, and a small
command-line tool throttles lines in a shell pipeline.

## Install

```
pip install taplimit
```

## Quick start

Cap a function at N calls per period. By default a call over the limit waits until a slot
frees:

```python
from taplimit import rate_limit


@rate_limit(calls=15, period=60)
def call_api() -> str:
    return "ok"
```

Prefer to fail fast, or to wait only so long? Ask it to raise, or give a timeout:

```python
from taplimit import RateLimitExceeded, rate_limit


@rate_limit(calls=15, period=60, on_limit="raise")
def call_api() -> str:
    return "ok"


@rate_limit(calls=15, period=60, timeout=5)  # waits up to 5 s, then raises
def call_other_api() -> str:
    return "ok"


try:
    call_api()
except RateLimitExceeded as exc:
    print(f"slow down, retry in {exc.retry_after:.1f}s")
```

`async def` functions work the same way, waiting with `await` instead of blocking:

```python
@rate_limit(calls=10, period=1)
async def fetch(url: str) -> str:
    return url
```

Limit each user, host or token separately with `key`, which receives the call's arguments:

```python
@rate_limit(calls=5, period=60, on_limit="raise", key=lambda user, message: user)
def send(user: str, message: str) -> None:
    print(f"to {user}: {message}")
```

### The limiter object

Share one budget across several functions, threads and coroutines, or control slots by
hand. A `RateLimiter` is a decorator, a context manager (sync and async), and exposes
`acquire`, `acquire_async` and `try_acquire`:

```python
from taplimit import RateLimiter

limiter = RateLimiter(calls=100, period=60)


@limiter
def read() -> None: ...


@limiter
def write() -> None: ...  # read and write draw on the same 100-per-minute budget


def do_work() -> None: ...


with limiter:  # guard a block of code
    do_work()

if limiter.try_acquire():  # never blocks; returns False when full
    do_work()

limiter.acquire(cost=10, timeout=2.5)  # take ten slots, wait at most 2.5 s
print(limiter.available(), limiter.retry_after())  # 88 0.0
```

`KeyedRateLimiter` gives every key its own window and forgets idle keys on its own:

```python
from taplimit import KeyedRateLimiter

per_host: KeyedRateLimiter[str] = KeyedRateLimiter(calls=2, period=1)
per_host.acquire("example.com")
```

`parse_rate` turns a human string into arguments: `RateLimiter(*parse_rate("100/min"))`.

### Testing without real time

`clock` (returns seconds), `sleep` (waits seconds) and `async_sleep` (awaits seconds) are
injectable, so a limiter runs instantly under a fake clock:

```python
now = [0.0]


def fake_sleep(seconds: float) -> None:
    now[0] += seconds


limiter = RateLimiter(calls=1, period=10, clock=lambda: now[0], sleep=fake_sleep)
limiter.acquire()
limiter.acquire()  # "waits" ten seconds without sleeping
assert now[0] == 10.0
```

## Command line

```
taplimit 5/s access.log                  # replay a log at five lines per second
tail -f app.log | taplimit 2/s           # follow a busy log without flooding
taplimit 30/min urls.txt | xargs -n1 curl -sO
journalctl -f | taplimit --drop 10/s     # keep ten lines per second, drop the rest
```

Lines pass through byte for byte. `taplimit --help` lists every option.

## How it limits

taplimit keeps a **sliding-window log**: at every instant `t`, at most `calls` slots have a
grant time in `(t - period, t]`. A slot frees exactly `period` seconds after the call that
took it, so a burst of up to `calls` is allowed at once and the sustained rate is
`calls / period`; nothing carries over a fixed boundary the way a reset-every-minute
counter does. Waiting callers reserve their slot and are served first come, first served.
All state is guarded by a lock, so one limiter is safe to share across threads and
coroutines. The decisions are checked against the moving-window limiter of `limits` and the
in-memory bucket of `pyrate-limiter`. The
[guide](https://github.com/JaviLianes8/taplimit/blob/main/GUIDE.md) states every
guarantee in detail.

## Why

The simple niche of "let this function run at most N times per period, in one process"
is oddly unserved:

- [`ratelimit`](https://pypi.org/project/ratelimit/) popularised the `@limits(calls, period)`
  shape and still had over 14 million downloads in the month to 16 October 2026, but its
  last release, 2.2.1, dates from December 2018. It counts calls in a fixed window that
  restarts once `period` has passed, so up to twice the limit can pass around a restart,
  and it has no asyncio support.
- [`limits`](https://pypi.org/project/limits/) and
  [`pyrate-limiter`](https://pypi.org/project/pyrate-limiter/) are maintained and implement
  the same sliding-window log (and more), but they are built around pluggable storage
  backends such as Redis, Memcached or SQL databases, and using them means choosing a
  storage, a strategy and a rate object first.
- [`limiter`](https://pypi.org/project/limiter/) is a token-bucket library with a different
  `rate` / `capacity` API, not the plain calls-per-period shape.

taplimit is the small, typed take: one decorator, a sliding window, thread-safe and
asyncio-aware, no dependencies, and a clock you can fake in tests. Reach for it when a
single process needs to stay under a rate and a full rate-limiting backend would be too much.

## Documentation

- [Guide](https://github.com/JaviLianes8/taplimit/blob/main/GUIDE.md): the algorithm, every
  guarantee, errors, threads and coroutines, keyed limits, testing and the command line.
- [Changelog](https://github.com/JaviLianes8/taplimit/blob/main/CHANGELOG.md), including
  what changed since 0.1.0.

## License

MIT. See [LICENSE](https://github.com/JaviLianes8/taplimit/blob/main/LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
