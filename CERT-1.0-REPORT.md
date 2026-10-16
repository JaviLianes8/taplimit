# taplimit 1.0.0 certification report

Progress:
- [x] Branch `release/1.0.0` created from `main` (0.2.0, never published, a53bfd7; PyPI has 0.1.0)
- [x] Baseline gates run on 0.2.0
- [x] API review and 1.0.0 API changes (item 1)
- [x] Ground truth: fetched documentation and established implementations run live (item 7)
- [x] Errors, typing, docstrings and doctests (items 2 to 5)
- [x] Contract, fuzz and author mutation round (items 6, 9, 18)
- [x] Docs: README, GUIDE, CHANGELOG (items 11, 12)
- [x] Packaging, e2e and upgrade from PyPI 0.1.0 (items 8, 13, 14)
- [x] Every interpreter on this PC (item 10)
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

## Author mutation round (item 18)

Each mutant applied alone to a fresh clone, `pytest -x` with no bytecode and a 240 second
limit per run (a hang counts as killed), baseline green before and after, on Elena's PC
under CPython 3.14.2. Round 1 at 84a7907: of A01 to A36, 28 killed and 8 survived (A04,
A05, A07, A11, A19, A24, A34, A35); A37 failed its test but left a waiting thread that kept
the run from exiting, so the round stopped there. The survivors got contracts in 5dedeb0
(`tests/test_reservations.py`), test threads became daemons in 1a12af0, and A19 showed the
refused-key argument always equalled the key, so it was removed. Round 2 at 1a12af0: 36 applicable
mutants, 34 killed, 2 equivalent.

| Id | File | Mutation | Round 2 | Caught by |
| --- | --- | --- | --- | --- |
| A01 | `_window.py` | window closed at the far end | killed | `tests/test_edges.py::test_keyed_reset_keeps_reservations_and_drops_idle_keys` |
| A02 | `_window.py` | no queueing behind reservations | killed | `tests/test_fuzz.py::test_every_operation_matches_a_brute_force_model[0]` |
| A03 | `_window.py` | blocker off by one | killed | `tests/test_async.py::test_acquire_async_waits_for_the_slot` |
| A04 | `_window.py` | runs never merged | killed | `tests/test_reservations.py::test_acquisitions_at_one_instant_share_one_entry` |
| A05 | `_window.py` | give_back drops the whole run | killed | `tests/test_reservations.py::test_cancelling_one_of_two_waiters_at_the_same_instant_keeps_the_other` |
| A06 | `_window.py` | give_back forgets the total | killed | `tests/test_fuzz.py::test_every_operation_matches_a_brute_force_model[0]` |
| A07 | `_window.py` | available ignores reservations | killed | `tests/test_reservations.py::test_cancelling_one_of_two_waiters_at_the_same_instant_keeps_the_other` |
| A08 | `_window.py` | walk from the newest off by one | killed | `tests/test_async.py::test_a_cancelled_waiter_returns_its_reservation` |
| A09 | `_window.py` | reset keeps grants made this instant | killed | `tests/test_edges.py::test_keyed_reset_keeps_reservations_and_drops_idle_keys` |
| A10 | `_base.py` | bool accepted as a count | killed | `tests/test_validation.py::test_calls_must_be_an_integer[True-RateLimiter]` |
| A11 | `_base.py` | huge int period becomes zero | equivalent | equivalent: zero and infinity both fail the same range check with the same `ValueError` |
| A12 | `_base.py` | infinite period accepted | killed | `tests/test_validation.py::test_period_must_be_finite_and_positive[inf-RateLimiter]` |
| A13 | `_base.py` | zero timeout refused | killed | `tests/test_fuzz.py::test_every_operation_matches_a_brute_force_model[0]` |
| A14 | `_base.py` | timeout bound exclusive | killed | `tests/test_fuzz.py::test_every_operation_matches_a_brute_force_model[0]` |
| A15 | `_base.py` | interrupted wait keeps the slot | killed | `tests/test_fuzz.py::test_every_operation_matches_a_brute_force_model[0]` |
| A16 | `_base.py` | cancelled coroutine keeps the slot | killed | `tests/test_async.py::test_a_cancelled_waiter_returns_its_reservation` |
| A17 | `_base.py` | try_acquire never succeeds | killed | `tests/test_cli.py::test_pump_drop_mode_samples_without_waiting` |
| A18 | `_base.py` | cost one above calls accepted | killed | `tests/test_keyed.py::test_repr_and_validation` |
| A19 | `_base.py` | refused key from the wrong argument | n/a | code removed (survived round 1: the argument always equalled the key) |
| A20 | `_keyed.py` | sweep twice as rare | killed | `tests/test_keyed.py::test_idle_keys_are_evicted_after_a_period` |
| A21 | `_keyed.py` | queries start tracking keys | killed | `tests/test_docs.py::test_module_doctests_pass[taplimit]` |
| A22 | `_keyed.py` | reset keeps empty windows | killed | `tests/test_edges.py::test_keyed_reset_keeps_reservations_and_drops_idle_keys` |
| A23 | `_keyed.py` | decorated refusal loses the key | n/a | code removed with A19 (killed in round 1 by `tests/test_keyed.py::test_limit_derives_the_key_from_the_arguments`) |
| A24 | `_decorator.py` | unknown on_limit blocks (guarded) | equivalent | equivalent: `on_limit` is already restricted to "block" or "raise" two lines above |
| A25 | `_decorator.py` | timeout with raise accepted | killed | `tests/test_validation.py::test_timeout_is_checked_when_a_decorator_is_built` |
| A26 | `_rate.py` | ms read as minutes | killed | `tests/test_docs.py::test_module_doctests_pass[taplimit._rate]` |
| A27 | `_rate.py` | hour unit wrong | killed | `tests/test_edges.py::test_milliseconds_are_not_mistaken_for_minutes` |
| A28 | `_rate.py` | preview one longer | killed | `tests/test_validation.py::test_rate_messages_show_at_most_forty_characters` |
| A29 | `_rate.py` | unicode digits accepted | killed | `tests/test_validation.py::test_parse_rate_reads_ascii_only[\u0661\u0660/s]` |
| A30 | `_rate.py` | fractional multiplier refused | killed | `tests/test_fuzz_rate.py::test_generated_rate_strings_parse_to_their_meaning[0]` |
| A31 | `_errors.py` | pickle drops the key | killed | `tests/test_contract.py::test_the_error_is_an_exception_with_its_fields_and_pickles` |
| A32 | `_cli.py` | dropped lines not counted | killed | `tests/test_cli.py::test_pump_drop_mode_samples_without_waiting` |
| A33 | `_cli.py` | ctrl-c exit status | killed | `tests/test_edges.py::test_ctrl_c_reports_dropped_lines_and_exits_130` |
| A34 | `_wrap.py` | async __call__ objects not awaited | killed | `tests/test_reservations.py::test_an_async_callable_object_takes_its_slot_when_awaited` |
| A35 | `_limiter.py` | async with blocks the loop | killed | `tests/test_reservations.py::test_async_with_waits_with_the_async_sleep` |
| A36 | `__init__.py` | classes keep private module names | killed | `tests/test_contract.py::test_classes_report_the_package_as_their_module` |
| A37 | `_limiter.py` | reset drops reservations | killed | `tests/test_edges.py::test_reset_during_a_wait_keeps_the_limit` |
| A38 | `_window.py` | available one short | killed | `tests/test_docs.py::test_module_doctests_pass[taplimit]` |

## Supported Pythons (item 10)

`requires-python = ">=3.10"`. The suite from the extracted sdist, with `src` removed so it
imports the installed wheel, on every interpreter of this PC from 3.10 up (at be199b0):
CPython 3.10.19, 3.11.5, 3.12.12, 3.13.2, 3.14.2 and 3.14.2 free-threaded, 619 passed and
10 skipped on each (five live-oracle tests without the reference libraries, four opt-in
end-to-end tests, the fetched-documentation test without its copy). 3.8 and 3.9 are also
installed but below `requires-python`.

## QA lenses (item 19)

Five independent reviews, one at a time, each reading the certification rules, running the
code and reporting only to the maintainer. Later rounds confirm the earlier findings and
sweep at most 40 new mutations on the code changed since.

| Lens | Round | Head | Verdict | Findings and outcome |
| --- | --- | --- | --- | --- |
| a. API and docs | 1 | be199b0 | FAIL | a literal dash character in a test; CHANGELOG missed `Decimal` and `Fraction` counts and overstated infinities; `rate_limit` key not checked when built; `annotations` visible in the package; NaN timeout message; README cross-check wording; no method examples. Fixed in a70f994 and 0758180 |
| a | 2 | 0758180 | FAIL | all seven confirmed; the new method doctests were never run by the suite. Fixed in c00eebd |
| a | 3 | c00eebd | PASS | breaking either method example now fails the suite |
| b. Correctness and ground truth | 1 | c00eebd | PASS (4 low) | oracle fixture reproduced byte for byte; 500 own schedules (41,520 requests) against `limits` sync and async, `pyrate-limiter` memory and SQLite and a naive log, 0 mismatches; reservation model 800 seeds (59,646 operations), 0 mismatches; 645,120 rate strings against an own parser, 0 differences. Low: a waiter cancelled after a reset could return a newer grant at the same instant; GUIDE wait wording; `10pers` parsed; capture script wrote CRLF. Fixed in 106fe77 |
| b | 2 | 106fe77 | PASS | fixes confirmed; 250 schedules, 400 model seeds, 645,120 strings, 0 differences; 34 mutants on changed code, 29 killed, 4 equivalent, 1 needing a contract (a multiplier ending in a bare point), added in a09535b |
| c. Adversarial and robustness | 1 | a09535b | FAIL | quadratic work with tens of thousands of queued or cancelled waiters; `available()` below zero after float rounding; quadratic regex on a run of spaces; huge numbers echoed in messages; non-finite clock readings accepted; sleeps over the platform limit; CLI traceback without stdin or stdout and full long file names; GUIDE rows for keys. Fixed in 0aa970e (runs indexed by a Fenwick tree, expiry by stamp plus period) |
| c | 2 | 0aa970e | FAIL | all eight confirmed (40,000 waiters queue in 0.69 s and cancel in 0.44 s; 30,000 rounding cases; 256k spaces in 0.02 s); new: an interrupted wait gave back the caller's raw cost instead of the checked one; 40 mutants, 30 killed, 2 equivalent, 8 needing contracts. Fixed in 05cf673 |
| c | 3 | 05cf673 | FAIL | fix confirmed with a 6,000-iteration fuzz; 16 mutants, 12 killed, 3 equivalent (spent counts not zeroed, give-back of the whole cost, the reset instant under a clock that steps back, which is not allowed), 1 needing an async contract, added in fabd984 |
| c | 4 | fabd984 | PASS | the async survivor is killed |
| d. Packaging and real e2e | 1 | ee28d15 | PASS (2 low) | build and `twine check --strict`; wheel and sdist contents and metadata; suite from the sdist against the installed wheel on 3.10.19, 3.11.5, 3.12.12, 3.13.2, 3.14.2, 3.14.2t (654 passed each); CLI by subprocess (console script and `-m`), byte-exact output, every bad usage exits 2, closed pipe exits 0; upgrade in place from PyPI 0.1.0 with 0.1.0-style code; strict mypy consumer of every name; opt-in e2e 4 passed; sdist install. Low: `release.ps1` refused any project already on PyPI; the sdist exclude named `.html` for a fetched `.rst`. Fixed in the next commit |
| d | 2 | 2416dd3 | PASS | the release script checks only the exact version (1.0.0 proceeds, 0.1.0 is refused; upload not run); an sdist built without git leaves the fetched copy out |
| e. Contract strength (blind) | 1 | 2416dd3 | FAIL | 100 own mutants over every module: 89 killed (3 by the time limit), 1 equivalent (give-back capped at the run's count), 10 survivors: give-back without the lock, `--drop` of exactly one line, non-pipe output errors swallowed, `rate_limit` losing `async_sleep`, keyed coroutine cost, `with` not waiting, `__exit__`/`__aexit__` swallowing errors, decorated coroutine blocking in the sync sleep, and the reset instant under a clock that steps back. Contracts in 279d611 (`tests/test_protocols.py`) |
| e | 2 | 279d611 | PASS | all nine killed by the new contracts; the reset-instant mutant agreed equivalent (it differs only when the clock steps back, which the guide forbids); the `async_sleep` mutant now fails in about 10 s instead of hanging (bounded in the next commit) |
