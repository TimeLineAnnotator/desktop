"""Regular expressions for TQL: the one place that decides which engine runs them.

``search`` is ``re.search`` with a time limit when the optional ``regex``
package is installed (``pip install "tilia-core[regex]"``): it runs the pattern
on ``regex`` and gives it the time its caller's budget has left. ``regex``
checks its clock only now and then, so the bound is approximate, never exact.
Without the package ``search`` runs on ``re``, which has no time limit, and a
pattern that backtracks badly holds the whole process (``re`` keeps the GIL).

The budget belongs to the caller, who sets it with :func:`within`; it is
per thread and per context, so two threads never see each other's. Patterns are
Python ``re`` syntax, which ``regex`` accepts in its default (version 0) mode.
This is the only module that imports ``regex``, and importing it never fails
without the package.
"""

from __future__ import annotations

import contextlib
import contextvars
import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Any, Protocol

_engine: Any
# What a bad pattern raises: re.error, and with the package regex.error too
# (it is no subclass of re.error).
PatternError: tuple[type[Exception], ...]
try:
    import regex as _engine
except ImportError:
    _engine = re
    HAS_TIMEOUT = False
    PatternError = (re.error,)
else:
    HAS_TIMEOUT = True
    PatternError = (re.error, _engine.error)


class RegexTimeout(Exception):
    """A regular expression ran out of time (only with the ``regex`` package)."""


class Budget(Protocol):
    """How long the regular expressions of one call may take."""

    def seconds_left(self) -> float | None:
        """The seconds left, or None when there is no time limit."""

    def ran_out(self) -> None:
        """Record that the time limit was reached."""


_budget: contextvars.ContextVar[Budget | None] = contextvars.ContextVar(
    "tilia_core_regex_budget", default=None
)


@contextlib.contextmanager
def within(budget: Budget) -> Iterator[None]:
    """Make ``budget`` the current one for this thread and context; the
    previous one is put back on exit, an exception included."""
    token = _budget.set(budget)
    try:
        yield
    finally:
        _budget.reset(token)


@lru_cache(maxsize=512)
def _compile(engine: Any, pattern: str) -> Any:
    """``pattern`` compiled by ``engine``. ``regex.search(pattern, text)`` takes
    some 100 microseconds to find a compiled pattern again, ``re`` 5, and this
    runs for every row a statement reads."""
    return engine.compile(pattern)


def search(pattern: str, text: str) -> Any:
    """Like ``re.search(pattern, text)``: the match object or None.

    With the ``regex`` package and a current budget (see :func:`within`) the
    search is given the budget's seconds left; when they run out the budget's
    ``ran_out()`` is called once and :class:`RegexTimeout` is raised. A bad
    pattern raises the engine's own error (one of :data:`PatternError`)."""
    compiled = _compile(_engine, pattern)
    budget = _budget.get()
    if budget is None or not HAS_TIMEOUT:
        return compiled.search(text)
    seconds = budget.seconds_left()
    if seconds is None:  # no limit; regex is slower when given timeout=None
        return compiled.search(text)
    try:
        return compiled.search(text, timeout=seconds)
    except TimeoutError:
        budget.ran_out()
        raise RegexTimeout("the regular expression ran out of time") from None
