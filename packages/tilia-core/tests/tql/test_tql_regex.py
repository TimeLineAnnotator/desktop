"""Regular expressions in SQL: ``REGEXP`` runs on the optional ``regex`` package
when it is installed, which gives a user's pattern a time limit, and on ``re``
when it is not (``tilia_core.tql.regexes``)."""

import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import examples
import fixture_index
import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from tilia_core import tql
from tilia_core.labels import nfc
from tilia_core.tql import engine, regexes, sqlfuncs, values
from tilia_core.tql.readonly import Limits, Stopped
from tilia_core.tql.syntax import TQLError

CORE = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = CORE.parents[1] / "scripts" / "check_packages.py"
FIXTURES = examples.load()["fixtures"]
# Both engines backtrack on this: `re` needs hours on the text below, `regex`
# gives up when its timeout runs out (a little after it, as its timeout is not
# exact).
CATASTROPHIC = "(a|aa)+$"
LONG_TEXT = "a" * 40 + "!"
SHORT_TEXT = "a" * 12 + "!"
CHILD_TIMEOUT = 45
PATIENCE = 60  # seconds a thread waits for another on a loaded machine
NO_TIMEOUT = "no timeout given"
# A clock that ticks coarsely (Windows': every 15 ms) can give the same instant twice, and then
# (t + 60) - t is not 60 to the last digit: the time left may exceed the limit by rounding.
CLOCK_SLACK = 1e-6
FROZEN_AT = 65483.490711330895  # (FROZEN_AT + 60) - FROZEN_AT is 60.000000000007276


@pytest.fixture
def index():
    return fixture_index.build_index(FIXTURES["exposition"])


@pytest.fixture
def regex_pkg():
    return pytest.importorskip("regex")


@pytest.fixture
def without_the_extra(monkeypatch):
    """What a process without ``regex`` sees: ``re`` runs the patterns."""
    monkeypatch.setattr(regexes, "_engine", re)
    monkeypatch.setattr(regexes, "HAS_TIMEOUT", False)


@pytest.fixture
def with_the_extra(monkeypatch, regex_pkg):
    monkeypatch.setattr(regexes, "_engine", regex_pkg)
    monkeypatch.setattr(regexes, "HAS_TIMEOUT", True)


class SpyEngine:
    """Stands in for ``regex``, in a process with or without it: runs ``re`` and
    notes what it was asked. Like ``regex`` it raises TimeoutError for a
    timeout of 0, and (not like it) for any timeout when the text has "slow"."""

    def __init__(self):
        self.calls = []
        self.compiled = []
        self.meeting = None  # a Barrier: each thread waits at its first search
        self.met = set()

    def compile(self, pattern):
        self.compiled.append(pattern)
        return SpyPattern(self, pattern)


class StrictSpyEngine(SpyEngine):
    """Like ``regex`` and ``re``, it refuses a bad pattern when it compiles it."""

    def compile(self, pattern):
        re.compile(pattern)
        return super().compile(pattern)


class SpyPattern:
    def __init__(self, engine, pattern):
        self.engine = engine
        self.pattern = pattern

    def search(self, text, **kwargs):
        me = threading.get_ident()
        if self.engine.meeting is not None and me not in self.engine.met:
            self.engine.met.add(me)
            self.engine.meeting.wait()
        self.engine.calls.append({"thread": me, **kwargs})
        timeout = kwargs.get("timeout")
        if timeout is not None and (timeout == 0 or "slow" in text):
            raise TimeoutError("regex timed out")
        return re.search(self.pattern, text)


@pytest.fixture
def spy(monkeypatch):
    engine = SpyEngine()
    monkeypatch.setattr(regexes, "_engine", engine)
    monkeypatch.setattr(regexes, "HAS_TIMEOUT", True)
    return engine


@pytest.fixture
def strict_spy(monkeypatch):
    engine = StrictSpyEngine()
    monkeypatch.setattr(regexes, "_engine", engine)
    monkeypatch.setattr(regexes, "HAS_TIMEOUT", True)
    return engine


@pytest.fixture(params=["re", "regex"])
def either_engine(request, monkeypatch):
    """The patterns run on ``re``, then on ``regex`` (skipped without it)."""
    if request.param == "re":
        monkeypatch.setattr(regexes, "_engine", re)
        monkeypatch.setattr(regexes, "HAS_TIMEOUT", False)
    else:
        monkeypatch.setattr(regexes, "_engine", pytest.importorskip("regex"))
        monkeypatch.setattr(regexes, "HAS_TIMEOUT", True)
    return request.param


class FrozenClock:
    """Stands in for the ``time`` module the limits read, on a clock that does not move."""

    def monotonic(self):
        return FROZEN_AT


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setattr("tilia_core.tql.readonly.time", FrozenClock())


def timeout_given(spy):
    """The timeout a search on this thread passes to the engine."""
    regexes.search("a", "a")
    mine = [c for c in spy.calls if c["thread"] == threading.get_ident()]
    return mine[-1].get("timeout", NO_TIMEOUT)


class Boom(Exception):
    pass


class FixedBudget:
    def __init__(self, seconds):
        self.seconds = seconds
        self.ran_out_calls = 0

    def seconds_left(self):
        return self.seconds

    def ran_out(self):
        self.ran_out_calls += 1


def child_env():
    return {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}


def run_python(code, *args):
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        env=child_env(),
        capture_output=True,
        text=True,
        timeout=CHILD_TIMEOUT,
    )


CHILD = textwrap.dedent(
    """
    import json
    import sys
    import time

    import examples
    import fixture_index
    from tilia_core import tql

    index = fixture_index.build_index(examples.load()["fixtures"]["exposition"])
    start = time.monotonic()
    got = tql.sql(index, sys.argv[1], time_limit=float(sys.argv[2]))
    print(
        json.dumps(
            {
                "stopped": got.stopped,
                "rows": len(got.rows),
                "elapsed": time.monotonic() - start,
            }
        )
    )
    """
)


def sql_in_a_child(text, time_limit):
    """Run ``tql.sql`` in a process of its own: if the time limit does not cover
    the regular expression, that process is held for hours, and the test fails
    after CHILD_TIMEOUT seconds instead of hanging the run."""
    try:
        done = run_python(CHILD, text, str(time_limit))
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"tql.sql was still running {CHILD_TIMEOUT} s after it started "
            f"with time_limit={time_limit}: the regular expression held the "
            "process, so the time limit does not cover it"
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


# -- the time limit covers a regular expression -------------------------------


def test_a_pattern_that_backtracks_badly_is_stopped_by_the_time_limit(regex_pkg):
    got = sql_in_a_child(
        f"SELECT 1 WHERE '{LONG_TEXT}' REGEXP '{CATASTROPHIC}'", time_limit=0.5
    )
    assert got["stopped"] == "time_limit"
    assert got["rows"] == 0
    assert got["elapsed"] < 30


def test_a_time_limit_of_zero_stops_a_statement_with_a_regular_expression(regex_pkg):
    got = sql_in_a_child(
        f"SELECT 1 WHERE '{LONG_TEXT}' REGEXP '{CATASTROPHIC}'", time_limit=0
    )
    assert got["stopped"] == "time_limit"
    assert got["rows"] == 0
    assert got["elapsed"] < 30


def test_without_a_time_limit_a_regular_expression_runs_to_its_answer(index):
    none = tql.sql(index, f"SELECT 1 WHERE '{SHORT_TEXT}' REGEXP '{CATASTROPHIC}'")
    assert (none.rows, none.stopped) == ([], None)
    some = tql.sql(index, f"SELECT 1 WHERE '{'a' * 12}' REGEXP '{CATASTROPHIC}'")
    assert (some.rows, some.stopped) == ([(1,)], None)


def test_without_a_time_limit_the_engine_is_given_no_timeout(index, spy):
    tql.sql(index, "SELECT label REGEXP 'a' FROM components")
    assert spy.calls
    assert all(c.get("timeout") is None for c in spy.calls)


def test_the_engine_is_given_the_time_left_of_the_call(index, spy):
    tql.sql(index, "SELECT label REGEXP 'a' FROM components", time_limit=60)
    assert spy.calls
    assert all(0 < c["timeout"] <= 60 + CLOCK_SLACK for c in spy.calls)


def test_a_clock_that_does_not_move_gives_the_limit_up_to_rounding(
    index, spy, frozen_clock
):
    tql.sql(index, "SELECT label REGEXP 'a' FROM components", time_limit=60)
    assert spy.calls
    assert all(60 <= c["timeout"] <= 60 + CLOCK_SLACK for c in spy.calls)


def test_a_time_limit_already_passed_gives_the_engine_a_timeout_of_zero(index, spy):
    # regex takes a negative timeout for none at all
    got = tql.sql(index, "SELECT 1 WHERE 'a' REGEXP 'a'", time_limit=0)
    assert [c["timeout"] for c in spy.calls] == [0.0]
    assert got.stopped == "time_limit"


def test_rows_read_before_a_regular_expression_ran_out_are_returned(index, spy):
    got = tql.sql(
        index,
        "SELECT column1 FROM (VALUES ('ok1'), ('ok2'), ('slow'), ('ok3')) "
        "WHERE column1 REGEXP 'o'",
        time_limit=60,
    )
    assert got.stopped == "time_limit"
    assert got.rows[:1] == [("ok1",)]
    assert ("slow",) not in got.rows
    assert ("ok3",) not in got.rows


def test_a_regular_expression_that_ran_out_does_not_raise(index, spy):
    got = tql.sql(index, "SELECT 'slow' REGEXP 'o'", time_limit=60)
    assert got.stopped == "time_limit"
    assert got.rows == []


def test_the_budget_of_a_call_is_taken_off_when_it_ends(index, spy):
    tql.sql(index, "SELECT 'a' REGEXP 'a'", time_limit=60)
    assert spy.calls
    assert timeout_given(spy) == NO_TIMEOUT


def test_the_budget_of_a_call_is_taken_off_when_it_fails(index, spy):
    with pytest.raises(TQLError):
        tql.sql(index, "SELECT 'a' REGEXP 'a' FROM nope", time_limit=60)
    with pytest.raises(TQLError):
        tql.sql(index, "SELECT 'a' REGEXP '('", time_limit=60)
    assert timeout_given(spy) == NO_TIMEOUT


def test_limits_report_the_seconds_left():
    assert Limits(None, None).seconds_left() is None
    assert 0 < Limits(60, None).seconds_left() <= 60 + CLOCK_SLACK
    passed = Limits(0, None)
    time.sleep(0.02)
    assert passed.seconds_left() == 0.0


def test_a_regular_expression_that_ran_out_records_a_time_limit_unless_stopped():
    limits = Limits(None, None)
    limits.ran_out()
    assert limits.stopped == "time_limit"
    limits = Limits(None, None)
    limits.stopped = "cancelled"
    limits.ran_out()
    assert limits.stopped == "cancelled"


# -- sqlfuncs.regexp ----------------------------------------------------------


def test_regexp_lets_a_regex_timeout_through(spy):
    with regexes.within(FixedBudget(0.0)):
        with pytest.raises(regexes.RegexTimeout):
            sqlfuncs.regexp("a", "a")


def test_regexp_searches_through_the_regexes_module(spy):
    assert sqlfuncs.regexp("a", "xax") == 1
    assert len(spy.calls) == 1


def test_a_pattern_is_compiled_once_however_often_it_is_searched(spy):
    for text in ("a", "ba", "ca", "d"):
        regexes.search("a+", text)
    regexes.search("b+", "b")
    assert spy.compiled == ["a+", "b+"]
    assert len(spy.calls) == 5


# -- the fallback on re -------------------------------------------------------


@pytest.mark.usefixtures("without_the_extra")
@pytest.mark.parametrize(
    "statement, expected",
    [
        ("SELECT 'Sätze' REGEXP 'ät'", 1),
        ("SELECT 'Sätze' REGEXP 'ö'", 0),
        ("SELECT 'ABC' REGEXP 'abc'", 0),
        ("SELECT 'ABC' REGEXP '(?i)abc'", 1),
        ("SELECT 'Sa\u0308tze' REGEXP 'Sätze'", 1),
        ("SELECT NULL REGEXP 'a'", 0),
        ("SELECT 'a' REGEXP NULL", 0),
        ("SELECT NULL REGEXP NULL", 0),
    ],
)
def test_without_the_extra_regexp_still_answers(index, statement, expected):
    assert tql.sql(index, statement).rows == [(expected,)]


def test_without_the_extra_a_budget_applies_no_timeout(without_the_extra):
    budget = FixedBudget(0.0)
    with regexes.within(budget):
        assert regexes.search("a", "a")
    assert budget.ran_out_calls == 0


def test_without_the_extra_a_time_limit_still_stops_what_is_not_a_regex(
    index, without_the_extra
):
    got = tql.sql(
        index,
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
        "SELECT x FROM n WHERE x REGEXP '9'",
        time_limit=0.05,
    )
    assert got.stopped == "time_limit"


def test_the_docstring_of_sql_says_where_the_limits_do_not_cover_regexes():
    doc = " ".join(tql.sql.__doc__.split())
    assert re.search(
        r"[Ww]ithout the ``regex`` package, neither limit covers a regular "
        r"expression, and a pattern that backtracks badly can hold the whole "
        r"process",
        doc,
    )
    assert "a regular expression is bounded by ``time_limit``" in doc
    assert "``cancel`` cannot interrupt a regular expression that is running" in doc


def test_the_docstring_of_sqlfuncs_says_a_pattern_is_bounded_by_the_time_limit():
    doc = " ".join(sqlfuncs.__doc__.split())
    assert "``regex`` package a pattern is bounded by the call's time limit" in doc


BLOCK_REGEX = textwrap.dedent(
    """
    import importlib
    import importlib.abc
    import pkgutil
    import re
    import sys


    class Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.partition(".")[0] == "regex":
                raise ImportError(f"{fullname} is blocked")
            return None


    sys.meta_path.insert(0, Blocker())
    package = importlib.import_module("tilia_core")
    for info in pkgutil.walk_packages(package.__path__, "tilia_core."):
        importlib.import_module(info.name)
    from tilia_core.tql import regexes, sqlfuncs

    assert "regex" not in sys.modules
    print(regexes.HAS_TIMEOUT, regexes._engine is re, sqlfuncs.regexp("b", "abc"))
    """
)


def test_tilia_core_imports_and_answers_without_the_regex_package():
    done = run_python(BLOCK_REGEX)
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["False", "True", "1"]


def test_with_the_extra_installed_regex_runs_the_patterns(regex_pkg):
    assert regexes.HAS_TIMEOUT is True
    assert regexes._engine is regex_pkg


# -- both engines agree -------------------------------------------------------

AGREE = [
    ("^abc", "abcdef", True),
    ("^abc", "xabc", False),
    ("abc$", "xxabc", True),
    ("abc$", "abcx", False),
    ("(ab)+", "xababx", True),
    ("(a|b)c", "bc", True),
    ("(a|b)c", "cc", False),
    ("(x)?(y)", "y", True),
    ("(?i)hello", "HeLLo wOrld", True),
    ("hello", "HELLO", False),
    ("ä", "Bär", True),
    ("ö", "Bär", False),
    (r"\w+é", "café", True),
    (r"\d+", "bar ٣٤", True),
    ("^$", "", True),
    ("a", "", False),
    ("a*", "", True),
    ("[A-G][#b]?", "F#", True),
    ("[^a-z]", "abc", False),
    ("[0-9]+", "bar 12", True),
    ("a{2,3}", "a", False),
    ("a{2,3}", "caab", True),
    ("^a{3}$", "aaa", True),
    ("^a{3}$", "aaaa", False),
    ("a+?", "aaa", True),
    ("(a+?)(a*)", "aaa", True),
    ("<.+?>", "<a><b>", True),
    ("<(.+)>", "<a><b>", True),
    ("foo(?=bar)", "foobar", True),
    ("foo(?!bar)", "foobar", False),
    ("(?<=x)y", "xy", True),
    ("(?<!x)y", "xy", False),
    (r"\bcat\b", "a cat sat", True),
    (r"\bcat\b", "concatenate", False),
    ("(a)\\1", "aa", True),
    ("(?P<n>a)(?P=n)", "aa", True),
    ("a.b", "a\nb", False),
    ("(?s)a.b", "a\nb", True),
    ("(?m)^b", "a\nb", True),
    ("(?:a|b)+", "xabbay", True),
]


def summary(match):
    return None if match is None else (match.groups(), match.span())


@pytest.mark.parametrize("pattern, text, expected", AGREE)
def test_both_engines_give_the_same_answer(
    monkeypatch, regex_pkg, pattern, text, expected
):
    monkeypatch.setattr(regexes, "_engine", re)
    monkeypatch.setattr(regexes, "HAS_TIMEOUT", False)
    by_re = regexes.search(pattern, text)
    monkeypatch.setattr(regexes, "_engine", regex_pkg)
    monkeypatch.setattr(regexes, "HAS_TIMEOUT", True)
    by_regex = regexes.search(pattern, text)
    assert by_regex is None or isinstance(by_regex, regex_pkg.Match)
    assert by_re is None or isinstance(by_re, re.Match)
    assert (by_re is not None) is expected
    assert (by_regex is not None) is expected
    assert summary(by_regex) == summary(by_re)


def test_the_table_of_cases_is_big_enough():
    assert len(AGREE) >= 25


@pytest.mark.parametrize("engine", ["re", "regex"])
@pytest.mark.parametrize("pattern", ["(", "[a", "a{2,1}", "*", "(?P<n"])
def test_an_invalid_pattern_raises_a_tql_error(index, monkeypatch, engine, pattern):
    if engine == "re":
        monkeypatch.setattr(regexes, "_engine", re)
        monkeypatch.setattr(regexes, "HAS_TIMEOUT", False)
    else:
        monkeypatch.setattr(regexes, "_engine", pytest.importorskip("regex"))
        monkeypatch.setattr(regexes, "HAS_TIMEOUT", True)
    with pytest.raises(TQLError):
        tql.sql(index, f"SELECT 'a' REGEXP '{pattern}'", time_limit=60)


# -- regexes.within and regexes.search ----------------------------------------


def test_within_nests_and_puts_the_previous_budget_back(spy):
    outer, inner = FixedBudget(10.0), FixedBudget(5.0)
    assert timeout_given(spy) == NO_TIMEOUT
    with regexes.within(outer):
        assert timeout_given(spy) == 10.0
        with regexes.within(inner):
            assert timeout_given(spy) == 5.0
        assert timeout_given(spy) == 10.0
    assert timeout_given(spy) == NO_TIMEOUT


def test_within_puts_the_previous_budget_back_after_an_exception(spy):
    with regexes.within(FixedBudget(10.0)):
        with pytest.raises(Boom):
            with regexes.within(FixedBudget(5.0)):
                raise Boom
        assert timeout_given(spy) == 10.0
    with pytest.raises(Boom):
        with regexes.within(FixedBudget(5.0)):
            raise Boom
    assert timeout_given(spy) == NO_TIMEOUT


def test_a_thread_without_a_budget_is_not_affected_by_the_budget_of_another(spy):
    seen = []
    thread = threading.Thread(target=lambda: seen.append(timeout_given(spy)))
    with regexes.within(FixedBudget(7.0)):
        thread.start()
        thread.join(timeout=10)
        assert timeout_given(spy) == 7.0
    assert seen == [NO_TIMEOUT]


def test_threads_with_budgets_of_their_own_do_not_see_each_other(spy):
    both_in = threading.Barrier(2, timeout=10)
    seen = {}

    def work(name, seconds):
        with regexes.within(FixedBudget(seconds)):
            both_in.wait()
            seen[name] = timeout_given(spy)

    threads = [
        threading.Thread(target=work, args=("one", 1.5)),
        threading.Thread(target=work, args=("two", 2.5)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert seen == {"one": 1.5, "two": 2.5}


def test_a_budget_that_gives_none_means_no_timeout(spy):
    with regexes.within(FixedBudget(None)):
        assert timeout_given(spy) in (None, NO_TIMEOUT)


def test_search_with_no_budget_gives_the_engine_no_timeout(spy):
    assert regexes.search("a", "xax") is not None
    assert spy.calls[0].get("timeout", NO_TIMEOUT) == NO_TIMEOUT


def test_search_tells_the_budget_once_when_the_time_ran_out(spy):
    budget = FixedBudget(0.0)
    with regexes.within(budget):
        with pytest.raises(regexes.RegexTimeout):
            regexes.search("a", "a")
    assert budget.ran_out_calls == 1


def test_with_the_extra_a_search_that_ran_out_raises_and_tells_the_budget_once(
    with_the_extra,
):
    budget = FixedBudget(0.0)
    with regexes.within(budget):
        with pytest.raises(regexes.RegexTimeout):
            regexes.search("a", "a")
    assert budget.ran_out_calls == 1


def test_with_the_extra_a_budget_that_gives_none_applies_no_timeout(with_the_extra):
    budget = FixedBudget(None)
    with regexes.within(budget):
        assert regexes.search("a", "a")
    assert budget.ran_out_calls == 0


def test_with_the_extra_a_search_with_time_left_returns_its_match(with_the_extra):
    budget = FixedBudget(30.0)
    with regexes.within(budget):
        assert regexes.search("(a)(b)", "xab").groups() == ("a", "b")
        assert regexes.search("c", "xab") is None
    assert budget.ran_out_calls == 0


def test_an_invalid_pattern_is_the_engines_own_error(with_the_extra, regex_pkg):
    with pytest.raises(regex_pkg.error):
        regexes.search("(", "a")


# -- tql.run: the time limit covers a regular expression ----------------------


def labelled(name, label):
    """A file whose form unit, composer and second timeline all read ``label``."""
    return {
        "name": name,
        "length": 10,
        "fields": {"composer": label},
        "timelines": [
            {"name": "Form (X)", "kind": "hierarchy", "units": [[label, 1, 0, 5]]},
            {"name": label, "kind": "marker", "units": []},
        ],
    }


def paired(name, subject, pattern):
    """A file of two units, the second one's label a pattern for the first's."""
    return {
        "name": name,
        "length": 10,
        "timelines": [
            {
                "name": "Form (X)",
                "kind": "hierarchy",
                "units": [[subject, 1, 0, 5], [pattern, 1, 5, 10]],
            }
        ],
    }


PAIR_QUERY = "* THEN * IN form WHERE $1.label ~ $2.label"


def scenarios(pattern, early, late):
    """What a regular expression is asked in each place ``run`` can ask one:
    ``{name: (files, query, files of the matches that come before the last
    file)}``. ``early`` is ``(file, label)`` pairs whose units the pattern is
    found in; the last file, ``z9``, has the label ``late``. ``sql``: a pattern
    literal, which is SQL's ``REGEXP``. The others run in Python: ``python``,
    a ``~`` on the units of a pattern; ``units``, ``timelines`` and ``files``,
    a query of only ``WHERE`` that lists those; ``pair``, the labels of two
    units, one of them the pattern."""
    where = {
        "sql": f"/{pattern}/ IN form",
        "python": f"* IN form WHERE label ~ /{pattern}/",
        "units": f"WHERE label ~ /{pattern}/",
        "timelines": f"WHERE tl.name ~ /{pattern}/",
        "files": f"WHERE file.composer ~ /{pattern}/",
    }
    first = [name for name, _ in early]
    out = {
        name: (
            [labelled(f, label) for f, label in early] + [labelled("z9", late)],
            query,
            first,
        )
        for name, query in where.items()
    }
    out["pair"] = (
        [paired(f, "x" + label, pattern) for f, label in early]
        + [paired("z9", late, pattern)],
        PAIR_QUERY,
        first,
    )
    return out


EARLY = [("a1", "aaa"), ("m5", "aaaa")]
ALONE = scenarios(CATASTROPHIC, [], LONG_TEXT)
AFTER_SOME = scenarios(CATASTROPHIC, EARLY, LONG_TEXT)
SLOW = scenarios("ok", [("a1", "ok"), ("m5", "okay")], "slow")  # see SpyPattern
SLOW_ALONE = scenarios("ok", [], "slow")
FINE = scenarios("ok", [("a1", "ok"), ("m5", "okay")], "fine")
WAYS = list(ALONE)


def files_of(got):
    return [row["file"] for row in got.rows]


def run_scenario(case, **limits):
    files, query, _ = case
    return tql.run(fixture_index.build_index(*files), query, **limits)


CHILD_RUN = textwrap.dedent(
    """
    import json
    import sys
    import time

    import fixture_index
    from tilia_core import tql

    index = fixture_index.build_index(*json.loads(sys.argv[1]))
    start = time.monotonic()
    got = tql.run(index, sys.argv[2], time_limit=float(sys.argv[3]))
    print(
        json.dumps(
            {
                "stopped": got.stopped,
                "matches": len(got.matches),
                "rows": len(got.rows),
                "files": [row["file"] for row in got.rows],
                "elapsed": time.monotonic() - start,
            }
        )
    )
    """
)


def run_in_a_child(files, query, time_limit):
    """``tql.run`` in a process of its own, as ``sql_in_a_child`` does ``tql.sql``;
    the answer, ``None`` when the process was still running after CHILD_TIMEOUT
    seconds, or the text of the error it died of."""
    try:
        done = run_python(CHILD_RUN, json.dumps(files), query, str(time_limit))
    except subprocess.TimeoutExpired:
        return None
    if done.returncode != 0:
        return done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def children():
    """Every process of this section, run at once: if a time limit does not
    cover a regular expression each of them is held for CHILD_TIMEOUT seconds,
    and they would take that long one after the other."""
    pytest.importorskip("regex")
    cases = {("alone", name): case for name, case in ALONE.items()}
    cases.update({("some", name): case for name, case in AFTER_SOME.items()})
    with ThreadPoolExecutor(len(cases)) as pool:
        futures = {
            key: pool.submit(run_in_a_child, files, query, 0.5)
            for key, (files, query, _) in cases.items()
        }
        return {key: future.result() for key, future in futures.items()}


def answer_of(children, key):
    got = children[key]
    if got is None:
        pytest.fail(
            f"tql.run was still running {CHILD_TIMEOUT} s after it started with "
            "time_limit=0.5: the regular expression held the process, so the "
            "time limit does not cover it"
        )
    if isinstance(got, str):
        pytest.fail(f"tql.run raised in its process:\n{got}")
    return got


@pytest.mark.parametrize("way", WAYS)
def test_run_is_stopped_by_the_time_limit_in_a_pattern_that_backtracks_badly(
    children, way
):
    got = answer_of(children, ("alone", way))
    assert got["stopped"] == "time_limit"
    assert got["matches"] == 0
    assert got["rows"] == 0
    assert got["elapsed"] < 30


@pytest.mark.parametrize("way", WAYS)
def test_the_matches_found_before_a_pattern_ran_out_of_time_are_kept(children, way):
    got = answer_of(children, ("some", way))
    assert got["stopped"] == "time_limit"
    assert got["files"] == ["a1", "m5"]
    assert got["matches"] == got["rows"] == len(EARLY)
    assert got["elapsed"] < 30


# The same, in this process, on an engine that times out on the text "slow"


@pytest.mark.parametrize("way", WAYS)
def test_a_run_stopped_by_a_pattern_returns_the_matches_found_so_far(spy, way):
    got = run_scenario(SLOW[way], time_limit=60)
    assert got.stopped == "time_limit"
    assert files_of(got) == ["a1", "m5"]
    assert len(got.matches) == len(got.rows) == 2


@pytest.mark.parametrize("way", WAYS)
def test_a_run_with_a_pattern_that_ran_out_does_not_raise_and_finds_nothing(spy, way):
    got = run_scenario(SLOW_ALONE[way], time_limit=60)
    assert got.stopped == "time_limit"
    assert got.matches == []
    assert got.rows == []


@pytest.mark.parametrize("way", WAYS)
def test_a_run_whose_patterns_all_finish_has_no_stop_reason(spy, way):
    got = run_scenario(FINE[way], time_limit=60)
    assert got.stopped is None
    assert files_of(got) == FINE[way][2]


@pytest.mark.parametrize("way", WAYS)
def test_the_engine_is_given_the_time_left_of_a_run(spy, way):
    run_scenario(FINE[way], time_limit=60)
    assert spy.calls
    assert all(0 < c["timeout"] <= 60 + CLOCK_SLACK for c in spy.calls)


@pytest.mark.parametrize("way", WAYS)
def test_a_clock_that_does_not_move_gives_a_run_its_limit_up_to_rounding(
    spy, frozen_clock, way
):
    run_scenario(FINE[way], time_limit=60)
    assert spy.calls
    assert all(60 <= c["timeout"] <= 60 + CLOCK_SLACK for c in spy.calls)


@pytest.mark.parametrize("way", WAYS)
def test_without_a_time_limit_the_engine_is_given_no_timeout_by_run(spy, way):
    got = run_scenario(FINE[way])
    assert spy.calls
    assert all(c.get("timeout") is None for c in spy.calls)
    assert got.stopped is None
    assert files_of(got) == FINE[way][2]


@pytest.mark.parametrize("way", WAYS)
def test_the_budget_of_a_run_is_taken_off_when_it_ends(spy, way):
    run_scenario(FINE[way], time_limit=60)
    assert spy.calls
    assert timeout_given(spy) == NO_TIMEOUT
    run_scenario(SLOW[way], time_limit=60)  # ended by the pattern
    assert timeout_given(spy) == NO_TIMEOUT


@pytest.mark.parametrize("function", ["_pattern_matches", "_where_only"])
def test_the_budget_of_a_run_is_taken_off_when_it_fails(spy, monkeypatch, function):
    seen = []

    def fail_inside(*args, **kwargs):
        seen.append(timeout_given(spy))
        raise Boom

    monkeypatch.setattr(engine, function, fail_inside)
    query = "WHERE label ~ /o/" if function == "_where_only" else "/o/ IN form"
    index = fixture_index.build_index(FIXTURES["exposition"])
    with pytest.raises(Boom):
        tql.run(index, query, time_limit=60)
    assert len(seen) == 1 and 0 < seen[0] <= 60 + CLOCK_SLACK
    assert timeout_given(spy) == NO_TIMEOUT


def test_runs_on_two_threads_have_budgets_of_their_own(spy):
    spy.meeting = threading.Barrier(2, timeout=PATIENCE)
    limits = {"short": 30, "long": 3000}
    indexes = {n: fixture_index.build_index(FIXTURES["exposition"]) for n in limits}
    idents, errors = {}, []

    def work(name):
        idents[name] = threading.get_ident()
        try:
            tql.run(indexes[name], "/o/ IN form", time_limit=limits[name])
        except BaseException as err:
            errors.append(err)

    threads = [threading.Thread(target=work, args=(n,)) for n in limits]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2 * PATIENCE)
    spy.meeting = None
    assert errors == []
    given = {
        name: [c["timeout"] for c in spy.calls if c["thread"] == idents[name]]
        for name in limits
    }
    assert given["short"] and given["long"]
    assert all(0 < t <= 30 + CLOCK_SLACK for t in given["short"])
    assert all(30 < t <= 3000 + CLOCK_SLACK for t in given["long"])
    assert timeout_given(spy) == NO_TIMEOUT


# -- the engines agree, in the queries as in the SQL --------------------------

LABELS = [
    "Verse 1",
    "verse",
    "Chorus",
    "chorus",
    "Sätze",
    "Sätze",
    "café",
    "Bär",
    "A",
    "ab",
    "aab",
    "aaa",
    "",
]
PATTERNS = [
    r"^V",
    r"(?i)^v",
    r"1$",
    r"^(\w+) (\d)$",  # captures
    r"^(x)?(Verse)",  # a capture that takes no part
    r"(a|aa)+$",  # alternation
    r"ä",  # unicode
    r"\w+é",
    r"^$",  # the empty string
    r"a*",
    r"[A-G][#b]?",
    r"(?i)(chorus|verse)\b",
    r"^.{4}$",
    r"(.)\1",  # a back-reference
    r"[^a-z]",
]
FORMS = {
    "a pattern literal": "/{p}/ IN form",
    "a condition in brackets": "*[label ~ /{p}/] IN form",
    "~ on a unit": "* IN form WHERE label ~ /{p}/",
    "~ in a query of only WHERE": "WHERE label ~ /{p}/",
}


@pytest.fixture(scope="module")
def labels_index():
    units = [[label, 1, i, i + 1] for i, label in enumerate(LABELS)]
    return fixture_index.build_index(
        {
            "name": "f1",
            "length": len(LABELS),
            "timelines": [{"name": "Form (X)", "kind": "hierarchy", "units": units}],
        }
    )


def expected_hits(pattern):
    """(label, captured groups) of the labels ``re`` finds ``pattern`` in."""
    found = []
    for label in LABELS:
        match = re.search(pattern, nfc(label))
        if match:
            found.append((nfc(label), tuple(g or "" for g in match.groups())))
    return found


def hits(index, query, pattern):
    got = tql.run(index, query.format(p=pattern))
    assert got.stopped is None
    return [(nfc(m.slots[0][0].label), m.captures) for m in got.matches]


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("pattern", PATTERNS)
def test_a_pattern_finds_the_same_units_on_either_engine(
    labels_index, either_engine, form, pattern
):
    got = hits(labels_index, FORMS[form], pattern)
    want = expected_hits(pattern)
    assert want  # no pattern of the table is vacuous
    if "WHERE" in FORMS[form]:
        assert got == want  # the groups a ~ captured go to the match
    else:
        assert [label for label, _ in got] == [label for label, _ in want]


def test_the_table_of_patterns_is_big_enough():
    assert len(PATTERNS) >= 10
    assert any(re.compile(p).groups for p in PATTERNS)


def test_a_pattern_that_matches_nothing_finds_nothing_on_either_engine(
    labels_index, either_engine
):
    for form in FORMS.values():
        assert hits(labels_index, form, "zzz") == []


@pytest.mark.parametrize("pattern", ["(", "[a", "a{2,1}", "*", "(?P<n"])
@pytest.mark.parametrize("form", FORMS)
def test_a_bad_pattern_in_a_query_raises_a_tql_error_before_the_run_starts(
    labels_index, either_engine, form, pattern
):
    with pytest.raises(TQLError):
        tql.run(labels_index, FORMS[form].format(p=pattern), time_limit=60)


def test_a_pattern_that_is_data_falls_back_to_its_text_on_either_engine(either_engine):
    index = fixture_index.build_index(
        paired("f1", "a(b", "("),
        paired("f2", "x[a]", "[a"),
        paired("f3", "ab", "("),
        paired("f4", "abc", "(b)c"),  # a valid pattern is not read as text
    )
    got = tql.run(index, PAIR_QUERY)
    assert [m.slots[0][0].file_id for m in got.matches] == ["f1", "f2", "f4"]
    assert [m.captures for m in got.matches] == [(), (), ("b",)]


def test_a_pattern_that_is_data_falls_back_to_its_text_with_a_time_limit(
    strict_spy,
):
    index = fixture_index.build_index(paired("f1", "a(b", "("))
    got = tql.run(index, PAIR_QUERY, time_limit=60)
    assert [m.slots[0][0].file_id for m in got.matches] == ["f1"]
    assert strict_spy.compiled == [r"\("]
    assert all(0 < c["timeout"] <= 60 + CLOCK_SLACK for c in strict_spy.calls)


def test_the_text_a_pattern_falls_back_to_is_bounded_by_the_time_limit(strict_spy):
    # the first search fails to compile, the second is made on the escaped text
    index = fixture_index.build_index(paired("f1", "slow (", "("))
    got = tql.run(index, PAIR_QUERY, time_limit=60)
    assert got.stopped == "time_limit"
    assert got.matches == []


def test_a_search_in_a_condition_goes_through_the_regexes_module(strict_spy):
    caps = []
    assert values._search("(a)(b)", "xab", caps) is True
    assert caps == ["a", "b"]
    assert values._search("^(c)?b", "b", caps) is True
    assert caps == [""]
    assert strict_spy.compiled == ["(a)(b)", "^(c)?b"]


def test_a_bad_pattern_in_a_condition_raises_the_error_of_its_engine(either_engine):
    with pytest.raises(regexes.PatternError):
        values._search("(", "a", None)
    assert values._search("(", "a(", None, literal=True) is True
    assert values._search("(", "ab", None, literal=True) is False


def test_pattern_error_holds_the_errors_of_the_engine_in_use():
    assert regexes.PatternError[0] is re.error
    if regexes.HAS_TIMEOUT:
        import regex

        assert regexes.PatternError == (re.error, regex.error)
        assert not issubclass(regex.error, re.error)
    else:
        assert regexes.PatternError == (re.error,)


BLOCK_REGEX_RUNS = BLOCK_REGEX + textwrap.dedent(
    """
        from tilia_core.tql import values

        print(regexes.PatternError == (re.error,))
        print(values._search("(", "a(b", None, literal=True))
        """
)


def test_without_the_regex_package_a_literal_comparison_still_falls_back_to_text():
    done = run_python(BLOCK_REGEX_RUNS)
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["False", "True", "1", "True", "True"]


# -- the fallback on re -------------------------------------------------------


@pytest.mark.usefixtures("without_the_extra")
@pytest.mark.parametrize("way", WAYS)
def test_without_the_extra_run_still_answers_with_or_without_a_time_limit(way):
    for limits in ({}, {"time_limit": 60}):
        got = run_scenario(FINE[way], **limits)
        assert got.stopped is None
        assert files_of(got) == FINE[way][2]


@pytest.mark.usefixtures("without_the_extra")
@pytest.mark.parametrize("way", WAYS)
def test_without_the_extra_the_budget_of_a_run_is_never_asked(way, monkeypatch):
    asked = []
    monkeypatch.setattr(Limits, "seconds_left", lambda self: asked.append(1) or 0.0)
    got = run_scenario(FINE[way], time_limit=60)
    assert asked == []
    assert got.stopped is None


@pytest.mark.parametrize("way", WAYS)
def test_with_a_short_label_the_answer_is_right_on_either_engine(either_engine, way):
    for late, matches in (("a" * 12, True), (SHORT_TEXT, False)):
        case = scenarios(CATASTROPHIC, EARLY, late)[way]
        for limits in ({}, {"time_limit": 60}):
            got = run_scenario(case, **limits)
            assert got.stopped is None
            assert files_of(got) == case[2] + (["z9"] if matches else [])


def test_the_docstring_of_run_says_where_the_limits_do_not_cover_regexes():
    doc = " ".join(tql.run.__doc__.split())
    assert "``regex`` package" in doc
    assert 'pip install "tilia-core[regex]"' in doc
    assert "a regular expression is bounded by ``time_limit``" in doc
    assert "though not to the instant" in doc
    assert "``cancel`` cannot interrupt a regular expression that is running" in doc
    assert re.search(
        r"[Ww]ithout the ``regex`` package, neither limit covers a regular "
        r"expression, and a pattern that backtracks badly can hold the whole "
        r"process",
        doc,
    )
    lower = doc.lower()
    assert "regex" in lower and "approximate" in lower and "cancel" in lower


def test_the_docstring_of_run_keeps_what_it_said_before():
    doc = " ".join(tql.run.__doc__.split())
    assert "``max_matches`` means some N matches" in doc
    assert "A stopped run does not raise" in doc
    assert "Raises ``RuntimeError``" in doc


# -- Limits as the budget of a call -------------------------------------------


def test_limits_have_no_seconds_left_without_a_time_limit():
    assert Limits(None, None).seconds_left() is None
    assert Limits(None, threading.Event()).seconds_left() is None


@pytest.mark.parametrize("time_limit", [0, 0.0, -1, -1e9])
def test_limits_never_have_a_negative_number_of_seconds_left(time_limit):
    limits = Limits(time_limit, None)
    time.sleep(0.01)
    assert limits.seconds_left() == 0.0


def test_a_regular_expression_that_ran_out_does_not_overwrite_an_earlier_reason():
    event = threading.Event()
    event.set()
    limits = Limits(None, event)
    assert limits.check() is True
    limits.ran_out()
    assert limits.stopped == "cancelled"
    limits = Limits(0, None)
    assert limits.check() is True
    limits.ran_out()
    assert limits.stopped == "time_limit"
    limits = Limits(None, None)
    limits.ran_out()
    limits.ran_out()
    assert limits.stopped == "time_limit"


def test_a_regex_timeout_ended_the_call_by_the_time_limit():
    assert Limits(None, None).reason_of(regexes.RegexTimeout("out")) == "time_limit"
    assert Limits(60, None).reason_of(regexes.RegexTimeout()) == "time_limit"


def test_a_regex_timeout_after_a_cancel_ends_the_call_as_the_cancel_did():
    limits = Limits(None, None)
    limits.stopped = "cancelled"
    assert limits.reason_of(regexes.RegexTimeout()) == "cancelled"


def test_the_other_reasons_a_call_can_end_by_are_unchanged():
    limits = Limits(None, None)
    assert limits.reason_of(Stopped("cancelled")) == "cancelled"
    with pytest.raises(Boom):
        limits.reason_of(Boom())
    error = sqlite3.OperationalError("interrupted")
    with pytest.raises(sqlite3.OperationalError):
        limits.reason_of(error)  # nothing stopped the call
    limits.stopped = "time_limit"
    assert limits.reason_of(error) == "time_limit"


# -- packaging ----------------------------------------------------------------


def pyproject():
    with open(CORE / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def test_regex_is_an_optional_extra_of_tilia_core():
    extra = pyproject()["project"]["optional-dependencies"]["regex"]
    assert len(extra) == 1
    assert extra[0].startswith("regex>=")


def test_the_dev_group_has_the_same_requirement_so_development_tests_the_timeout():
    data = pyproject()
    extra = data["project"]["optional-dependencies"]["regex"]
    assert extra[0] in data["dependency-groups"]["dev"]


def test_regex_is_never_a_dependency_of_tilia_core():
    dependencies = pyproject()["project"].get("dependencies", [])
    assert not [d for d in dependencies if re.match(r"regex\b", d, re.IGNORECASE)]


def test_check_packages_mentions_installing_the_regex_extra():
    text = CHECK_SCRIPT.read_text(encoding="utf-8")
    assert re.search(r'f"\{\w+\}\[regex\]"', text)
    assert "tilia-core with the regex extra: tests pass" in text
    assert "HAS_TIMEOUT" in text


@pytest.fixture
def script(monkeypatch):
    """scripts/check_packages.py as a module, with its steps recorded instead
    of run: ``script.steps`` is a list of ``(args, label)``."""
    spec = importlib.util.spec_from_file_location("check_packages", CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.steps = []

    def record(args, cwd, label):
        module.steps.append((args, label))
        if label == "build both wheels":
            wheel_dir = Path(args[args.index("--wheel-dir") + 1])
            wheel_dir.mkdir(parents=True)
            (wheel_dir / "tilia_core-0.0.1-py3-none-any.whl").touch()
            (wheel_dir / "tilia_library-0.0.1-py3-none-any.whl").touch()

    monkeypatch.setattr(module, "run", record)
    monkeypatch.setattr(module.venv, "create", lambda *args, **kwargs: None)
    return module


def test_check_packages_installs_the_core_wheel_with_the_extra_in_a_second_environment(
    script, tmp_path
):
    wheel = tmp_path / "tilia_core-0.0.1-py3-none-any.whl"
    script.check_core_with_regex(wheel, tmp_path)
    install, probe, tests = script.steps
    assert f"{wheel}[regex]" in install[0]  # one argument, for Windows
    assert "pytest" in install[0]
    assert probe[0][-2:] == ["-c", script.REGEX_IN_USE]
    assert probe[0][0] == install[0][0]
    assert tests[0][:3] == [install[0][0], "-m", "pytest"]
    assert tests[1] == "tilia-core with the regex extra: tests pass"


def test_check_packages_probe_fails_unless_regex_is_in_use(
    script, with_the_extra, monkeypatch
):
    exec(script.REGEX_IN_USE, {})
    monkeypatch.setattr(regexes, "HAS_TIMEOUT", False)
    with pytest.raises(AssertionError):
        exec(script.REGEX_IN_USE, {})


def test_check_packages_checks_that_the_plain_core_environment_has_no_regex(
    script, tmp_path
):
    wheel = tmp_path / "tilia_core-0.0.1-py3-none-any.whl"
    script.check_package("tilia-core", [wheel], tmp_path, optional=("regex",))
    absent = [a for a, label in script.steps if label == "tilia-core: regex is absent"]
    assert len(absent) == 1
    assert absent[0][1:] == ["-c", script.FIND_SPEC, "regex"]
    assert script.steps[-1][1] == "tilia-core: tests pass"
    script.steps.clear()
    script.check_package("tilia-library", [wheel], tmp_path)
    assert not [label for _, label in script.steps if "regex" in label]


def test_check_packages_tests_the_core_both_ways_and_the_library_as_before(script):
    calls = []
    script.check_package = lambda name, wheels, tmp, **kw: calls.append(
        (name, [w.name for w in wheels], kw)
    )
    script.check_core_with_regex = lambda core, tmp: calls.append(
        ("with the regex extra", core.name, {})
    )
    script.pip_python = lambda tmp: "python"
    assert script.main() == 0
    core, library = (
        "tilia_core-0.0.1-py3-none-any.whl",
        "tilia_library-0.0.1-py3-none-any.whl",
    )
    assert calls == [
        ("tilia-core", [core], {"optional": ("regex",)}),
        ("with the regex extra", core, {}),
        ("tilia-library", [core, library], {}),
    ]
