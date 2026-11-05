import copy
import dataclasses
import json
import logging
import pickle
from fractions import Fraction as F

import pytest

from docs import beat_timeline, document, pickup_piece
from tilia_core import tla
from tilia_core.timemap import time_map_for
from tilia_core.timemap._rows import rows_of
from tilia_core.timemap.meters import meters_of
from tilia_core.timemap.table import build_rows, find_rows, format_time_signature


def _timeline(marks: list[dict], beats: int = 2) -> tla.Timeline:
    """One measure per mark, each of `beats` beats, a beat every second from 0."""
    return beat_timeline(
        [
            {"time": float(j * beats + b), "measure": mark if b == 0 else None}
            for j, mark in enumerate(marks)
            for b in range(beats)
        ]
    )


def _rows(marks: list[dict], beats: int = 2, **kwargs):
    timeline = _timeline(marks, beats)
    return build_rows(document(timeline, **kwargs), timeline)


ENDINGS = [{"number": 1}, {"label": "2a"}, {"number": 1}, {"label": "2b"}]
CADENZA = [{"number": 1}, {}, {"number": 2, "label": "2c", "cadenza": True}, {}]


def test_count_is_the_position_in_the_timeline():
    rows = _rows([{"number": 41}, {}, {"number": 44}, {}])

    assert [r.count for r in rows] == [1, 2, 3, 4]
    assert [r.number for r in rows] == [41, 42, 44, 45]


@pytest.mark.parametrize(
    "break_row",
    [lambda row: row.beats.reverse(), lambda row: row.beats.clear()],
    ids=["beats not starting at the downbeat", "no beats"],
)
def test_no_rows_for_a_broken_table(break_row):
    timeline = _timeline([{"number": 1}, {}, {}])
    break_row(timeline.measures.rows[1])

    assert build_rows(document(timeline), timeline) == []


@pytest.mark.parametrize(
    "change",
    [
        lambda beat: beat.attrs.pop("time"),
        lambda beat: beat.attrs.update(time=float("nan")),
        lambda beat: beat.attrs.update(time="1.0"),
    ],
    ids=["missing", "NaN", "text"],
)
@pytest.mark.parametrize("which", [0, 1], ids=["downbeat", "other beat"])
def test_no_rows_while_a_beat_has_no_usable_time(change, which):
    timeline = _timeline([{"number": 1}, {}, {}])
    change(timeline.components[timeline.measures.rows[1].beats[which]])

    assert build_rows(document(timeline), timeline) == []


def test_rows_keep_what_the_table_gives():
    timeline = _timeline(
        [
            {"number": 1, "force_display": True, "metadata": {"tag": "a"}},
            {"source": "edited"},
        ],
        beats=3,
    )
    first, second = build_rows(document(timeline), timeline)

    assert first.id == first.beat_ids[0] == timeline.measures.rows[0].id
    assert first.beat_ids == tuple(timeline.measures.rows[0].beats)
    assert (first.beats, second.beats) == (3, 3)
    assert first.force_display and not second.force_display
    assert (first.source, second.source) == ("tapped", "edited")
    assert first.metadata == {"tag": "a"}
    assert first.next is None and not first.folded


def test_passes_count_the_times_through_a_number():
    rows = _rows([{"number": 1}, {}, {"number": 1}, {}, {}])

    assert [r.number for r in rows] == [1, 2, 1, 2, 3]
    assert [r.pass_ for r in rows] == [1, 1, 2, 2, 1]


def test_passes_of_endings_count_by_number():
    rows = _rows(ENDINGS)

    assert [r.label for r in rows] == ["1", "2a", "1", "2b"]
    assert [r.pass_ for r in rows] == [1, 1, 2, 2]


def test_a_cadenza_has_no_pass_and_counts_for_none():
    rows = _rows(CADENZA)

    assert [(r.number, r.label) for r in rows] == [
        (1, "1"),
        (2, "2"),
        (2, "2c"),
        (3, "3"),
    ]
    assert [r.pass_ for r in rows] == [1, 1, None, 1]
    assert [r.cadenza for r in rows] == [False, False, True, False]


def test_a_restart_counts_passes_again_in_the_next_movement():
    rows = _rows([{"number": 1}, {}, {}, {"number": 1, "restart": True}, {}, {}])

    assert [r.number for r in rows] == [1, 2, 3, 1, 2, 3]
    assert [r.pass_ for r in rows] == [1] * 6
    assert [r.movement for r in rows] == [1, 1, 1, 2, 2, 2]
    assert [r.restart for r in rows] == [False, False, False, True, False, False]
    assert [r.count for r in rows] == [1, 2, 3, 4, 5, 6]


def test_without_a_restart_a_second_song_is_a_second_pass():
    rows = _rows([{"number": 1}, {}, {"number": 1}, {}])

    assert [r.pass_ for r in rows] == [1, 1, 2, 2]
    assert [r.movement for r in rows] == [1, 1, 1, 1]


def test_a_restart_on_the_first_bar_leaves_it_in_movement_1():
    rows = _rows(
        [{"number": 1, "restart": True}, {}, {"number": 1, "restart": True}, {}]
    )

    assert [r.movement for r in rows] == [1, 1, 2, 2]
    assert [r.pass_ for r in rows] == [1, 1, 1, 1]
    assert [r.restart for r in rows] == [True, False, True, False]


def test_a_restart_goes_on_a_song_s_first_measure_its_pickup():
    # Each song starts with a pickup numbered 0, which carries the restart.
    rows = _rows(
        [{"number": 0, "restart": True}, {}, {}, {"number": 0, "restart": True}, {}, {}]
    )

    assert [r.number for r in rows] == [0, 1, 2, 0, 1, 2]
    assert [r.movement for r in rows] == [1, 1, 1, 2, 2, 2]
    assert [r.pass_ for r in rows] == [1] * 6


def test_each_restart_starts_another_movement():
    rows = _rows(
        [{"number": 1}, {"number": 1, "restart": True}, {"number": 1, "restart": True}]
    )

    assert [r.movement for r in rows] == [1, 2, 3]
    assert [r.pass_ for r in rows] == [1, 1, 1]


def test_a_table_with_next_is_folded():
    timeline = _timeline([{"number": 1}, {}, {}])
    timeline.measures.rows[1].next = [timeline.measures.rows[0].id]

    rows = build_rows(document(timeline), timeline)

    assert [r.folded for r in rows] == [True, True, True]
    assert rows[1].next == (timeline.measures.rows[0].id,)
    assert rows[0].next is None


def test_a_table_without_next_is_not_folded():
    assert not any(r.folded for r in _rows(ENDINGS))


def test_each_measure_ends_on_the_next_downbeat():
    rows = _rows([{"number": 1}, {}, {}], beats=3)

    assert [(r.start, r.end) for r in rows] == [(0.0, 3.0), (3.0, 6.0), (6.0, 9.0)]


def test_the_closing_barline_is_one_gap_after_the_last_beat():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0},
            {"time": 2.0, "measure": {}},
            {"time": 2.5},
        ]
    )
    rows = build_rows(document(timeline), timeline)

    assert rows[-1].end == 3.0


def test_the_closing_barline_after_a_one_beat_last_measure():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0},
            {"time": 1.5, "measure": {}},
        ]
    )
    rows = build_rows(document(timeline), timeline)

    assert (rows[-1].start, rows[-1].end, rows[-1].beats) == (1.5, 2.0, 1)


def test_no_beats_are_added_to_the_last_measure():
    # Spec, US1 scenario 8.
    timeline = pickup_piece()
    rows = build_rows(document(timeline), timeline)

    assert [r.beats for r in rows] == [1, 4, 4, 4, 4, 3]
    assert (rows[-1].start, rows[-1].end) == (18.0, 21.0)


@pytest.mark.parametrize(
    "media_length, end", [(None, 21.0), (20.4, 20.4), (21.0, 21.0), (30.0, 21.0)]
)
def test_the_end_of_the_media_caps_the_closing_barline(media_length, end, caplog):
    timeline = pickup_piece()
    rows = build_rows(document(timeline, media_length=media_length), timeline)

    assert rows[-1].end == end
    assert not caplog.records


@pytest.mark.parametrize("media_length", [19.5, 20.0])
def test_media_ending_at_or_before_the_last_beat_leaves_the_gap(media_length, caplog):
    # find_time_map warns about it, once per file; a table built logs nothing (FR-082).
    timeline = pickup_piece()
    with caplog.at_level(logging.WARNING):
        rows = build_rows(document(timeline, media_length=media_length), timeline)

    assert rows[-1].end == 21.0
    assert not caplog.records


def test_the_end_of_the_media_doesnt_cap_a_quarters_file(caplog):
    # The media's length is in seconds; a quarters file's times are in quarter notes.
    timeline = pickup_piece()
    for media_length in (20.4, 19.5):
        doc = document(timeline, media_length=media_length, time_unit="quarters")

        assert build_rows(doc, timeline)[-1].end == 21.0
    assert not caplog.records


def test_metadata_is_a_frozen_copy():
    timeline = _timeline([{"number": 1, "metadata": {"tags": ["a"], "key": "x"}}])
    doc = document(timeline)
    (row,) = build_rows(doc, timeline)
    (again,) = build_rows(doc, timeline)

    assert row.metadata == {"tags": ("a",), "key": "x"}
    assert isinstance(row.metadata, dict)
    metadata = row.metadata
    for change in (
        lambda m: m.__setitem__("key", "y"),
        lambda m: m.__delitem__("key"),
        lambda m: m.update(key="y"),
        lambda m: m.pop("key"),
        lambda m: m.popitem(),
        lambda m: m.setdefault("new", "y"),
        lambda m: m.clear(),
        lambda m: m.__ior__({"key": "y"}),
    ):
        with pytest.raises(TypeError):
            change(metadata)
    assert row.metadata == {"tags": ("a",), "key": "x"}
    timeline.measures.rows[0].metadata["tags"].append("b")
    assert row.metadata["tags"] == ("a",)
    assert row == again and hash(row) == hash(again)


def test_rows_can_be_pickled_copied_and_turned_into_dicts():
    timeline = _timeline([{"number": 1, "metadata": {"tags": ["a"], "key": "x"}}])
    (row,) = build_rows(document(timeline), timeline)

    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        assert pickle.loads(pickle.dumps(row, protocol)) == row, protocol
    assert copy.deepcopy(row) == row
    assert hash(copy.deepcopy(row)) == hash(row)
    as_dict = dataclasses.asdict(row)
    assert as_dict["metadata"] == {"tags": ("a",), "key": "x"}
    # Fractions, exact, aren't JSON numbers: they go as text, "3/2".
    as_json = json.loads(json.dumps(as_dict, default=str))
    assert as_json["metadata"] == {"tags": ["a"], "key": "x"}
    assert as_json["ts_numerator"] == "2"
    assert as_json["meter"]["beat_values"] == ["1", "1"]


def test_a_timeline_without_measures_gives_no_rows():
    timeline = beat_timeline([{"time": 0.0}, {"time": 1.0}])
    timeline.measures = None

    assert build_rows(document(timeline), timeline) == []


class TestFindRows:
    def test_a_number_finds_every_pass(self):
        rows = _rows(ENDINGS)

        assert [r.label for r in find_rows(rows, 2)] == ["2a", "2b"]
        assert [r.count for r in find_rows(rows, 1)] == [1, 3]

    def test_a_pass_narrows_a_number_to_one(self):
        rows = _rows(ENDINGS)

        assert [r.label for r in find_rows(rows, 2, pass_=2)] == ["2b"]
        assert find_rows(rows, 2, pass_=3) == []

    def test_a_label_finds_its_measures(self):
        rows = _rows(ENDINGS)

        assert [r.count for r in find_rows(rows, label="2b")] == [4]
        assert [r.count for r in find_rows(rows, label="1")] == [1, 3]
        assert [r.count for r in find_rows(rows, label="1", pass_=2)] == [3]

    def test_a_number_skips_a_cadenza_which_its_label_finds(self):
        rows = _rows(CADENZA)

        assert [r.label for r in find_rows(rows, 2)] == ["2"]
        assert [r.label for r in find_rows(rows, label="2c")] == ["2c"]
        assert find_rows(rows, label="2c", pass_=1) == []

    def test_a_number_and_a_label_must_both_match(self):
        rows = _rows(CADENZA)

        assert [r.label for r in find_rows(rows, 2, label="2c")] == ["2c"]
        assert find_rows(rows, 3, label="2c") == []

    def test_a_number_the_table_lacks_finds_nothing(self):
        assert find_rows(_rows(ENDINGS), 7) == []
        assert find_rows(_rows(ENDINGS), label="7") == []

    def test_no_number_and_no_label_finds_nothing(self):
        assert find_rows(_rows(ENDINGS)) == []
        assert find_rows(_rows(ENDINGS), pass_=1) == []


# Time signatures: each row's meter, by desktop#621's rules.

# What TiLiA puts on the first beat, and WP3's migration on an old file's.
DEFAULT = {"denominator": 4, "units": "1", "assumed": True}


def unit(denominator, units, assumed=False):
    return {"denominator": denominator, "units": units, "assumed": assumed}


def taps(count, beat_unit=None, *, on_beat=1):
    """The units set on a measure's `count` taps: `beat_unit` on beat `on_beat`."""
    units = [None] * count
    units[on_beat - 1] = beat_unit
    return units


def _metered_timeline(measures, first_number=1):
    """One measure per list of the units set on its beats, a beat every second from 0."""
    beats = []
    for j, units in enumerate(measures):
        for b, beat_unit in enumerate(units):
            mark = None if b else ({"number": first_number} if j == 0 else {})
            beats.append(
                {"time": float(len(beats)), "measure": mark, "beat_unit": beat_unit}
            )
    return beat_timeline(beats)


def _metered(measures, first_number=1):
    timeline = _metered_timeline(measures, first_number)
    return build_rows(document(timeline), timeline)


def _quarters(row):
    return [row.meter.quarter_length(value) for value in row.meter.beat_values]


@pytest.mark.parametrize(
    "beat_unit, count, time_signature, ts_numerator, ts_denominator, ambiguous",
    [
        (unit(8, "3"), 2, "6/8", 6, 8, False),
        (unit(8, "1"), 7, "7/8", 7, 8, False),
        (unit(8, "2+2+3"), 3, "2+2+3/8", 7, 8, False),
        (unit(8, "2+3"), 3, "2+3+2/8", 7, 8, True),
        (unit(4, "1/3"), 4, "(4/3)/4", F(4, 3), 4, False),
        (unit(8, "1/2+1"), 2, "(1/2+1)/8", F(3, 2), 8, False),
    ],
)
def test_a_time_signature_as_text_and_as_numbers(
    beat_unit, count, time_signature, ts_numerator, ts_denominator, ambiguous
):
    # The table of TimeLineAnnotator/project-management#193 (how the index shows
    # time signatures).
    (row,) = _metered([taps(count, beat_unit)])

    assert row.time_signature == time_signature
    assert (row.ts_numerator, row.ts_denominator) == (ts_numerator, ts_denominator)
    assert type(row.ts_numerator) is F
    assert type(row.ts_denominator) is int
    assert row.ambiguous == ambiguous


@pytest.mark.parametrize(
    "beat_values, denominator, text",
    [
        # All equal: their sum, when it is whole.
        ([3, 3], 8, "6/8"),
        ([1] * 7, 8, "7/8"),
        ([3], 8, "3/8"),
        ([F(1, 2)] * 4, 4, "2/4"),
        # They differ: joined by "+", as they fall in the bar.
        ([2, 2, 3], 8, "2+2+3/8"),
        ([2, 3, 2], 8, "2+3+2/8"),
        ([3, 2], 8, "3+2/8"),
        # A numerator that isn't whole, or holds a fraction: in brackets.
        ([F(1, 3)] * 4, 4, "(4/3)/4"),
        ([F(1, 2)] * 3, 4, "(3/2)/4"),
        ([F(1, 2)], 2, "(1/2)/2"),
        ([F(1, 2), 1], 8, "(1/2+1)/8"),
        ([1, F(3, 2)], 4, "(1+3/2)/4"),
    ],
)
def test_format_time_signature(beat_values, denominator, text):
    assert format_time_signature([F(v) for v in beat_values], denominator) == text


def test_timemap_six_eight_in_two():
    # Spec, US2 scenarios 1 and 2: two taps with only the default beat unit
    # read 2/4, assumed; with {8, "3"} on the downbeat they read 6/8, counted
    # in two beats of a dotted quarter.
    (tapped,) = _metered([taps(2, DEFAULT)])

    assert tapped.time_signature == "2/4"
    assert tapped.assumed

    timeline = _metered_timeline([taps(2, unit(8, "3"))])
    doc = document(timeline)
    (row,) = build_rows(doc, timeline)

    assert row.time_signature == "6/8"
    assert (row.ts_numerator, row.ts_denominator) == (6, 8)
    assert not row.assumed
    time_map = time_map_for(doc, timeline.id)
    assert [time_map.positions(t, t).beat for t in (0.0, 1.0)] == [1, 2]
    assert _quarters(row) == [F(3, 2), F(3, 2)]


def test_two_plus_three_on_two_taps_is_five_eighths():
    # Spec, US2 scenario 3.
    (row,) = _metered([taps(2, unit(8, "2+3"))])

    assert row.time_signature == "2+3/8"
    assert (row.ts_numerator, row.ts_denominator) == (5, 8)
    assert _quarters(row) == [1, F(3, 2)]
    assert not row.ambiguous


def test_a_unit_on_a_later_beat_applies_from_its_measure_until_the_next():
    # Spec, US2 scenario 4: set on the third beat of measure 10.
    measures = [
        taps(3, unit(4, "1")),
        *[taps(3)] * 8,
        taps(3, unit(8, "2"), on_beat=3),
        taps(3),
        taps(3, unit(4, "1")),
    ]
    rows = _metered(measures)

    assert [r.number for r in rows] == list(range(1, 13))
    assert [r.time_signature for r in rows] == ["3/4"] * 9 + ["6/8", "6/8", "3/4"]
    assert rows[9].meter.beat_unit_id == rows[9].beat_ids[2]
    assert rows[10].meter.beat_unit_id == rows[9].beat_ids[2]


def test_of_two_units_in_a_measure_the_first_governs_it_and_those_after():
    # Spec, US2 scenario 5.
    second = taps(4, unit(8, "1"), on_beat=2)
    second[3] = unit(2, "1")
    rows = _metered([taps(4, unit(4, "1")), second, taps(4)])

    assert [r.time_signature for r in rows] == ["4/4", "4/8", "4/8"]
    assert [r.conflicting for r in rows] == [False, True, False]
    assert rows[2].meter.beat_unit_id == rows[1].beat_ids[1]


def test_three_taps_under_two_plus_three_are_ambiguous():
    # Spec, US2 scenario 6.
    (row,) = _metered([taps(3, unit(8, "2+3"))])

    assert row.meter.beat_values == (2, 3, 2)
    assert row.time_signature == "2+3+2/8"
    assert (row.ts_numerator, row.ts_denominator) == (7, 8)
    assert row.ambiguous


def test_a_pickup_of_one_tap_under_three_eighths():
    # Spec, US2 scenario 7.
    rows = _metered([taps(1, unit(8, "3")), taps(2)], first_number=0)

    assert [(r.number, r.time_signature) for r in rows] == [(0, "3/8"), (1, "6/8")]


def test_a_numerator_that_isnt_whole():
    # Spec, US2 scenario 8: TiLiA shows "1 1/3" over 4.
    (row,) = _metered([taps(4, unit(4, "1/3"))])

    assert row.ts_numerator == F(4, 3)
    assert row.time_signature == "(4/3)/4"


def test_each_row_has_its_meter_and_the_meter_s_flags():
    # The meter is meters_of's; the row's flags and numbers are its.
    timeline = _metered_timeline(
        [
            taps(2, unit(8, "2+3")),
            taps(3),
            [unit(4, "1"), None, unit(2, "1")],
            taps(2, unit(8, "3", assumed=True)),
        ]
    )
    rows = build_rows(document(timeline), timeline)

    assert [r.meter for r in rows] == meters_of(rows_of(timeline))
    assert [(r.assumed, r.ambiguous, r.conflicting) for r in rows] == [
        (False, False, False),
        (False, True, False),
        (False, False, True),
        (True, False, False),
    ]
    assert [(r.ts_numerator, r.ts_denominator) for r in rows] == [
        r.meter.time_signature for r in rows
    ]
    assert [r.time_signature for r in rows] == ["2+3/8", "2+3+2/8", "3/4", "6/8"]


DERIVED = (
    "time_signature",
    "ts_numerator",
    "ts_denominator",
    "assumed",
    "ambiguous",
    "conflicting",
)


def test_a_row_s_time_signature_and_flags_are_computed_from_its_meter():
    # When the row is made, so nothing can make them disagree with the meter.
    six_eight, three_four = _metered(
        [taps(2, unit(8, "3")), [unit(4, "1", assumed=True), None, unit(2, "1")]]
    )

    moved = dataclasses.replace(six_eight, meter=three_four.meter)

    assert [getattr(moved, name) for name in DERIVED] == [
        "3/4",
        3,
        4,
        True,
        False,
        True,
    ]
    for name in DERIVED:
        # init=False fields: ValueError before Python 3.13, TypeError from it on
        with pytest.raises((ValueError, TypeError)):
            dataclasses.replace(six_eight, **{name: getattr(three_four, name)})


def test_a_folded_table_has_its_time_signatures():
    # A folded table has no positions yet, but its rows' other values are computed.
    timeline = _metered_timeline([taps(2, unit(8, "3")), taps(3)])
    timeline.measures.rows[1].next = [timeline.measures.rows[0].id]
    rows = build_rows(document(timeline), timeline)

    assert [r.folded for r in rows] == [True, True]
    assert [r.time_signature for r in rows] == ["6/8", "9/8"]
