# taplimit

Small, typed, thread-safe in-process rate limiter: N calls per period, block or raise,
sync or async, globally or per key.

Zero dependencies, one obvious decorator, and a reusable limiter object when you need to
share a budget. The clock and sleep are injectable, so tests never wait on real time.
A small command-line tool throttles lines in a shell pipeline.

## Install

```
pip install taplimit
```

## Usage

Cap a function at N calls per period. By default a call over the limit blocks until a
slot frees:

```python
from taplimit import rate_limit


@rate_limit(calls=15, period=60)
def call_api() -> None: ...
```

Prefer to fail fast, or to wait only so long? Ask it to raise, or give a timeout:

```python
from taplimit import RateLimitExceeded, rate_limit


@rate_limit(calls=15, period=60, on_limit="raise")
def call_api() -> None: ...


@rate_limit(calls=15, period=60, timeout=5)  # waits up to 5 s, then raises
def call_other_api() -> None: ...


try:
    call_api()
except RateLimitExceeded as exc:
    print(f"slow down, retry in {exc.retry_after:.1f}s")
```

`async def` functions work the same way, waiting with `await` instead of blocking:

```python
@rate_limit(calls=10, period=1)
async def fetch(url: str) -> bytes: ...
```

Limit each user, host or token separately with `key`, which receives the call's arguments:

```python
@rate_limit(calls=5, period=60, on_limit="raise", key=lambda user, message: user)
def send(user: str, message: str) -> None: ...
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


with limiter:  # guard a block of code
    do_work()

if limiter.try_acquire():  # never blocks; returns False when full
    do_work()

limiter.acquire(cost=10, timeout=2.5)  # take ten slots, wait at most 2.5 s
print(limiter.available(), limiter.retry_after())
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
slept: list[float] = []

limiter = RateLimiter(
    calls=1,
    period=10,
    clock=lambda: now[0],
    sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)),
)
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

taplimit uses a **sliding window**: at every instant `t`, at most `calls` grants have a
timestamp in `(t - period, t]`. A slot frees exactly `period` seconds after the call that
took it, so a burst of up to `calls` is allowed at once and the sustained rate is
`calls / period`; nothing carries over a fixed boundary the way a reset-every-minute
counter does. Waiting callers reserve their slot and are served first come, first served.
All state is guarded by a lock, so one limiter is safe to share across threads and
coroutines. [GUIDE.md](GUIDE.md) states every guarantee in detail.

## Why

The simple niche of "let this function run at most N times per period, in one process"
is oddly unserved:

- [`ratelimit`](https://pypi.org/project/ratelimit/) popularised the `@limits(calls, period)`
  shape and is still downloaded millions of times a month, but it has been **abandoned since
  2018** (last release 2.2.1). It also uses a fixed window and its threading story is thin.
- [`pyrate-limiter`](https://pypi.org/project/pyrate-limiter/) and
  [`limits`](https://pypi.org/project/limits/) are maintained and capable, but they are
  **backend-oriented and heavy**: buckets, optional SQLite / Redis stores, async machinery.
  Overkill when all you want is a decorator on one function.
- [`limiter`](https://pypi.org/project/limiter/) is a token-bucket library with a different
  `rate` / `capacity` API, not the plain calls-per-period shape.

taplimit is the small, modern, typed take: one decorator, a sliding window, thread-safe
and asyncio-aware, no dependencies, and a clock you can fake in tests. Reach for it when a
single process needs to stay under a rate and a full rate-limiting backend would be too much.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
