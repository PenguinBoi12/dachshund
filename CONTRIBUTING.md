# Contributing to dachshund

## Setup

1. Clone the dachshund repository
2. Create and activate a virtual environment
3. Install the development dependencies

```bash
pip install -e ".[dev]"
```

## Checks

Run these before committing, they are the same checks CI runs:

```bash
black dachshund/ tests/
mypy dachshund
pytest -v --cov=dachshund --cov-report=term-missing --cov-fail-under=90
```

## Branching

Work happens on local branches, which are merged into `dev`. `dev` is merged into `main`
for releases, so `main` stays clean.

## Guidelines

Add docstrings to all of your code (functions, methods, classes, ...). The codebase
should have enough examples for you to copy from.

Write tests for your code.

- If you are fixing a bug, add a regression test that references the original issue.
- If you are implementing a new feature, add tests covering the new functionality.

All code must be formatted with [black](https://black.readthedocs.io/), typed
([type hinting](https://docs.python.org/3/library/typing.html)) and pass
[mypy](https://mypy-lang.org/). The code, documentation and other text must be in
English.
