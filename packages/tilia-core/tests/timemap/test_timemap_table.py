import copy
import dataclasses
import logging
import pickle

import pytest

from docs import beat_timeline, document, pickup_piece
from tilia_core import tla
from tilia_core.timemap.table import build_rows, find_rows


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


def test_count_is_the_row_s_index_in_the_table():
    # The downbeat at 2 s has no time: its measure is skipped, and the others
    # keep their place in the table.
    timeline = _timeline([{"number": 1}, {}, {}])
    del timeline.components[timeline.measures.rows[1].id].attrs["time"]

    rows = build_rows(document(timeline), timeline)

    assert [(r.number, r.count) for r in rows] == [(1, 1), (3, 3)]


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
    timeline = pickup_piece()
    with caplog.at_level(logging.WARNING):
        rows = build_rows(document(timeline, media_length=media_length), timeline)

    assert rows[-1].end == 21.0
    assert timeline.id in caplog.text
    assert "media" in caplog.text


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
    with pytest.raises(TypeError):
        row.metadata["key"] = "y"  # type: ignore[index]
    timeline.measures.rows[0].metadata["tags"].append("b")
    assert row.metadata["tags"] == ("a",)
    assert row == again and hash(row) == hash(again)


def test_rows_can_be_pickled_copied_and_turned_into_dicts():
    timeline = _timeline([{"number": 1, "metadata": {"tags": ["a"], "key": "x"}}])
    (row,) = build_rows(document(timeline), timeline)

    assert pickle.loads(pickle.dumps(row)) == row
    assert copy.deepcopy(row) == row
    assert dataclasses.asdict(row)["metadata"] == {"tags": ("a",), "key": "x"}


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
