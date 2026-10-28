"""Finding bars, and the times of a bar and a fraction of it.

The shared cases come from the app's tests of `get_time_by_measure`, which
the app's half runs too, and from TimeLineAnnotator/project-management#315,
which gives one time per pass. The tests after them are the core's own:
labels, passes, movements and cadenzas, which the app's format has no place
for.

A case that passes on one side only means the two sides differ: fix one
side, never the expected values alone.
"""

import json
import logging
from pathlib import Path

import pytest

from docs import beat_timeline, document
from tilia_core.timemap import time_map_for

EXAMPLES = json.loads(
    Path(__file__).with_name("shared_examples.json").read_text(encoding="utf-8")
)
TIMES_OF = [pytest.param(case, id=case["name"]) for case in EXAMPLES["times_of"]]

# Every assertion of the app's tests that call get_time_by_measure on two
# beats or more, and #315's cases, by the names the file gives them.
REQUIRED = [
    # test_get_times_by_measure_one_measure
    "one bar: bar 1",
    # test_get_times_by_measure_one_measures_repeating_decimal
    "three beats, then one: bar 1",
    "three beats, then one: bar 1 at 0.333, its second beat",
    "three beats, then one: bar 1 at 0.667, its third beat",
    # test_get_times_by_measure_multiple_measures
    "three bars: bar 1",
    "three bars: bar 2",
    "three bars: bar 3",
    # test_get_times_by_measure_uneven_beats_time_at_beats
    "uneven beats: bar 1 at 0",
    "uneven beats: bar 1 at 0.25, its second beat",
    "uneven beats: bar 1 at 0.5, its third beat",
    "uneven beats: bar 1 at 0.75, its fourth beat",
    # test_get_times_by_measure_fraction_is_1
    "the fraction 1: the next bar's downbeat",
    # test_get_times_by_measure_uneven_beats_time_in_between_beats
    "uneven beats: bar 1 at 0.125, between its first two beats",
    "uneven beats: bar 1 at 0.375, between its second and third",
    "uneven beats: bar 1 at 0.625, between its third and fourth",
    # test_get_time_between_last_beat_of_measure_and_first_beat_of_next_measure
    "between a bar's last beat and the next downbeat",
    # test_get_times_by_measure_index_bigger_than_max_measure
    "a bar after the last: none",
    "a bar far after the last: none",
    # test_get_times_by_fraction_in_repeat_measure_number
    "bar 1 played three times",
    "bar 2 played twice, at 0.5",
    "bar 2 played twice, at 0.75",
    "bar 3 played once, at 0.5",
    "bar 3 played once, at 0.75",
    "the end of bar 3, no bar 4: none",
    "the end of bar 3, no bar 4, as a segment's end",
    # what dev gives for an end on a downbeat, each time through
    "a segment's end on a downbeat: where bar 2 ends, each time",
    # #315
    "the last bar, between its beats",
    "passes of four and three beats",
    "a bar that doesn't exist: none",
    "the fraction 1: the downbeat after the bar, not every bar N+1's",
    "the last time through, past the last beat",
]


def test_the_file_holds_every_case():
    names = [case["name"] for case in EXAMPLES["times_of"]]

    assert [name for name in REQUIRED if name not in names] == []
    assert len(set(names)) == len(names)


@pytest.mark.parametrize("case", TIMES_OF)
def test_each_case_is_laid_out_as_the_contract_says(case):
    times = [beat["time"] for beat in case["beats"]]

    assert case["beats"][0].get("measure") is not None
    assert times == sorted(set(times))
    assert set(case["query"]) == {"number", "fraction", "segment_end"}
    assert case["expected"] == sorted(case["expected"])


@pytest.mark.parametrize("case", TIMES_OF)
def test_times_of(case):
    timeline = beat_timeline(case["beats"])
    time_map = time_map_for(document(timeline), timeline.id)
    query = case["query"]

    assert time_map.times_of(
        query["number"], query["fraction"], segment_end=query["segment_end"]
    ) == pytest.approx(case["expected"])


def time_map(*bars):
    """A beat every second from 1 s, in bars of (mark, beats); a mark is a
    number, or a dict."""
    beats, t = [], 1.0
    for mark, count in bars:
        mark = {"number": mark} if isinstance(mark, int) else mark
        for k in range(count):
            beats.append({"time": t, "measure": mark if k == 0 else None})
            t += 1.0
    timeline = beat_timeline(beats)
    return time_map_for(document(timeline), timeline.id)


def restart(number):
    return {"number": number, "restart": True}


# Two songs, each numbered from 1: bars from 1, 3, 5, then 7 and 9 s.
SONGS = ((1, 2), (2, 2), (3, 2), (restart(1), 2), (2, 2))
# Bar 1 three times, from 1, 7 and 11 s (US6, scenario 1).
REPEATS = ((1, 2), (2, 2), (3, 2), (1, 2), (2, 2), (1, 2))
# First and second endings: 10 11 12a 10 11 12b 13, two beats each.
ENDINGS = (
    (10, 2),
    (11, 2),
    ({"number": 12, "label": "12a"}, 2),
    (10, 2),
    (11, 2),
    ({"number": 12, "label": "12b"}, 2),
    (13, 2),
)
# A cadenza that shares bar 2's number: 1, 2, 2c, 3. Bar 2 ends at 5 s,
# where the cadenza starts, and bar 3 starts at 8 s.
C2 = {"number": 2, "label": "2c", "cadenza": True}
CADENZA = ((1, 2), (2, 2), (C2, 3), (3, 2))
# Two cadenzas in a row: 1, 2, 2c, 2d, 3, with bar 3 from 9 s.
CADENZAS = ((1, 2), (2, 2), (C2, 2), ({**C2, "label": "2d"}, 2), (3, 2))


class TestFind:
    def test_a_number_finds_it_in_every_movement(self):
        rows = time_map(*SONGS).find(1)

        assert [(row.count, row.movement) for row in rows] == [(1, 1), (4, 2)]

    def test_a_movement_narrows_it_to_that_movement(self):
        songs = time_map(*SONGS)

        assert [row.count for row in songs.find(1, movement=2)] == [4]
        assert [row.count for row in songs.find(1, movement=1)] == [1]
        assert [row.count for row in songs.find(label="2", movement=2)] == [5]
        assert songs.find(3, movement=2) == []

    def test_passes_count_again_in_each_movement(self):
        songs = time_map(*SONGS)

        assert [row.count for row in songs.find(1, pass_=1)] == [1, 4]
        assert [row.count for row in songs.find(1, pass_=1, movement=2)] == [4]
        assert songs.find(1, pass_=2) == []

    def test_a_movement_alone_names_no_bar(self):
        assert time_map(*SONGS).find(movement=1) == []

    def test_a_label_finds_that_measure_and_a_number_every_one(self):
        endings = time_map(*ENDINGS)

        assert [row.count for row in endings.find(label="12a")] == [3]
        assert [row.label for row in endings.find(12)] == ["12a", "12b"]

    def test_a_number_and_a_pass_find_one_measure(self):
        assert [row.count for row in time_map(*REPEATS).find(1, pass_=2)] == [4]

    def test_a_cadenza_is_found_by_its_label(self):
        cadenza = time_map(*CADENZA)

        assert [row.label for row in cadenza.find(2)] == ["2"]
        assert [row.label for row in cadenza.find(label="2c")] == ["2c"]


class TestTimesOf:
    def test_every_pass_of_a_bar(self):
        # US6, scenario 1
        assert time_map(*REPEATS).times_of(1) == [1.0, 7.0, 11.0]

    def test_a_pass_gives_that_time_through(self):
        repeats = time_map(*REPEATS)

        assert repeats.times_of(1, pass_=2) == [7.0]
        assert repeats.times_of(2, 0.5, pass_=2) == [10.0]
        assert repeats.times_of(1, pass_=4) == []

    def test_the_fraction_counts_beats(self):
        # US6, scenario 2: a four-beat bar at 0.5 is its third beat;
        # between beats the time is interpolated.
        bars = time_map((1, 4), (2, 4))

        assert bars.times_of(1, 0.5) == [3.0]
        assert bars.times_of(1, 0.375) == [2.5]
        assert bars.times_of(1, 0.875) == [4.5]

    def test_a_label_gives_that_measure_and_a_number_every_one(self):
        # US6, scenario 3
        endings = time_map(*ENDINGS)

        assert endings.times_of(label="12a") == [5.0]
        assert endings.times_of(12) == [5.0, 11.0]
        assert endings.times_of(12, label="12b") == [11.0]

    def test_a_number_and_a_pass_in_each_movement_or_in_one(self):
        # US6, scenario 4
        songs = time_map(*SONGS)

        assert songs.times_of(1, pass_=1) == [1.0, 7.0]
        assert songs.times_of(1, pass_=1, movement=2) == [7.0]
        assert songs.times_of(2, 0.5, movement=1) == [4.0]
        assert songs.times_of(3, movement=2) == []

    def test_a_cadenza_has_no_pass_and_is_found_by_its_label(self):
        # US6, scenario 4
        cadenza = time_map(*CADENZA)

        assert cadenza.times_of(2) == [3.0]
        assert cadenza.times_of(label="2c") == [5.0]
        assert cadenza.times_of(label="2c", pass_=1) == []

    def test_neither_a_number_nor_a_label_gives_no_time(self):
        assert time_map(*REPEATS).times_of(fraction=0.5) == []
        assert time_map(*SONGS).times_of(movement=2) == []

    @pytest.mark.parametrize("fraction", [-0.1, 1.5, float("nan")])
    def test_a_fraction_outside_0_to_1_gives_no_time_and_a_warning(
        self, fraction, caplog
    ):
        with caplog.at_level(logging.WARNING, logger="tilia_core.timemap.lookup"):
            assert time_map(*REPEATS).times_of(1, fraction) == []

        assert "from 0 to 1" in caplog.text

    def test_a_fraction_on_a_beat_at_3_decimals_is_that_beat(self):
        # TiLiA rounds to 3 decimals, so 0.333 is the second of three beats
        # and 1/3 is too; a fraction that rounds elsewhere is interpolated.
        bars = time_map((1, 3), (2, 1))

        assert bars.times_of(1, 0.333) == [2.0]
        assert bars.times_of(1, 1 / 3) == [2.0]
        assert bars.times_of(1, 0.3336) == [pytest.approx(2.0008)]

    def test_between_beats_the_fraction_is_exact(self):
        # Not TiLiA's 2.5005 today, which interpolates from 0.333 (#315)
        bars = time_map((1, 3), (2, 1))

        assert bars.times_of(1, 0.5) == [2.5]
        assert bars.times_of(1, 1 / 6) == [1.5]

    def test_a_bar_that_does_not_exist_gives_no_time(self):
        bars = time_map((1, 2), (2, 2), (4, 2), (5, 2))

        assert bars.times_of(3) == []
        assert bars.times_of(3, 0.5) == []
        assert bars.times_of(3, segment_end=True) == []

    def test_the_fraction_1_needs_the_next_bar_to_be_n_plus_1(self):
        repeats = time_map(*REPEATS)

        assert repeats.times_of(1, 1.0) == [3.0, 9.0]  # the last bar 1 ends the piece
        assert repeats.times_of(3, 1.0) == []  # bar 1 follows it

    def test_the_fraction_1_as_a_segments_end_is_the_bars_end(self):
        repeats = time_map(*REPEATS)

        assert repeats.times_of(3, 1.0, segment_end=True) == [7.0]
        # the last bar 1 ends the piece: it lasts as long as the bar 2 before it
        assert repeats.times_of(1, 1.0, segment_end=True) == [3.0, 9.0, 13.0]

    def test_past_the_last_beat_the_bar_before_gives_the_length(self):
        # The last bar lasts as long as the bar before it in the timeline,
        # whatever its number (TiLiA's projection), not FR-011's closing
        # barline: two beats, in a bar 4 s long.
        bars = time_map((1, 4), ({"number": 7}, 2))

        assert bars.times_of(7, 0.75) == [7.5]
        assert bars.times_of(7, 1.0, segment_end=True) == [9.0]
        assert bars.times_of(7, 1.0) == []

    def test_one_bar_alone_gives_no_time_past_its_last_beat(self):
        # Nothing to project from, as in TiLiA
        bars = time_map((1, 2))

        assert bars.times_of(1, 0.25) == [1.5]
        assert bars.times_of(1, 0.75) == []
        assert bars.times_of(1, 1.0, segment_end=True) == []

    def test_a_pickup(self):
        bars = time_map((0, 1), (1, 4), (2, 4), (3, 2))

        assert bars.times_of(0) == [1.0]
        assert bars.times_of(0, 0.5) == [1.5]
        assert bars.times_of(0, 1.0) == [2.0]
        assert bars.times_of(0, 1.0, segment_end=True) == [2.0]

    def test_a_segments_end_on_an_inner_beat_is_that_beat(self):
        assert time_map(*REPEATS).times_of(2, 0.5, segment_end=True) == [4.0, 10.0]


class TestASegmentsEndOnADownbeat:
    """As a segment's end, the fraction 0 of bar N also gives where each time
    through the bar numbered just below it ends: an end on a downbeat belongs
    to the bar before. With a pass, a label or a movement, an end that leads
    into a bar N the query doesn't name is left out
    (TimeLineAnnotator/project-management#321)."""

    def test_where_the_bar_before_ends_each_time(self):
        repeats = time_map(*REPEATS)

        assert repeats.times_of(3, segment_end=True) == [5.0, 11.0]
        assert repeats.times_of(3) == [5.0]

    def test_the_first_bar_has_no_bar_before(self):
        assert time_map(*REPEATS).times_of(1, segment_end=True) == [1.0, 7.0, 11.0]

    def test_the_bar_before_is_the_number_just_below_that_the_table_has(self):
        bars = time_map((1, 2), (2, 2), (4, 2), (5, 2))

        assert bars.times_of(4, segment_end=True) == [5.0]
        # the second bar 2 leads to bar 5, and ends where it starts
        cut = time_map((1, 2), (2, 2), (4, 2), (1, 2), (2, 2), (5, 2))

        assert cut.times_of(4, segment_end=True) == [5.0, 11.0]

    def test_a_label_leaves_out_the_ends_that_lead_into_another_bar_n(self):
        endings = time_map(*ENDINGS)

        assert endings.times_of(12, segment_end=True) == [5.0, 11.0]
        assert endings.times_of(label="12b", segment_end=True) == [11.0]
        assert endings.times_of(label="12a", segment_end=True) == [5.0]

    def test_a_pass_gives_the_bar_befores_end_in_that_pass(self):
        repeats = time_map(*REPEATS)

        assert repeats.times_of(3, pass_=1, segment_end=True) == [5.0]
        assert repeats.times_of(3, pass_=2, segment_end=True) == []

    def test_a_movement_gives_the_bar_befores_ends_in_that_movement(self):
        songs = time_map(*SONGS)

        assert songs.times_of(2, segment_end=True) == [3.0, 9.0]
        assert songs.times_of(2, movement=2, segment_end=True) == [9.0]


class TestACadenzaBelongsToTheBarBeforeIt:
    """An end of bar N-1 that leads into a cadenza is taken after the
    cadenza, or after the last of a run of them, and then counts as any
    other end of bar N-1 does, whatever follows the cadenza; a pass, a label
    or a movement judges it by the bar after the cadenza. A cadenza moves an
    end and never removes one. The fraction 1 of bar N-1 gives the downbeat
    after the cadenza when that bar is numbered N
    (TimeLineAnnotator/project-management#339)."""

    def test_a_section_that_ends_at_the_bar_after_a_cadenza_holds_it(self):
        cadenza = time_map(*CADENZA)

        assert cadenza.times_of(3, segment_end=True) == [8.0]
        assert cadenza.times_of(3) == [8.0]

    def test_the_fraction_1_of_the_bar_before_is_the_downbeat_after_it(self):
        assert time_map(*CADENZA).times_of(2, 1.0) == [8.0]

    def test_after_a_run_of_cadenzas_the_last_one(self):
        cadenzas = time_map(*CADENZAS)

        assert cadenzas.times_of(3, segment_end=True) == [9.0]
        assert cadenzas.times_of(2, 1.0) == [9.0]

    def test_a_cadenza_that_leads_into_another_bar_moves_the_end(self):
        # 1, 2, 3, 1, 2, 2c, 1: the second bar 2 and its cadenza lead back
        # to bar 1, at 13 s. Without the cadenza, 1, 2, 3, 1, 2, 1 gives
        # [5.0, 11.0]: the second end moves past the cadenza and stays.
        back = time_map((1, 2), (2, 2), (3, 2), (1, 2), (2, 2), (C2, 2), (1, 2))

        assert back.times_of(3, segment_end=True) == [5.0, 13.0]
        assert back.times_of(2, 1.0) == [5.0]

    def test_a_cadenza_that_ends_the_piece_moves_the_end_to_its_own(self):
        # 1, 2, 3, 1, 2, 2c: the cadenza, the last row, lasts as long as the
        # row before it (TiLiA's projection): it ends at 11 s + 2 s.
        last = time_map((1, 2), (2, 2), (3, 2), (1, 2), (2, 2), (C2, 2))

        assert last.times_of(3, segment_end=True) == [5.0, 13.0]

    def test_a_cadenza_that_ends_a_movement_moves_the_end_to_its_own(self):
        # 1, 2, 2c, then a second song 1, 2, 3: the first song's bar 2 and
        # its cadenza lead into the second song's bar 1, at 7 s.
        songs = time_map((1, 2), (2, 2), (C2, 2), (restart(1), 2), (2, 2), (3, 2))

        assert songs.times_of(3, segment_end=True) == [7.0, 11.0]
        assert songs.times_of(3, movement=2, segment_end=True) == [11.0]
        assert songs.times_of(2, 1.0, segment_end=True) == [7.0, 11.0]

    def test_a_pass_across_a_repeat(self):
        # 1, 2, 3, 1, 2, 2c, 3: the cadenza comes the second time only;
        # bar 3 starts at 5 and 13 s.
        repeat = time_map((1, 2), (2, 2), (3, 2), (1, 2), (2, 2), (C2, 2), (3, 2))

        assert repeat.times_of(3, pass_=2, segment_end=True) == [13.0]
        assert repeat.times_of(3, pass_=1, segment_end=True) == [5.0]
        assert repeat.times_of(3, segment_end=True) == [5.0, 13.0]
        assert repeat.times_of(2, 1.0) == [5.0, 13.0]
        assert repeat.times_of(2, 1.0, pass_=2) == [13.0]

    def test_a_label_is_judged_at_the_bar_after_the_cadenza(self):
        # 10, 11, 12a, 10, 11, 11c, 12b, 13: the second bar 11 leads into
        # 12b through its cadenza; 12a starts at 5 s and 12b at 13 s.
        endings = time_map(
            (10, 2),
            (11, 2),
            ({"number": 12, "label": "12a"}, 2),
            (10, 2),
            (11, 2),
            ({"number": 11, "label": "11c", "cadenza": True}, 2),
            ({"number": 12, "label": "12b"}, 2),
            (13, 2),
        )

        assert endings.times_of(label="12a", segment_end=True) == [5.0]
        assert endings.times_of(label="12b", segment_end=True) == [13.0]
        assert endings.times_of(12, segment_end=True) == [5.0, 13.0]
        assert endings.times_of(11, 1.0) == [5.0, 13.0]

    def test_a_movement(self):
        # 1, 2, 2c, 3, then a second song 1, 2, 3: bar 3 from 7 and 13 s.
        songs = time_map(
            (1, 2), (2, 2), (C2, 2), (3, 2), (restart(1), 2), (2, 2), (3, 2)
        )

        assert songs.times_of(3, movement=1, segment_end=True) == [7.0]
        assert songs.times_of(3, segment_end=True) == [7.0, 13.0]

    # Cases the rule leaves open, read as "the cadenza is part of the bar
    # before it".

    def test_as_a_segments_end_the_fraction_1_is_where_the_cadenza_ends(self):
        assert time_map(*CADENZA).times_of(2, 1.0, segment_end=True) == [8.0]
        assert time_map(*CADENZAS).times_of(2, 1.0, segment_end=True) == [9.0]
        # A cadenza that ends the piece lasts as long as the row before it,
        # as the last row does (TiLiA's projection): 11 s + 2 s.
        last = time_map((1, 2), (2, 2), (3, 2), (1, 2), (2, 2), (C2, 2))

        assert last.times_of(2, 1.0, segment_end=True) == [5.0, 13.0]

    def test_a_fraction_below_1_counts_the_bars_own_beats(self):
        # Between bar 2's last beat and the cadenza's start, not its end
        assert time_map(*CADENZA).times_of(2, 0.75) == [4.5]
        assert time_map(*CADENZA).times_of(2, 0.75, segment_end=True) == [4.5]

    def test_a_cadenza_named_by_its_label_is_that_measure_alone(self):
        cadenza = time_map(*CADENZA)

        assert cadenza.times_of(label="2c", fraction=1.0) == [8.0]
        assert cadenza.times_of(label="2c", segment_end=True) == [5.0]
        cadenzas = time_map(*CADENZAS)

        # 2d follows 2c, and is numbered 2, not 3
        assert cadenzas.times_of(label="2c", fraction=1.0) == []
        assert cadenzas.times_of(label="2c", fraction=1.0, segment_end=True) == [7.0]

    def test_a_cadenza_that_starts_a_movement_belongs_to_it(self):
        # 1, 2, then a second song that opens with a cadenza: 0c, 1, 2, 3.
        # The first song's bar 2 ends where the second song starts, at 5 s,
        # as it would before a bar 1 that restarts the count.
        opening = {"number": 0, "label": "0c", "cadenza": True, "restart": True}
        songs = time_map((1, 2), (2, 2), (opening, 2), (1, 2), (2, 2), (3, 2))

        assert songs.times_of(3, segment_end=True) == [5.0, 11.0]
        assert songs.times_of(2, 1.0, segment_end=True) == [5.0, 11.0]
        assert songs.times_of(2, 1.0) == [11.0]
