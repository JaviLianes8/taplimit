# taplimit

Small, typed, thread-safe in-process rate-limit decorator: N calls per period, block or raise.

Zero dependencies, one obvious decorator, and a reusable limiter object when you need to
share a budget. The clock and sleep are injectable, so tests never wait on real time.

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
def call_api() -> None:
    ...
```

Prefer to fail fast instead of waiting? Ask it to raise:

```python
from taplimit import rate_limit, RateLimitExceeded

@rate_limit(calls=15, period=60, on_limit="raise")
def call_api() -> None:
    ...

try:
    call_api()
except RateLimitExceeded as exc:
    print(f"slow down, retry in {exc.retry_after:.1f}s")
```

Share one budget across several functions, or control slots by hand, with the limiter
object. It is a decorator, a context manager, and exposes `acquire` / `try_acquire`:

```python
from taplimit import RateLimiter

limiter = RateLimiter(calls=100, period=60)

@limiter
def read() -> None: ...

@limiter
def write() -> None: ...  # read and write draw on the same 100-per-minute budget

with limiter:            # guard a block of code
    do_work()

if limiter.try_acquire():  # never blocks; returns False when full
    do_work()
```

### Testing without real time

`clock` (returns seconds) and `sleep` (waits seconds) are injectable, so a limiter runs
instantly under a fake clock:

```python
now = [0.0]
slept: list[float] = []

limiter = RateLimiter(
    calls=1, period=10,
    clock=lambda: now[0],
    sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)),
)
```

## How it limits

taplimit uses a **sliding window**: it keeps the timestamps of recent calls and a slot
frees exactly `period` seconds after the call that took it. A burst never carries over a
fixed boundary the way a reset-every-minute counter does, so the rate you ask for is the
rate you get. All state is guarded by a lock, so one decorator or limiter is safe to share
across threads.

## Why

The simple niche of "let this function run at most N times per period, in one process,
synchronously" is oddly unserved:

- [`ratelimit`](https://pypi.org/project/ratelimit/) popularised the `@limits(calls, period)`
  shape and is still downloaded millions of times a month, but it has been **abandoned since
  2018** (last release 2.2.1). It also uses a fixed window and its threading story is thin.
- [`pyrate-limiter`](https://pypi.org/project/pyrate-limiter/) and
  [`limits`](https://pypi.org/project/limits/) are maintained and capable, but they are
  **backend-oriented and heavy**: buckets, optional SQLite / Redis stores, async machinery.
  Overkill when all you want is a decorator on one function.
- [`limiter`](https://pypi.org/project/limiter/) is a token-bucket library with a different
  `rate` / `capacity` API, not the plain calls-per-period shape.

taplimit is the small, modern, typed take: one decorator, a sliding window, thread-safe,
no dependencies, and a clock you can fake in tests. Reach for it when a single process needs
to stay under a rate and a full rate-limiting backend would be too much.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
