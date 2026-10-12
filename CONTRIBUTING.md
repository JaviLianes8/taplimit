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
- One logical change per commit, imperative subject line.

Open an issue first if the change is large or shifts the public API.
