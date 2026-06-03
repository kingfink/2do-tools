# Contributing

Thanks for helping improve 2Do Tools.

## Privacy

Do not commit real 2Do database files, task exports, screenshots containing
private tasks, local credentials, tunnel URLs, or machine-specific config.
Tests should use synthetic task data only.

## Local Setup

```bash
uv sync --extra dev
```

Run checks before opening a pull request:

```bash
git ls-files '*.py' -z | xargs -0 python3 -m py_compile
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev pytest -q
```

## Pull Requests

Keep changes focused, include tests for behavior changes, and update README or
plugin metadata when install instructions change.
