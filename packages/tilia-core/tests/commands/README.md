# The subcommands' tests

Tests of `tilia run` and of what every subcommand shares: files `test_run*.py` and `test_conventions.py`, with no `__init__.py`. Helpers here are imported by their bare names (`pythonpath` in `pyproject.toml`), so they must not share a name with those in `tests/timemap` or `tests/importers`.
