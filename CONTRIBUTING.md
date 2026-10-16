# Contributing

Thanks for taking the time. This project keeps a small, predictable shape.

## Setup

```
pip install -r requirements-dev.txt
```

## Before you open a pull request

- Keep public API in `src/taplimit/__init__.py`; internals live in `_`-prefixed modules.
- Add a test for the behaviour you change. Behaviour tests inject the clock and sleep;
  only the stress tests use real time, and only with bounds that cannot flake.
- Run `scripts/check.ps1` (format, lint, types, tests) and make sure it passes.
- `TAPLIMIT_E2E=1 pytest tests/test_e2e_wheel.py` builds the wheel, installs it in fresh
  virtual environments and upgrades from the published 0.1.0 (needs the network).
- `python scripts/fetch_sources.py` fetches the documentation the ground-truth tests read
  into `tests/sources/` (not committed; those tests skip without it).
  `scripts/capture_oracles.py` regenerates `tests/fixtures/oracles.json` from the
  reference libraries; with them installed, the suite also runs them live.
- One logical change per commit, imperative subject line.

Open an issue first if the change is large or shifts the public API.
