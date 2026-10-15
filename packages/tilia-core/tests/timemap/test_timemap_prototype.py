"""The prototype's time-map self-test, ported to documents in the new format.

The prototype is `scripts/ql_timemap.py` in MusicalForm/tla-corpus-ui, at
1db7524. Its `_selftest` builds maps from TiLiA's arrays (the beat times, the
beats in each measure, the printed numbers); here each map is a beat timeline
whose measures are marked on their first beats, through `docs.py`. The
assertions follow the prototype's, block for block, through helpers named after
its methods. Where WP9's spec changes an expectation, a comment says so.

The prototype's `snap` and `is_downbeat`'s `tol` are one tolerance in the core,
`TimeMap.tolerance`, which reads `timemap.TOLERANCE`: an assertion that passes
another value sets it for that assertion.

Left out:
- The constructor's `ValueError` cases. Arrays that disagree with each other
  can't be written as marks, and one beat or two beats at the same time give no
  time map (`test_timemap_no_time_map`).
- `from_timeline`'s cases on how TiLiA loads an old file: fitting the arrays to
  the beats, refusing arrays it can't load, sorting the beats, and dropping a
  beat at a time already taken, or at a negative, infinite or non-numeric time.
  Old files are converted by WP3's migration, which follows the prototype
  there. So are `pick_time_map`'s old kind names and `display_position`.
- The real files of `_selftest_real_files`, which aren't in this repository.
  Their check of every beat runs on the maps here
  (`test_every_beat_reads_back_its_measure`).
"""

from __future__ import annotations

import contextlib
import itertools
import math

import pytest

from docs import beat_timeline, document
from tilia_core import tla
from tilia_core.timemap import TimeMap, find_time_map, time_map_for
from tilia_core.timemap import timemap as timemap_module

T44 = [1.0 + 0.5 * i for i in range(12)]  # 4/4, bars 1-3: downbeats 1.0, 3.0, 5.0


def _map(times: list[float], counts: list[int], numbers: list[int]) -> TimeMap:
    """The time map of the prototype's arrays: a beat at each time, and a mark
    with its number on each measure's first beat."""
    assert sum(counts) == len(times) and len(counts) == len(numbers)
    firsts = itertools.accumulate(counts[:-1], initial=0)
    marks = {
        first: {"number": number} for first, number in zip(firsts, numbers, strict=True)
    }
    timeline = beat_timeline(
        [{"time": t, "measure": marks.get(k)} for k, t in enumerate(times)]
    )
    time_map = time_map_for(document(timeline), timeline.id)
    assert time_map is not None
    return time_map


def _close(a: float | None, b: float, tol: float = 1e-9) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


@contextlib.contextmanager
def _tolerance(monkeypatch: pytest.MonkeyPatch, value: float):
    with monkeypatch.context() as patch:
        patch.setattr(timemap_module, "TOLERANCE", value)
        yield


# The prototype's lookups, each from the core's positions of a point at `t`.


def _start_field(name: str):
    def lookup(time_map: TimeMap, t: float | None):
        positions = time_map.positions(t, t)
        return None if positions is None else getattr(positions, name)

    return lookup


bar = _start_field("bar")
beat = _start_field("beat")
pass_of = _start_field("pass_")
bar_count = _start_field("bar_count")
bar_label = _start_field("bar_label")
measure_beats = _start_field("bar_beat_count")


def is_downbeat(time_map: TimeMap, t: float | None) -> bool:
    positions = time_map.positions(t, t)
    return positions is not None and positions.downbeat


def end_bar(time_map: TimeMap, end: float) -> int | None:
    """The prototype's `end_bar(end)`, which takes no start: where a span from
    the first beat to `end` ends."""
    return time_map.positions(time_map.start, end).end_bar


def measures(time_map: TimeMap) -> list[tuple[float, float, int, int]]:
    """The prototype's `measures()`: (start, end, number, beats) per measure."""
    return [(r.start, r.end, r.number, r.beats) for r in time_map.measure_rows()]


# Distances. The prototype's position, length, beat_seconds and bar_seconds
# are the core's position, length and unit_seconds. Its beat_pos and
# measure_pos are position(t, unit) everywhere but on the closing barline,
# where no assertion here looks.


def beat_pos(time_map: TimeMap, t: float) -> float | None:
    return time_map.position(t, "beat")


def measure_pos(time_map: TimeMap, t: float) -> float | None:
    return time_map.position(t, "bar")


def position(time_map: TimeMap, t: float, unit: str = "bar") -> float | None:
    return time_map.position(t, unit)


def length(
    time_map: TimeMap, start: float, end: float, unit: str = "bar"
) -> float | None:
    return time_map.length(start, end, unit)


def beat_seconds(time_map: TimeMap, t: float) -> float | None:
    return time_map.unit_seconds(t, "beat")


def bar_seconds(time_map: TimeMap, t: float) -> float | None:
    return time_map.unit_seconds(t, "bar")


# --- 4/4, three bars, a beat every 0.5 s from 1.0 s -------------------------


def test_four_four():
    tm = _map(T44, [4, 4, 4], [1, 2, 3])

    assert (tm.start, tm.end) == (1.0, 7.0)
    assert [bar(tm, t) for t in (1.0, 2.85, 3.0, 4.75, 5.0, 6.8)] == [1, 1, 2, 2, 3, 3]
    assert beat(tm, 1.0) == 1.0 and beat(tm, 3.0) == 1.0 and beat(tm, 4.5) == 4.0
    # positions between beats are fractional, not rounded
    assert _close(beat(tm, 1.25), 1.5) and _close(beat(tm, 1.75), 2.5)
    assert _close(beat(tm, 4.25), 3.5) and _close(beat(tm, 2.85), 4.7)
    assert (bar_count(tm, 4.0), bar_label(tm, 4.0), pass_of(tm, 4.0)) == (2, "2", 1)
    # before the first beat: nothing, unless within the snap
    assert bar(tm, 0.85) is None and beat(tm, 0.5) is None
    assert pass_of(tm, 0.0) is None
    assert bar(tm, 0.95) == 1 and beat(tm, 0.95) == 1.0
    # a start a little before a downbeat is on it (snapping)
    assert bar(tm, 2.95) == 2 and beat(tm, 2.95) == 1.0 and bar_count(tm, 2.95) == 2
    # end exclusion: a span ending on the downbeat of bar 2 ends in bar 1
    assert end_bar(tm, 3.0) == 1 and end_bar(tm, 3.0 + 1e-9) == 1
    assert end_bar(tm, 3.04) == 1 and end_bar(tm, 2.96) == 1  # snapped onto it
    assert end_bar(tm, 3.2) == 2 and end_bar(tm, 4.0) == 2
    # Changed (WP9's spec, FR-030): an end that, once both ends are snapped,
    # isn't after the start ends in the start's bar, here bar 1. The prototype
    # gives no end_bar for an end on the first beat.
    assert end_bar(tm, 1.0) == 1 and end_bar(tm, 1.05) == 1
    # After the last beat (6.5), the last bar lasts one more beat: the gap
    # before it (FR-011). The prototype gets the same end from the beat
    # pattern, as the bar holds all four of its beats.
    assert _close(beat(tm, 6.8), 4.6)
    assert bar(tm, 7.0) is None and bar(tm, 7.5) is None
    assert bar(tm, 6.95) is None  # on the closing barline: past the map
    assert end_bar(tm, 7.0) == 3 and end_bar(tm, 7.05) == 3
    assert end_bar(tm, 7.2) is None


def test_four_four_distances():
    tm = _map(T44, [4, 4, 4], [1, 2, 3])

    assert beat_pos(tm, 1.0) == 0.0 and _close(beat_pos(tm, 6.75), 11.5)
    assert measure_pos(tm, 5.0) == 2.0 and _close(measure_pos(tm, 6.0), 2.5)
    assert _close(measure_pos(tm, 6.75), 2.875) and _close(measure_pos(tm, 2.0), 0.5)
    assert beat_pos(tm, 0.0) is None and measure_pos(tm, 8.0) is None
    assert _close(beat_seconds(tm, 2.2), 0.5) and _close(bar_seconds(tm, 2.2), 2.0)
    assert _close(bar_seconds(tm, 6.8), 2.0) and _close(beat_seconds(tm, 6.8), 0.5)
    assert beat_seconds(tm, 9.0) is None and bar_seconds(tm, 0.0) is None
    # lengths: the distance between two positions, the closing barline included
    assert length(tm, 1.0, 5.0) == 2.0 and length(tm, 1.0, 5.0, "beat") == 8.0
    assert length(tm, 1.0, 7.0) == 3.0 and length(tm, 1.0, 7.03, "beat") == 12.0
    assert length(tm, 2.0, 6.0) == 2.0 and length(tm, 1.0, 2.0) == 0.5
    assert length(tm, 2.95, 5.04) == 1.0  # both ends snapped
    assert length(tm, 4.0, 4.0) == 0.0  # a point lasts nothing
    assert length(tm, 0.5, 5.0) is None and length(tm, 1.0, 7.5) is None
    assert length(tm, 7.0, 7.0) is None  # starting on the closing barline
    # positions for distances: the closing barline ends the last bar
    assert position(tm, 5.0) == 2.0 and position(tm, 5.0, "beat") == 8.0
    assert position(tm, 7.0) == 3.0 and position(tm, 7.03, "beat") == 12.0
    assert position(tm, 7.5) is None and position(tm, 0.5) is None


def test_four_four_downbeat(monkeypatch):
    tm = _map(T44, [4, 4, 4], [1, 2, 3])

    assert is_downbeat(tm, 3.0) and is_downbeat(tm, 3.08) and is_downbeat(tm, 2.93)
    assert not is_downbeat(tm, 3.2)
    with _tolerance(monkeypatch, 0.25):  # is_downbeat(3.2, tol=0.25)
        assert is_downbeat(tm, 3.2)
    assert not is_downbeat(tm, 4.0) and is_downbeat(tm, 0.95)
    with _tolerance(monkeypatch, 0):  # is_downbeat(t, tol=0)
        assert is_downbeat(tm, 3.0 + 1e-9) and not is_downbeat(tm, 3.01)
    assert bar(tm, None) is None and bar(tm, math.nan) is None
    assert not is_downbeat(tm, None)


# --- exact containment (snap=0): only float noise is forgiven ---------------


def test_exact_containment(monkeypatch):
    monkeypatch.setattr(timemap_module, "TOLERANCE", 0)
    strict = _map(T44, [4, 4, 4], [1, 2, 3])

    assert strict.tolerance == 0  # from_timeline(..., snap=0).snap == 0
    assert bar(strict, 2.95) == 1 and _close(beat(strict, 2.95), 4.9)
    assert bar(strict, 3.0 - 1e-9) == 2 and beat(strict, 3.0 - 1e-9) == 1.0
    assert end_bar(strict, 3.04) == 2 and end_bar(strict, 3.0 + 1e-9) == 1
    assert bar(strict, 0.95) is None and bar(strict, 1.0 - 1e-9) == 1


# --- a 3/4 bar inside 4/4 ---------------------------------------------------

THREE_FOUR_INSIDE = ([float(i) for i in range(11)], [4, 3, 4], [1, 2, 3])


def test_three_four_bar_inside_four_four():
    tm = _map(*THREE_FOUR_INSIDE)

    assert (bar(tm, 3.5), bar(tm, 4.0), bar(tm, 6.5), bar(tm, 7.0)) == (1, 2, 2, 3)
    assert _close(beat(tm, 6.5), 3.5) and end_bar(tm, 7.0) == 2
    # after the last beat (10.0): one gap, as the full last bar gets from the
    # pattern in the prototype (FR-011)
    assert bar(tm, 10.5) == 3 and _close(beat(tm, 10.5), 4.5) and tm.end == 11.0
    beats = [measure_beats(tm, t) for t in (0.0, 4.0, 6.5, 6.95)]
    assert beats == [4, 3, 3, 4]  # 6.95 snaps
    assert measure_beats(tm, -1.0) is None and measure_beats(tm, 11.0) is None


def test_three_four_bar_inside_four_four_distances():
    tm = _map(*THREE_FOUR_INSIDE)

    assert _close(bar_seconds(tm, 5.0), 3.0) and _close(bar_seconds(tm, 1.0), 4.0)
    assert _close(measure_pos(tm, 5.5), 1.5) and _close(measure_pos(tm, 8.0), 2.25)
    assert length(tm, 0.0, 11.0) == 3.0 and length(tm, 0.0, 11.0, "beat") == 11.0
    assert length(tm, 4.0, 7.0) == 1.0  # the 3/4 bar is one bar


# --- a pickup measure, printed 0 --------------------------------------------

PICKUP = ([float(i) for i in range(9)], [1, 4, 4], [0, 1, 2])


def test_pickup():
    tm = _map(*PICKUP)

    assert (bar(tm, 0.0), bar_count(tm, 0.5), bar_label(tm, 0.5)) == (0, 1, "0")
    assert _close(beat(tm, 0.5), 1.5)
    assert (bar(tm, 1.0), bar_count(tm, 1.0), end_bar(tm, 1.0)) == (1, 2, 0)
    # Changed (TQL §7.3; FR-030): a point on bar 1's downbeat ends in its own
    # bar. The prototype's end_bar takes no start, and gives 0 for it too.
    point = tm.positions(1.0, 1.0)
    assert (point.bar, point.bar_count, point.end_bar) == (1, 2, 1)
    assert is_downbeat(tm, 0.0)  # TiLiA's view: the pickup starts measure 0


def test_pickup_distances():
    tm = _map(*PICKUP)

    assert _close(measure_pos(tm, 0.5), 0.5)


# --- a repeated printed number = two passes ---------------------------------

REPEAT = ([float(i) for i in range(10)], [2] * 5, [1, 2, 1, 2, 3])


def test_repeated_number():
    tm = _map(*REPEAT)
    times = (0.5, 2.5, 4.5, 6.5, 8.5)

    assert [bar(tm, t) for t in times] == [1, 2, 1, 2, 3]
    assert [pass_of(tm, t) for t in times] == [1, 1, 2, 2, 1]
    assert [bar_count(tm, t) for t in times] == [1, 2, 3, 4, 5]
    assert end_bar(tm, 4.0) == 2 and bar(tm, 9.5) == 3 and tm.end == 10.0


def test_repeated_number_distances():
    tm = _map(*REPEAT)

    assert length(tm, 0.0, 8.0) == 4.0  # repeats count as played


# --- a jump in the numbering (42 -> 44) -------------------------------------

JUMP = ([float(i) for i in range(8)], [2, 2, 2, 2], [41, 42, 44, 45])


def test_jump_in_the_numbering():
    tm = _map(*JUMP)

    assert (bar(tm, 4.5), bar_count(tm, 4.5), bar_label(tm, 4.5)) == (44, 3, "44")
    assert end_bar(tm, 4.0) == 42


def test_jump_in_the_numbering_distances():
    tm = _map(*JUMP)

    assert measure_pos(tm, 4.0) == 2.0  # index space: no gap


# --- after the last beat ----------------------------------------------------
# Changed (FR-011), every expectation after the last beat: the last beat lasts
# as long as the gap before it, and no beats are added, so the last bar ends one
# gap after its last beat. The prototype runs the last bar on to the count its
# beat pattern gives it, adding beats as long as the last gap.

SHORT_LAST = ([float(i) for i in range(6)], [4, 2], [1, 2])  # bar 2: 2 of 4


def test_after_the_last_beat():
    tm = _map(*SHORT_LAST)

    # The prototype: end 8.0, and 7.5 in bar 2 at beat 4.5.
    assert tm.end == 6.0 and bar(tm, 7.5) is None and beat(tm, 7.5) is None
    assert bar(tm, 5.5) == 2 and _close(beat(tm, 5.5), 2.5)
    # ... and it still has the 2 beats TiLiA shows
    assert measure_beats(tm, 7.5) is None and measure_beats(tm, 5.5) == 2
    assert measure_beats(tm, 0.0) == 4
    # The prototype: (4.0, 8.0, 2, 2) for bar 2.
    assert measures(tm) == [(0.0, 4.0, 1, 4), (4.0, 6.0, 2, 2)]
    # The prototype: end_bar(8.0) == 2, on its closing barline.
    assert bar(tm, 8.0) is None and end_bar(tm, 8.0) is None
    assert end_bar(tm, 6.0) == 2 and end_bar(tm, 8.5) is None


def test_after_the_last_beat_distances():
    tm = _map(*SHORT_LAST)

    # The prototype: bar_seconds(7.0) 4.0, measure_pos(7.0) 1.75,
    # beat_pos(7.5) 7.5 and beat_seconds(7.5) 1.0, inside the beats it added.
    assert bar_seconds(tm, 7.0) is None and measure_pos(tm, 7.0) is None
    assert beat_pos(tm, 7.5) is None and beat_seconds(tm, 7.5) is None
    # Within the last bar as the core ends it: two beats, the second lasting
    # until the closing barline at 6.0.
    assert _close(bar_seconds(tm, 5.5), 2.0) and _close(measure_pos(tm, 5.5), 1.75)
    assert _close(beat_pos(tm, 5.5), 5.5) and _close(beat_seconds(tm, 5.5), 1.0)


def test_closing_one_beat_bar():
    # The prototype builds two maps here, with the beat patterns [4, 4, 1] and
    # [4]. The core doesn't read the beat pattern, so both are this one.
    tm = _map([float(i) for i in range(9)], [4, 4, 1], [1, 2, 3])

    # a closing one-beat bar the pattern also calls one beat (as in s4)
    assert tm.end == 9.0 and bar(tm, 8.5) == 3 and end_bar(tm, 8.0) == 2
    # A closing one-beat bar in 4/4. Changed (FR-011): the prototype's final
    # bar lasts its four beats (end 12.0, and 11.5 at beat 4.5 of bar 3); the
    # core's lasts the one beat tapped, as long as the gap before it.
    assert tm.end == 9.0 and bar(tm, 11.5) is None and beat(tm, 11.5) is None
    assert bar(tm, 8.5) == 3 and _close(beat(tm, 8.5), 1.5)


# --- snapping: within 0.1 s of a beat is on it, further away stays fractional


def test_snapping():
    tm = _map(T44, [4, 4, 4], [1, 2, 3])

    assert beat(tm, 1.45) == 2.0 and beat(tm, 1.55) == 2.0
    assert _close(beat(tm, 1.38), 1.76)
    # ... onto the NEAREST beat when two are close together
    tm = _map([0.0, 0.12, 1.0, 2.0], [2, 2], [1, 2])
    assert beat(tm, 0.07) == 2.0 and beat(tm, 0.05) == 1.0


def test_snapping_distances():
    tm = _map(T44, [4, 4, 4], [1, 2, 3])

    assert _close(beat_pos(tm, 1.38), 0.76)


# --- from_timeline and pick_time_map, where they don't load old files -------

EIGHT = [float(i) for i in range(8)]


def test_from_a_timeline():
    tm = _map(EIGHT, [4, 4], [1, 2])

    assert (bar(tm, 4.0), beat(tm, 5.5), tm.end) == (2, 2.5, 8.0)


def test_no_time_map():
    # fewer than two beats, no beats, and not a beat timeline
    one = beat_timeline([{"time": 1.0, "measure": {"number": 1}}])
    none = beat_timeline([])
    hierarchy = tla.Timeline(id=tla.new_id(), kind="hierarchy", ordinal=1)
    doc = document(one, none, hierarchy)

    assert time_map_for(doc, one.id) is None
    assert time_map_for(doc, none.id) is None
    assert time_map_for(doc, hierarchy.id) is None
    assert time_map_for(doc, tla.new_id()) is None


def test_choosing_the_time_map():
    """The prototype's pick_time_map, which is the core's find_time_map."""
    # the first beat timeline by ordinal
    hierarchy = tla.Timeline(id=tla.new_id(), kind="hierarchy", ordinal=1)
    late = beat_timeline([], ordinal=5)
    early = beat_timeline([], ordinal=2)
    assert find_time_map(document(hierarchy, late, early)).timeline_id == early.id
    # ties in file order
    first = beat_timeline([], ordinal=2)
    second = beat_timeline([], ordinal=2)
    assert find_time_map(document(first, second)).timeline_id == first.id
    # no beat timeline, no time map
    for doc in (document(hierarchy), document()):
        found = find_time_map(doc)
        assert found.timeline_id is None and found.time_map is None


# --- every beat reads back its measure ---------------------------------------


@pytest.mark.parametrize(
    "times, counts, numbers",
    [
        (T44, [4, 4, 4], [1, 2, 3]),
        THREE_FOUR_INSIDE,
        PICKUP,
        REPEAT,
        JUMP,
        SHORT_LAST,
        ([float(i) for i in range(9)], [4, 4, 1], [1, 2, 3]),
        ([0.0, 0.12, 1.0, 2.0], [2, 2], [1, 2]),
        (EIGHT, [4, 4], [1, 2]),
    ],
)
def test_every_beat_reads_back_its_measure(monkeypatch, times, counts, numbers):
    # _selftest_real_files' check of a real file's beats, on the maps above:
    # (number, beat, pass, count) of every beat, from the arrays.
    ref, seen = [], {}
    for j, (number, count) in enumerate(zip(numbers, counts, strict=True)):
        seen[number] = seen.get(number, 0) + 1
        ref += [(number, b + 1, seen[number], j + 1) for b in range(count)]
    tm = _map(times, counts, numbers)

    for k, (t, (number, b, p, count)) in enumerate(zip(times, ref, strict=True)):
        assert (bar(tm, t), beat(tm, t), pass_of(tm, t), bar_count(tm, t)) == (
            number,
            b,
            p,
            count,
        ), t
        assert bar_label(tm, t) == str(number)
        if k:  # ending on a beat: the bar of the beat before it
            assert end_bar(tm, t) == ref[k - 1][0], t
    with _tolerance(monkeypatch, 0):  # is_downbeat(t, tol=0)
        for t, (_, b, _, _) in zip(times, ref, strict=True):
            assert is_downbeat(tm, t) == (b == 1), t
