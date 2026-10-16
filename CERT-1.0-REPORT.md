# taplimit 1.0.0 certification report

Progress:
- [x] Branch `release/1.0.0` created from `main` (0.2.0, never published, a53bfd7; PyPI has 0.1.0)
- [x] Baseline gates run on 0.2.0
- [x] API review and 1.0.0 API changes (item 1)
- [x] Ground truth: fetched documentation and established implementations run live (item 7)
- [x] Errors, typing, docstrings and doctests (items 2 to 5)
- [ ] Contract, fuzz and author mutation round (items 6, 9, 18)
- [x] Docs: README, GUIDE, CHANGELOG (items 11, 12)
- [x] Packaging, e2e and upgrade from PyPI 0.1.0 (items 8, 13, 14)
- [ ] Every interpreter on this PC (item 10)
- [ ] Five QA lenses report PASS (item 19)
- [ ] Independent reviewer (item 16)
- [ ] Gates (item 15)
- [ ] PR open and trace guard CLEAN (item 17); merge and publish left to the maintainer

## Baseline on 0.2.0 (before any change)

Fresh clone of `main` (a53bfd7), CPython 3.13.2, private virtual environment.

| Command | Result |
| --- | --- |
| `ruff format --check .`, `ruff check .` | exit 0 |
| `mypy --strict src tests` | exit 0 (24 files) |
| `pytest` | 136 passed in 23 s (the end-to-end module builds a wheel on every run) |
| doctests | none in the package |

## Ground truth (item 7)

taplimit implements a sliding-window log. Three kinds of truth, none of them its own output:

- **Established implementations, run live.** `scripts/capture_oracles.py` (2026-10-16,
  CPython 3.11.5, throwaway virtual environment) drives `limits` 5.8.0
  (`MovingWindowRateLimiter` over `MemoryStorage`, with its `time.time` patched to a fake
  clock) and `pyrate-limiter` 4.5.0 (`InMemoryBucket`, timestamps passed in) through 60
  seeded schedules of 80 requests each (whole-number instants, costs 1 to `calls`, gaps
  aimed at the window edges). `tests/fixtures/oracles.json` keeps their decisions, the
  statistics `limits` reports and the wait `pyrate-limiter` reports after each refusal:
  4,800 requests, 3,188 granted, 1,612 refused, and the two libraries agree on every one.
  When both libraries are installed the suite runs five fresh schedules through them live.
- **Their published documentation.** `scripts/fetch_sources.py` fetches the `limits`
  5.8.0 strategies page (pinned commit, MIT; `tests/sources/MANIFEST.json` records URL,
  date, size, SHA-256 and licence; the copy stays local and git-ignored). The test reads
  its moving-window example (10 per minute: requests at 0:10, 0:20, 0:30, 0:50 allowed,
  1:11 allowed, 1:12 rejected) from the fetched file and replays it; the same sequence is
  also cited in the test with its URL, so it runs without the copy.
- **An independent brute-force model.** `tests/test_fuzz.py` finds the earliest instant at
  which a request fits by trying every candidate time and counting stamps, rather than by
  the library's index arithmetic, and checks every operation against it (40 seeds of 250
  random operations: try, refuse, wait, interrupted wait, reset, timeout).

What the comparison established:

| Property | Result |
| --- | --- |
| Decisions | equal to both libraries on all 4,800 requests when taplimit gets `period + 0.5` on whole-number instants (its half-open window then equals their closed one) |
| Waits | `retry_after` and `RateLimitExceeded.retry_after` equal `pyrate-limiter`'s wait minus 0.5 on all 1,612 refusals |
| Window statistics | replaying the grants of `limits` at the same period, taplimit accepts each one, `available()` equals `limits`' remaining on every request, and `retry_after() + t` equals its reset time whenever the window is full (1,967 instants) |
| Boundary | at the same period, the first difference in every schedule is a request exactly one period after a grant, which taplimit allows and both libraries refuse; the `limits` documentation states taplimit's rule ("at least" a period old) |

Defects of 0.2.0 found against this truth and the API review: a cost of `n` stored `n`
timestamps (a limiter of `10**9` slots per second allocated gigabytes on one call) and
returning an abandoned reservation removed them one at a time; `calls=True`, a `bool`
period, `Decimal` and string periods were accepted or failed with the interpreter's own
message; an infinite period was accepted and made a blocking call raise `OverflowError`;
`parse_rate` accepted non-ASCII digits and spaces and echoed whole inputs in its errors;
a timeout given with `blocking=False` to `limit()` was only rejected on the first call; the
public classes reported private module names.
