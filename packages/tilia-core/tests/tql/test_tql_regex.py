"""Regular expressions in SQL: ``REGEXP`` runs on the optional ``regex`` package
when it is installed, which gives a user's pattern a time limit, and on ``re``
when it is not (``tilia_core.tql.regexes``)."""

import importlib.util
import json
import os
import re
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import examples
import fixture_index
import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from tilia_core import tql
from tilia_core.tql import regexes, sqlfuncs
from tilia_core.tql.readonly import _Limits
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

    def compile(self, pattern):
        self.compiled.append(pattern)
        return SpyPattern(self, pattern)


class SpyPattern:
    def __init__(self, engine, pattern):
        self.engine = engine
        self.pattern = pattern

    def search(self, text, **kwargs):
        self.engine.calls.append({"thread": threading.get_ident(), **kwargs})
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
    assert _Limits(None, None).seconds_left() is None
    assert 0 < _Limits(60, None).seconds_left() <= 60 + CLOCK_SLACK
    passed = _Limits(0, None)
    time.sleep(0.02)
    assert passed.seconds_left() == 0.0


def test_a_regular_expression_that_ran_out_records_a_time_limit_unless_stopped():
    limits = _Limits(None, None)
    limits.ran_out()
    assert limits.stopped == "time_limit"
    limits = _Limits(None, None)
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
