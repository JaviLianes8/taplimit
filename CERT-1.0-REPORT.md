# taplimit 1.0.0 certification report

Progress:
- [x] Branch `release/1.0.0` created from `main` (0.2.0, never published, a53bfd7; PyPI has 0.1.0)
- [x] Baseline gates run on 0.2.0
- [ ] API review and 1.0.0 API changes (item 1)
- [ ] Ground truth: fetched documentation and established implementations run live (item 7)
- [ ] Errors, typing, docstrings and doctests (items 2 to 5)
- [ ] Contract, fuzz and author mutation round (items 6, 9, 18)
- [ ] Docs: README, GUIDE, CHANGELOG (items 11, 12)
- [ ] Packaging, e2e and upgrade from PyPI 0.1.0 (items 8, 13, 14)
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
