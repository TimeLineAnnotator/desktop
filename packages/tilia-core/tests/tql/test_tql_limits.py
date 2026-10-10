"""The limits of a run: ``max_matches``, ``time_limit`` and ``cancel``."""

import threading
import time
import types

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import engine, readonly

FIXTURES = examples.load()["fixtures"]
QUERY = "a THEN b IN form"
HARMONY_QUERY = "V7 IN harmony"
PATIENCE = 60  # seconds a thread waits for another on a loaded machine


def big_fixture(k, units=300):
    """A file of ``units`` contiguous level-1 units, a ``b`` every third."""
    return {
        "name": f"g{k:02d}",
        "length": units,
        "timelines": [
            {
                "name": "Form (X)",
                "kind": "hierarchy",
                "units": [["a" if i % 3 else "b", 1, i, i + 1] for i in range(units)],
            },
            {
                "name": "Cadences",
                "kind": "marker",
                "units": [["PAC", i * 5 + 0.5] for i in range(units // 5)],
            },
        ],
    }


@pytest.fixture(scope="module")
def big_index():
    return fixture_index.build_index(*[big_fixture(k) for k in range(12)])


@pytest.fixture(scope="module")
def full(big_index):
    return tql.run(big_index, QUERY)


@pytest.fixture(scope="module")
def harmony_index():
    """Eight files of chords and keys, each with a name of its own."""
    return fixture_index.build_index(
        *[dict(FIXTURES["harmony"], name=f"h{k:02d}") for k in range(8)]
    )


@pytest.fixture(scope="module")
def harmony_full(harmony_index):
    return tql.run(harmony_index, HARMONY_QUERY)


@pytest.fixture(scope="module")
def listing_index():
    """Forty files with a composer and a hierarchy timeline each, for the
    queries of only ``WHERE`` that list timelines and files."""
    return fixture_index.build_index(
        *[
            {
                "name": f"l{k:02d}",
                "length": 4,
                "fields": {"composer": "Mozart"},
                "timelines": [
                    {
                        "name": "Form (X)",
                        "kind": "hierarchy",
                        "units": [["a", 1, 0, 4]],
                    }
                ],
            }
            for k in range(40)
        ]
    )


def keys(result):
    return [m.key for m in result.matches]


class SteppingClock:
    """Stands in for the ``time`` module that the limits read: each read moves
    the clock on by 1 ms, so a time limit falls at a known point of the run on
    any machine. A full run of ``QUERY`` on ``big_index`` reads it about 2,000
    times."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        self.now += 0.001
        return self.now


class ManualClock:
    """Stands in for the ``time`` module that the limits read: it only moves
    when a test sets ``now``."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


def watch_calls(monkeypatch, name, on_call=None):
    """Count the calls of ``engine.<name>``; ``on_call(n)`` runs after the
    ``n``-th one has returned."""
    calls = types.SimpleNamespace(n=0)
    original = getattr(engine, name)

    def counting(*args, **kwargs):
        calls.n += 1
        out = original(*args, **kwargs)
        if on_call is not None:
            on_call(calls.n)
        return out

    monkeypatch.setattr(engine, name, counting)
    return calls


def watch_the_warnings_pass(monkeypatch, on_resolve=None):
    """Record the files whose lanes are resolved inside the warnings pass
    (``engine._harmony_warnings``); ``on_resolve(n)`` runs after the ``n``-th
    resolution inside it."""
    seen = types.SimpleNamespace(resolved=[], inside=False)
    resolve = engine.tql_compile.resolve_lanes
    warnings_pass = engine._harmony_warnings

    def counting_resolve(con, file_id, lane):
        out = resolve(con, file_id, lane)
        if seen.inside:
            seen.resolved.append(file_id)
            if on_resolve is not None:
                on_resolve(len(seen.resolved))
        return out

    def counting_pass(*args, **kwargs):
        seen.inside = True
        try:
            return warnings_pass(*args, **kwargs)
        finally:
            seen.inside = False

    monkeypatch.setattr(engine.tql_compile, "resolve_lanes", counting_resolve)
    monkeypatch.setattr(engine, "_harmony_warnings", counting_pass)
    return seen


class PausingEvent(threading.Event):
    """A cancel event that holds the run at its ``n``-th check until another
    thread has set it, so the cancel lands mid-run on any machine."""

    def __init__(self, n: int) -> None:
        super().__init__()
        self.n = n
        self.checks = 0
        self.paused = threading.Event()

    def is_set(self) -> bool:
        self.checks += 1
        if self.checks == self.n:
            self.paused.set()
            self.wait(PATIENCE)
        return super().is_set()


def cancel_from_another_thread(cancel: PausingEvent) -> threading.Thread:
    """Start the thread that sets ``cancel`` once the run is held at its check."""

    def set_once_paused() -> None:
        if cancel.paused.wait(PATIENCE):
            cancel.set()

    other = threading.Thread(target=set_once_paused)
    other.start()
    return other


class TestNoLimitByDefault:
    def test_a_run_without_limits_is_not_stopped(self, full):
        assert full.stopped is None
        assert len(full.matches) == 12 * 99

    def test_none_means_no_limit(self, big_index, full):
        got = tql.run(big_index, QUERY, max_matches=None, time_limit=None)
        assert got.stopped is None and keys(got) == keys(full)


class TestMaxMatches:
    def test_stops_at_the_limit_with_the_matches_so_far(self, big_index, full):
        got = tql.run(big_index, QUERY, max_matches=150)
        assert got.stopped == "max_matches"
        assert len(got.matches) == len(got.rows) == 150
        assert keys(got) == keys(full)[:150]

    def test_a_limit_equal_to_the_matches_is_not_a_stop(self, big_index, full):
        got = tql.run(big_index, QUERY, max_matches=len(full.matches))
        assert got.stopped is None and len(got.matches) == len(full.matches)

    def test_a_limit_stops_early(self, big_index):
        start = time.monotonic()
        tql.run(big_index, QUERY, max_matches=10)
        assert time.monotonic() - start < 1.0

    def test_zero_matches(self, big_index):
        got = tql.run(big_index, QUERY, max_matches=0)
        assert got.stopped == "max_matches" and got.matches == [] and got.rows == []

    def test_a_query_of_only_where_lists_up_to_the_limit(self, big_index):
        got = tql.run(big_index, "WHERE start > 0", max_matches=7)
        assert got.stopped == "max_matches" and len(got.rows) == 7

    def test_a_relation_stops_at_the_limit(self, big_index):
        got = tql.run(big_index, "PAC IN cadences DURING a IN form", max_matches=5)
        assert got.stopped == "max_matches" and len(got.rows) == 5


class TestTimeLimit:
    def test_stops_with_the_matches_so_far(self, big_index, full, monkeypatch):
        monkeypatch.setattr(readonly, "time", SteppingClock())
        got = tql.run(big_index, QUERY, time_limit=1.0)
        assert got.stopped == "time_limit"
        assert 0 < len(got.matches) == len(got.rows) < len(full.matches)
        assert keys(got) == keys(full)[: len(got.matches)]

    def test_a_zero_limit_stops_at_once(self, big_index):
        got = tql.run(big_index, QUERY, time_limit=0)
        assert got.stopped == "time_limit" and got.rows == []

    def test_a_generous_limit_is_not_a_stop(self, big_index, full):
        got = tql.run(big_index, QUERY, time_limit=60)
        assert got.stopped is None and len(got.matches) == len(full.matches)

    def test_stops_a_relation_and_a_where(self, big_index):
        for query in ("PAC IN cadences DURING a IN form", "* IN form WHERE label = a"):
            got = tql.run(big_index, query, time_limit=0)
            assert got.stopped == "time_limit" and got.rows == []

    def test_stops_a_query_of_only_where(self, big_index):
        got = tql.run(big_index, "WHERE start > 0", time_limit=0)
        assert got.stopped == "time_limit"

    def test_leaves_no_progress_handler_behind(self, big_index):
        tql.run(big_index, QUERY, time_limit=0)
        con = big_index.connection()
        assert con.execute(
            "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n "
            "WHERE x < 300000) SELECT count(*) FROM n"
        ).fetchone() == (300000,)


class TestCancel:
    def test_set_before_the_run(self, big_index):
        cancel = threading.Event()
        cancel.set()
        got = tql.run(big_index, QUERY, cancel=cancel)
        assert got.stopped == "cancelled" and got.matches == [] and got.rows == []

    def test_an_unset_event_changes_nothing(self, big_index, full):
        got = tql.run(big_index, QUERY, cancel=threading.Event())
        assert got.stopped is None and keys(got) == keys(full)

    def test_set_from_another_thread_during_a_long_run(self, big_index, full):
        cancel = PausingEvent(1000)

        other = cancel_from_another_thread(cancel)
        got = tql.run(big_index, QUERY, cancel=cancel)
        other.join(PATIENCE)
        assert cancel.paused.is_set()
        assert got.stopped == "cancelled"
        assert 0 < len(got.matches) == len(got.rows) < len(full.matches)
        assert keys(got) == keys(full)[: len(got.matches)]

    def test_a_cancelled_run_leaves_the_index_usable(self, big_index, full):
        cancel = threading.Event()
        cancel.set()
        tql.run(big_index, QUERY, cancel=cancel)
        assert tql.run(big_index, "PAC IN cadences", max_matches=3).stopped


class TestRowsAfterAStop:
    def test_a_stop_still_gives_rows_for_a_where(self, big_index):
        got = tql.run(big_index, "* IN form WHERE label = a", max_matches=4)
        assert got.stopped == "max_matches"
        assert [r["label"] for r in got.rows] == ["a"] * 4


class TestWarningsPass:
    def test_a_cancel_set_before_the_run_resolves_no_lane(
        self, harmony_index, monkeypatch
    ):
        cancel = threading.Event()
        cancel.set()
        seen = watch_the_warnings_pass(monkeypatch)
        got = tql.run(harmony_index, HARMONY_QUERY, cancel=cancel)
        assert got.stopped == "cancelled"
        assert seen.resolved == []

    def test_a_cancel_in_the_middle_ends_the_pass_and_keeps_the_rows(
        self, harmony_index, harmony_full, monkeypatch
    ):
        assert harmony_full.stopped is None and len(harmony_full.matches) == 32
        cancel = threading.Event()
        seen = watch_the_warnings_pass(
            monkeypatch, lambda n: cancel.set() if n == 3 else None
        )
        got = tql.run(harmony_index, HARMONY_QUERY, cancel=cancel)
        assert len(seen.resolved) == 3
        assert got.stopped == "cancelled"
        assert len(got.matches) == len(got.rows) == len(harmony_full.matches)
        assert keys(got) == keys(harmony_full)

    def test_a_time_limit_of_zero_resolves_no_lane(self, harmony_index, monkeypatch):
        seen = watch_the_warnings_pass(monkeypatch)
        got = tql.run(harmony_index, HARMONY_QUERY, time_limit=0)
        assert got.stopped == "time_limit"
        assert seen.resolved == []

    def test_a_time_limit_in_the_middle_ends_the_pass_and_keeps_the_rows(
        self, harmony_index, harmony_full, monkeypatch
    ):
        clock = ManualClock()
        monkeypatch.setattr(readonly, "time", clock)
        seen = watch_the_warnings_pass(
            monkeypatch, lambda n: setattr(clock, "now", 100.0) if n == 3 else None
        )
        got = tql.run(harmony_index, HARMONY_QUERY, time_limit=10)
        assert len(seen.resolved) == 3
        assert got.stopped == "time_limit"
        assert len(got.matches) == len(got.rows) == len(harmony_full.matches)
        assert keys(got) == keys(harmony_full)

    def test_the_pass_is_not_cut_by_max_matches(self, harmony_index, monkeypatch):
        seen = watch_the_warnings_pass(monkeypatch)
        got = tql.run(harmony_index, HARMONY_QUERY, max_matches=2)
        assert got.stopped == "max_matches"
        assert len(got.matches) == len(got.rows) == 2
        assert seen.resolved == [f"h{k:02d}" for k in range(8)]

    def test_a_complete_run_resolves_every_file_once(self, harmony_index, monkeypatch):
        seen = watch_the_warnings_pass(monkeypatch)
        got = tql.run(harmony_index, HARMONY_QUERY)
        assert got.stopped is None
        assert seen.resolved == [f"h{k:02d}" for k in range(8)]


class TestRowsUnderLimits:
    def test_a_cancel_in_the_middle_of_the_rows_stops_them(
        self, big_index, full, monkeypatch
    ):
        cancel = threading.Event()
        built = watch_calls(
            monkeypatch, "_row", lambda n: cancel.set() if n == 10 else None
        )
        got = tql.run(big_index, QUERY, cancel=cancel)
        assert got.stopped == "cancelled"
        assert 10 <= len(got.rows) < len(full.rows) // 2
        assert len(got.matches) == len(got.rows)
        assert keys(got) == keys(full)[: len(got.rows)]
        assert built.n == len(got.rows)

    def test_a_cancel_in_the_middle_of_the_rows_wins_over_max_matches(
        self, big_index, full, monkeypatch
    ):
        cancel = threading.Event()
        built = watch_calls(
            monkeypatch, "_row", lambda n: cancel.set() if n == 10 else None
        )
        got = tql.run(big_index, QUERY, max_matches=150, cancel=cancel)
        assert got.stopped == "cancelled"
        assert len(got.matches) == len(got.rows) == built.n == 10

    @pytest.mark.parametrize(
        "query, grain, builder",
        [
            ("WHERE tl.kind = hierarchy", "timeline", "_timeline_row"),
            ("WHERE file.composer = Mozart", "file", "_file_row"),
        ],
    )
    def test_a_cancel_in_the_middle_of_the_rows_of_a_listing(
        self, listing_index, monkeypatch, query, grain, builder
    ):
        full = tql.run(listing_index, query)
        assert full.grain == grain and len(full.rows) == 40
        cancel = threading.Event()
        built = watch_calls(
            monkeypatch, builder, lambda n: cancel.set() if n == 5 else None
        )
        got = tql.run(listing_index, query, cancel=cancel)
        assert got.stopped == "cancelled"
        assert 5 <= len(got.rows) < 20
        assert len(got.matches) == len(got.rows)
        assert keys(got) == keys(full)[: len(got.rows)]
        assert built.n == len(got.rows)

    def test_a_cancel_that_stopped_the_search_keeps_the_rows_it_found(
        self, big_index, monkeypatch
    ):
        cancel = PausingEvent(1000)
        built = watch_calls(monkeypatch, "_row")

        other = cancel_from_another_thread(cancel)
        got = tql.run(big_index, QUERY, cancel=cancel)
        other.join(PATIENCE)
        assert got.stopped == "cancelled"
        assert 0 < len(got.matches) == len(got.rows)
        assert built.n == len(got.rows)

    def test_a_time_limit_that_stopped_the_search_keeps_the_rows_it_found(
        self, big_index, monkeypatch
    ):
        monkeypatch.setattr(readonly, "time", SteppingClock())
        built = watch_calls(monkeypatch, "_row")
        got = tql.run(big_index, QUERY, time_limit=1.0)
        assert got.stopped == "time_limit"
        assert 0 < len(got.matches) == len(got.rows)
        assert built.n == len(got.rows)

    def test_a_time_limit_that_falls_while_the_rows_are_built_does_not_cut_them(
        self, big_index, monkeypatch
    ):
        clock = ManualClock()
        monkeypatch.setattr(readonly, "time", clock)
        built = watch_calls(
            monkeypatch,
            "_row",
            lambda n: setattr(clock, "now", 100.0) if n == 5 else None,
        )
        got = tql.run(big_index, QUERY, max_matches=60, time_limit=10)
        assert got.stopped == "max_matches"
        assert len(got.matches) == len(got.rows) == built.n == 60


class TestSql:
    LONG = (
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
        "SELECT x FROM n"
    )

    def test_max_rows(self, big_index):
        got = tql.sql(big_index, "SELECT id FROM components", max_rows=25)
        assert got.stopped == "max_rows" and len(got.rows) == 25

    def test_time_limit_returns_the_rows_so_far(self, big_index):
        start = time.monotonic()
        got = tql.sql(big_index, self.LONG, time_limit=0.2)
        assert time.monotonic() - start < 1.5
        assert got.stopped == "time_limit" and got.columns == ["x"]

    def test_a_time_limit_interrupts_a_statement_that_never_returns_a_row(
        self, big_index
    ):
        got = tql.sql(
            big_index,
            "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
            "SELECT x FROM n WHERE x < 0",
            time_limit=0.2,
        )
        assert got.stopped == "time_limit" and got.rows == []

    def test_cancel_set_before(self, big_index):
        cancel = threading.Event()
        cancel.set()
        assert tql.sql(big_index, self.LONG, cancel=cancel).stopped == "cancelled"

    def test_cancel_from_another_thread(self, big_index):
        cancel = threading.Event()
        timer = threading.Timer(0.2, cancel.set)
        timer.start()
        start = time.monotonic()
        try:
            got = tql.sql(big_index, self.LONG, cancel=cancel)
        finally:
            timer.cancel()
        assert time.monotonic() - start < 1.5
        assert got.stopped == "cancelled"

    def test_a_statement_that_fails_still_raises(self, big_index):
        with pytest.raises(tql.TQLError):
            tql.sql(big_index, "SELECT * FROM nope", time_limit=5)
