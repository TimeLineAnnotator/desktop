"""Quarter stamps: each beat's position in quarter notes, and the conversion
between times and quarter stamps.

The first part ports desktop#621's tests/timelines/beat/test_quarter_stamps.py
(at 0ee8ea45) case for case: each class and test keeps its name, and builds the
beat timeline #621's `beat_tl` fixture builds, as a document. The second part
is the spec's User Story 3, scenarios 1-3 and 5.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import threading
from fractions import Fraction as F

import pytest

from docs import beat_timeline, document
from tilia_core import tla
from tilia_core.timemap import TimeMap, qstamps, time_map_for
from tilia_core.timemap import timemap as timemap_module
from tilia_core.timemap.table import build_rows

# What TiLiA puts on the first beat, which #621's tests edit.
DEFAULT = {"denominator": 4, "units": "1", "assumed": True}


def _timeline(times, pattern=(4,), units=None) -> tla.Timeline:
    """#621's `beat_tl` after `add_beats(times)` and `add_beat_unit`: a beat at
    each time, in measures of `pattern`'s counts in turn, TiLiA's default unit
    on the first beat, and `units` ({beat index: (denominator, units)}) set on
    the beats, the first beat's replacing the default."""
    downbeats = set(
        itertools.takewhile(
            lambda i: i < len(times),
            itertools.accumulate(itertools.cycle(pattern), initial=0),
        )
    )
    marks = {i: {} for i in downbeats} | {0: {"number": 1}}
    set_units = {0: DEFAULT}
    for index, (denominator, text) in (units or {}).items():
        set_units[index] = {"denominator": denominator, "units": text}
    return beat_timeline(
        [
            {"time": float(t), "measure": marks.get(i), "beat_unit": set_units.get(i)}
            for i, t in enumerate(times)
        ]
    )


def _map(timeline: tla.Timeline, **kwargs) -> TimeMap:
    time_map = time_map_for(document(timeline, **kwargs), timeline.id)
    assert time_map is not None
    return time_map


def _beat_times(timeline: tla.Timeline) -> list[float]:
    return [
        timeline.components[beat].attrs["time"]
        for row in timeline.measures.rows
        for beat in row.beats
    ]


def _stamps(timeline: tla.Timeline) -> list[float]:
    """The quarter stamp of every beat, as the timeline's time map gives it."""
    time_map = _map(timeline)
    return [time_map.qstamp(t) for t in _beat_times(timeline)]


def _floats(stamps) -> list[float]:
    return [float(F(stamp)) for stamp in stamps]


def _set_time(timeline: tla.Timeline, index: int, time: float) -> None:
    beat_id = [b for row in timeline.measures.rows for b in row.beats][index]
    timeline.components[beat_id].attrs["time"] = time


# --- desktop#621's tests ----------------------------------------------------


class TestBeatStamps:
    def test_default_is_one_quarter_per_beat(self):
        assert _stamps(_timeline(range(6))) == _floats([0, 1, 2, 3, 4, 5])

    def test_dotted_quarter_beats(self):
        timeline = _timeline(range(4), [2], {0: (8, "3")})

        assert _stamps(timeline) == _floats([0, F(3, 2), 3, F(9, 2)])

    def test_changing_beat_unit(self):
        timeline = _timeline(range(6), [2], {2: (2, "1")})

        assert _stamps(timeline) == _floats([0, 1, 2, 4, 6, 8])

    def test_uneven_units(self):
        timeline = _timeline(range(4), [2], {0: (8, "2+3")})

        assert _stamps(timeline) == _floats([0, 1, F(5, 2), F(7, 2)])

    def test_triplets_are_exact(self):
        timeline = _timeline(range(7), [3], {0: (4, "1/3")})

        assert _stamps(timeline)[6] == 2
        assert _stamps(timeline)[1] == float(F(1, 3))
        # Exact inside: the measure after two of triplets starts at 2, not at
        # the float sum of six thirds.
        rows = _map(timeline).measure_rows()
        assert [row.qstamp for row in rows] == [0, 1, 2]
        assert type(rows[2].qstamp) is F

    def test_pickup_starts_at_zero(self):
        timeline = _timeline(range(3), [1, 2], {0: (4, "3+2")})

        # One pickup tap, read from the start of 3+2, then a full bar.
        assert _stamps(timeline) == _floats([0, 3, 6])

    def test_stamps_follow_inserted_beats(self):
        timeline = _timeline([0, 2, 3])
        assert _stamps(timeline) == _floats([0, 1, 2])

        beat = tla.Component(id=tla.new_id(), kind="beat", attrs={"time": 1.0})
        timeline.components[beat.id] = beat
        timeline.measures.rows[0].beats.insert(1, beat.id)

        # A time map is built from the document as it is (FR-004).
        assert _stamps(timeline) == _floats([0, 1, 2, 3])

    def test_of_beat(self):
        timeline = _timeline(range(3))

        assert _map(timeline).qstamp(_beat_times(timeline)[2]) == 2


class TestTimeToStamp:
    @pytest.fixture
    def tl(self):
        # Beats every 2 s, worth a dotted quarter each.
        return _timeline([10, 12, 14, 16], [2], {0: (8, "3")})

    @pytest.mark.parametrize(
        "time, stamp",
        [(10, 0), (11, 0.75), (12, 1.5), (15, 3.75), (16, 4.5), (18, 6), (8, -1.5)],
    )
    def test_time_to_stamp(self, tl, time, stamp):
        assert _map(tl).qstamp(time) == pytest.approx(stamp)

    @pytest.mark.parametrize(
        "stamp, time",
        [(0, 10), (0.75, 11), (1.5, 12), (3.75, 15), (4.5, 16), (6, 18), (-1.5, 8)],
    )
    def test_stamp_to_time(self, tl, stamp, time):
        assert _map(tl).time_at_qstamp(stamp) == pytest.approx(time)

    def test_round_trip(self, tl):
        tm = _map(tl)
        for time in [10.3, 12.7, 13.1, 16.9]:
            stamp = tm.qstamp(time)
            assert tm.time_at_qstamp(stamp) == pytest.approx(time)

    def test_uneven_beat_lengths(self):
        tm = _map(_timeline([0, 1, 2], [2], {0: (4, "2+3")}))

        # Beat 0 lasts 2 quarters over 1 s; beat 1 lasts 3 quarters over 1 s.
        assert tm.qstamp(0.5) == pytest.approx(1)
        assert tm.qstamp(1.5) == pytest.approx(3.5)

    def test_past_last_beat_keeps_last_gap_tempo(self):
        timeline = _timeline([0, 1, 2], [2], {0: (4, "2+3")})
        tm = _map(timeline)

        # The last gap lasts 3 quarters over 1 s. The last beat is worth 2
        # quarters, which must not change that tempo.
        assert _stamps(timeline) == _floats([0, 2, 5])
        assert tm.qstamp(2.5) == pytest.approx(6.5)
        assert tm.time_at_qstamp(6.5) == pytest.approx(2.5)

    @pytest.mark.parametrize("times", [[], [5]])
    def test_needs_two_beats(self, times):
        # #621 gives None for either conversion. In the core such a timeline
        # has no time map at all (FR-003), and the port's functions give None.
        timeline = _timeline(times)
        assert time_map_for(document(timeline), timeline.id) is None

        table = qstamps.build_time_stamp_table(
            [float(t) for t in times], [F(1)] * len(times)
        )
        assert table is None
        assert qstamps.quarter_stamp_by_time(table, 5) is None
        assert qstamps.time_by_quarter_stamp(table, 0) is None

    def test_follows_dragged_beat(self, tl):
        _set_time(tl, 1, 13.0)

        assert _map(tl).qstamp(13) == pytest.approx(1.5)


class TestCaching:
    def test_conversions_reuse_one_table(self, monkeypatch):
        calls = []

        def build(*args):
            calls.append(args)
            return qstamps.build_time_stamp_table(*args)

        monkeypatch.setattr(timemap_module, "build_time_stamp_table", build)
        tm = _map(_timeline(range(100)))
        # Built the first time a qstamp is asked for, not with the map.
        assert calls == []
        for i in range(500):
            stamp = tm.qstamp(i * 0.2)
            tm.time_at_qstamp(stamp)

        assert len(calls) == 1

    def test_table_is_rebuilt_after_a_change(self):
        timeline = _timeline(range(4))
        before = _map(timeline)
        assert before.qstamp(3) == pytest.approx(3)

        _set_time(timeline, 3, 4.0)

        # A map built after the change has it; one built before doesn't
        # follow it (FR-004).
        assert _map(timeline).qstamp(4) == pytest.approx(3)
        assert before.qstamp(3) == pytest.approx(3)


# --- the spec's User Story 3 ------------------------------------------------


def _tapped_example(*, six_eight: bool = True) -> tla.Timeline:
    """The layout's tapped recording, a beat every second from 0 s: a one-beat
    pickup, then bars 1, 2a, 1 and 2b in 3/4, and bar 3, a 6/8 tapped in two."""
    marks = {
        0: {"number": 0},
        1: {},
        4: {"label": "2a"},
        7: {"number": 1},
        10: {"label": "2b"},
        13: {},
    }
    beats = [{"time": float(t), "measure": marks.get(t)} for t in range(15)]
    beats[0]["beat_unit"] = DEFAULT
    if six_eight:
        beats[13]["beat_unit"] = {"denominator": 8, "units": "3"}
    return beat_timeline(beats)


def test_qstamps_of_the_tapped_example():
    # Spec, US3 scenario 1.
    tm = _map(_tapped_example())
    rows = tm.measure_rows()

    assert tm.qstamp(0.0) == 0
    assert [(row.label, row.qstamp) for row in rows] == [
        ("0", 0),
        ("1", 1),
        ("2a", 4),
        ("1", 7),
        ("2b", 10),
        ("3", 13),
    ]
    assert [row.quarters for row in rows] == [1, 3, 3, 3, 3, 3]
    assert tm.qstamp(14.0) - tm.qstamp(13.0) == 1.5
    # The rows' stamps are the map's, at their downbeats, and exact.
    assert [tm.qstamp(row.start) for row in rows] == [float(r.qstamp) for r in rows]
    assert {type(row.qstamp) for row in rows} == {F}
    assert {type(row.quarters) for row in rows} == {F}


def test_setting_a_beat_unit_changes_every_qstamp_after_it():
    # Spec, US3 scenario 2: the 6/8 bar without a unit of its own reads 2/4,
    # assumed. Setting {8, "3"} on its downbeat changes every qstamp after it
    # at once, and the file only by that beat unit.
    timeline = _tapped_example(six_eight=False)
    doc = document(timeline)
    written = tla.canonical_bytes(doc)
    before = time_map_for(doc, timeline.id)
    assert before.measure_rows()[-1].time_signature == "2/4"
    assert before.measure_rows()[-1].assumed

    six_eight = {"denominator": 8, "units": "3"}
    downbeat = timeline.measures.rows[-1].id
    timeline.components[downbeat].attrs["beat_unit"] = six_eight
    after = time_map_for(doc, timeline.id)

    times = [0.0, 5.5, 12.0, 13.0, 13.5, 14.0, 14.5, 15.5]
    assert [before.qstamp(t) for t in times] == [0, 5.5, 12, 13, 13.5, 14, 14.5, 15.5]
    assert [after.qstamp(t) for t in times] == pytest.approx(
        [0, 5.5, 12, 13, 13.75, 14.5, 15.25, 16.75]
    )
    assert after.measure_rows()[-1].time_signature == "6/8"
    assert after.measure_rows()[-1].quarters == 3
    # Nothing computed reaches the file: it changed by the beat unit alone.
    rewritten = tla.canonical_bytes(doc)
    assert rewritten != written
    unchanged = _without(json.loads(rewritten), "beat_unit", six_eight)
    assert unchanged == json.loads(written)


def _without(value, key, unwanted):
    """`value` with every `key` whose value holds `unwanted`'s items taken out."""
    if isinstance(value, list):
        return [_without(item, key, unwanted) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        k: _without(v, key, unwanted)
        for k, v in value.items()
        if not (k == key and isinstance(v, dict) and unwanted.items() <= v.items())
    }


def test_qstamps_between_and_beyond_the_beats():
    # Spec, US3 scenario 3, on the tapped example: between two beats a qstamp
    # is interpolated; beyond the last beat it is extrapolated with the last
    # gap's tempo, and before the first with the first gap's; a qstamp converts
    # back to the same time.
    tm = _map(_tapped_example())

    assert tm.qstamp(2.25) == 2.25  # quarter notes, a beat every second
    assert tm.qstamp(13.5) == 13.75  # dotted quarters
    # The last gap (13 to 14 s) lasts 1.5 quarters: so does every second after
    # 14 s, past the closing barline (15 s) too.
    assert tm.qstamp(15.0) == 16.0 and tm.qstamp(20.0) == 23.5
    # Before the first beat: the first gap's tempo, a quarter a second. Bar 0
    # has no position there (the prototype), but a qstamp (#621).
    assert tm.qstamp(-2.0) == -2.0
    assert tm.positions(-2.0, -2.0) is None
    for t in (-2.0, 0.0, 2.25, 6.6, 13.5, 14.0, 15.0, 20.0):
        assert tm.time_at_qstamp(tm.qstamp(t)) == pytest.approx(t)


def test_a_missing_time_has_no_qstamp():
    tm = _map(_tapped_example())

    for t in (None, float("nan"), float("inf")):
        assert tm.qstamp(t) is None
        assert tm.time_at_qstamp(t) is None
        assert tm.quarters(t, 3.0) is None and tm.quarters(3.0, t) is None
        assert not tm.assumed_between(t, 3.0)


def test_a_span_in_quarter_notes():
    # Spec, US3 scenario 5: a span's length in quarter notes is the difference
    # of its qstamps, rounded to a millionth as lengths in bars and beats are.
    tm = _map(_tapped_example())

    assert tm.quarters(1.0, 4.0) == 3.0  # bar 1
    assert tm.quarters(13.0, 15.0) == 3.0  # the 6/8 bar
    assert tm.quarters(12.5, 13.5) == 0.5 + 0.75
    assert tm.quarters(6.6, 6.6) == 0.0
    for start, end in ((0.0, 15.0), (2.3, 14.2), (-1.0, 20.0), (14.2, 2.3)):
        difference = tm.qstamp(end) - tm.qstamp(start)
        assert tm.quarters(start, end) == round(difference, 6)


def test_quarters_are_rounded_to_a_millionth():
    # Under 1/3 units, a beat every second, the float stamps of two beats
    # 8 quarter notes apart differ by 7.999999999999999.
    tm = _map(_timeline(range(30), [3], {0: (4, "1/3")}))

    assert tm.qstamp(26.0) - tm.qstamp(2.0) != 8
    assert tm.quarters(2.0, 26.0) == 8.0 and tm.quarters(4.0, 7.0) == 1.0


def _assumed_timeline(assumed_unit=None, *, beats=8) -> tla.Timeline:
    """Bars of two taps, a beat every second from 0 s: bars 1 and 2 under a
    unit someone set, bar 3 under an assumed one, bar 4 set again, a 6/8."""
    marks = {t: {} for t in range(0, beats, 2)} | {0: {"number": 1}}
    units = {
        0: {"denominator": 4, "units": "1"},
        4: {"denominator": 4, "units": "1", **(assumed_unit or {}), "assumed": True},
        6: {"denominator": 8, "units": "3"},
    }
    return beat_timeline(
        [
            {"time": float(t), "measure": marks.get(t), "beat_unit": units.get(t)}
            for t in range(beats)
        ]
    )


def test_whether_an_assumed_meter_went_into_a_length_in_quarters():
    # Spec, US3 scenario 5 (FR-043): whether a measure holding a beat whose
    # length the span's quarter notes count is assumed. Times aren't snapped,
    # as qstamps aren't; an end exactly on a beat takes nothing from its gap.
    tm = _map(_assumed_timeline())
    assert [row.assumed for row in tm.measure_rows()] == [False, False, True, False]

    assert not tm.assumed_between(0.0, 4.0)  # bars 1 and 2, ending on bar 3
    assert tm.assumed_between(0.5, 4.08)  # 0.08 s into bar 3
    assert not tm.assumed_between(3.92, 3.98)  # just before it
    assert tm.assumed_between(3.5, 6.5)
    assert tm.assumed_between(5.0, 5.0)  # a point in bar 3
    assert tm.assumed_between(4.0, 4.0)  # a point on its downbeat
    assert not tm.assumed_between(3.95, 3.95)  # a point just before it
    assert not tm.assumed_between(6.0, 7.5)  # bar 4
    # An end before the start: the bars between, as the other way round.
    assert tm.assumed_between(5.5, 2.0) and tm.assumed_between(7.5, 3.5)
    assert not tm.assumed_between(2.5, 1.5)


def test_off_the_map_the_gap_at_that_end_counts():
    # Qstamps off the map are extrapolated with the tempo of the gap at that
    # end (#621): before the first beat the first gap's, after the last beat
    # the last gap's.
    tm = _map(_assumed_timeline())

    assert not tm.assumed_between(-5.0, -1.0)  # bar 1's
    assert not tm.assumed_between(7.5, 20.0)  # bar 4's
    assert tm.assumed_between(-5.0, 20.0)  # every bar
    # The tapped example's last bar, without its unit, reads 2/4, assumed.
    assert _map(_tapped_example(six_eight=False)).assumed_between(16.0, 18.0)
    assert not _map(_tapped_example()).assumed_between(16.0, 18.0)
    # A last bar of a single tap: the last gap is the assumed bar 3's.
    one_tap = _map(_assumed_timeline(beats=7))
    assert [row.beats for row in one_tap.measure_rows()] == [2, 2, 2, 1]
    assert one_tap.assumed_between(6.0, 6.9)


@pytest.mark.parametrize("beats", [8, 7], ids=["two taps", "one tap"])
def test_a_meter_the_flag_leaves_out_never_changes_the_quarters(beats):
    # Wherever assumed_between says no, another meter for the assumed bar 3
    # leaves quarters() as it was: the flag misses no meter that went in.
    quarter = _map(_assumed_timeline(beats=beats))
    eighth = _map(_assumed_timeline({"denominator": 8}, beats=beats))
    times = [t / 4 for t in range(-8, 44)]
    times += [t + d for t in range(beats) for d in (-0.05, 1e-9, 0.05)]

    for start, end in itertools.product(times, repeat=2):
        if not quarter.assumed_between(start, end):
            expected = eighth.quarters(start, end)
            assert quarter.quarters(start, end) == pytest.approx(expected, abs=1e-6)


def test_first_qstamps_on_two_maps_dont_wait_for_each_other(monkeypatch):
    # Each map builds its stamp table on first use, without a lock that every
    # map shares, as functools.cached_property's is on Python 3.10 and 3.11.
    started, release = threading.Event(), threading.Event()

    def slow_build(times, lengths):
        if times[0] == 100.0:
            started.set()
            release.wait(5)
        return qstamps.build_time_stamp_table(times, lengths)

    monkeypatch.setattr(timemap_module, "build_time_stamp_table", slow_build)
    slow, quick = _map(_timeline([100, 101, 102])), _map(_timeline(range(3)))
    building = threading.Thread(target=slow.qstamp, args=(100.5,))
    building.start()
    try:
        assert started.wait(5)
        asking = threading.Thread(target=quick.qstamp, args=(0.5,))
        asking.start()
        asking.join(2)
        assert not asking.is_alive()
    finally:
        release.set()
        building.join(5)
    assert slow.qstamp(100.5) == 0.5 and quick.qstamp(0.5) == 0.5


def _uneven_ending(units: str, **kwargs) -> TimeMap:
    """Two bars of two taps under `units` over 8, a beat every second, then a
    last bar of one tap at 4 s, which reads the pattern's first entry."""
    return _map(_timeline(range(5), [2], {0: (8, units)}), **kwargs)


def test_a_last_beat_lasts_its_own_length_at_the_last_tempo():
    # TimeLineAnnotator/project-management#325's example: under 2+3, the beat
    # at 3 s is worth 3 eighths and lasts 1 s, so an eighth takes 1/3 s; the
    # last beat, worth 2, lasts 2/3 s.
    tm = _uneven_ending("2+3")
    last = tm.measure_rows()[-1]

    assert tm.end == pytest.approx(4 + 2 / 3)
    assert (last.quarters, last.end) == (1, tm.end)
    assert tm.quarters(last.start, last.end) == 1.0
    assert tm.qstamp(tm.end) == pytest.approx(float(last.qstamp + last.quarters))
    assert tm.qstamp(4.5) == 5.75  # desktop#621's tempo past the last beat
    assert tm.positions(4.8, 4.8) is None  # past the closing barline
    # Worth more than the beat before: under 3+2, the last beat is worth 3
    # eighths after a beat of 2 that took 1 s, so it lasts 1.5 s.
    longer = _uneven_ending("3+2")
    assert longer.end == 5.5 and longer.quarters(4.0, 5.5) == 1.5
    # The end of the media still comes first.
    assert _uneven_ending("2+3", media_length=4.5).end == 4.5


def test_a_last_beat_worth_the_same_ends_one_gap_after_it():
    # When the last two beats are worth the same, the barline doesn't move:
    # exactly one gap after the last beat, as before #325. Under 5/3, the gap
    # through the tempo in floats would move this barline by a float's last
    # place.
    for units in ("3", "1", "1/3", "5/3"):
        tm = _map(_timeline([0.0, 0.3, 0.5, 0.721, 0.94], [2], {0: (8, units)}))
        assert tm.end == 0.94 + (0.94 - 0.721)


@pytest.mark.parametrize(
    "beat_unit, taps, quarters",
    [
        ((8, "3"), 2, 3),
        ((8, "2+3"), 3, F(7, 2)),  # 2+3+2 eighths, ambiguous
        ((4, "1/3"), 4, F(4, 3)),
        ((8, "1/2+1"), 3, 1),  # 1/2+1+1/2 eighths
        ((2, "1"), 5, 10),
    ],
)
def test_a_measure_lasts_the_sum_of_its_beats(beat_unit, taps, quarters):
    # FR-050: a measure's length in quarter notes is the sum of its beats',
    # and the next measure starts there.
    timeline = _timeline(range(taps + 2), [taps, 2], {0: beat_unit})
    first, second = build_rows(document(timeline), timeline)

    assert first.quarters == quarters == sum(qstamps.beat_lengths(first.meter))
    assert second.qstamp == quarters


def test_rows_give_their_qstamps_as_text_in_json():
    timeline = _timeline(range(4), [2])
    first, second = build_rows(document(timeline), timeline)

    assert (first.qstamp, first.quarters) == (0, 2)
    as_json = json.loads(json.dumps(dataclasses.asdict(second), default=str))
    assert (as_json["qstamp"], as_json["quarters"]) == ("2", "2")


def test_qstamps_are_computed_for_a_folded_table():
    # FR-013: a folded table has no time map, but its rows have their qstamps,
    # in the timeline's order.
    beats = [
        {"time": float(t), "measure": {} if t % 2 == 0 else None} for t in range(6)
    ]
    beats[0]["measure"] = {"number": 1, "next": ["a later measure"]}
    timeline = beat_timeline(beats)
    doc = document(timeline)

    assert time_map_for(doc, timeline.id) is None
    assert [row.qstamp for row in build_rows(doc, timeline)] == [0, 2, 4]
