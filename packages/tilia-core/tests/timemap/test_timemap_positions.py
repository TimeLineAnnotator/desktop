import dataclasses
import math

import pytest

from docs import beat_timeline, document, pickup_piece
from tilia_core import tla
from tilia_core.timemap import TimeMap, time_map_for
from tilia_core.timemap.table import build_rows
from tilia_core.timemap.timemap import build_time_map


def _timeline(marks: dict[int, dict], last: int, first: int = 0) -> tla.Timeline:
    """A beat every second from `first` to `last`, with `marks` by time."""
    return beat_timeline(
        [{"time": float(t), "measure": marks.get(t)} for t in range(first, last + 1)]
    )


def _map(timeline: tla.Timeline, **kwargs) -> TimeMap:
    time_map = time_map_for(document(timeline, **kwargs), timeline.id)
    assert time_map is not None
    return time_map


def _four_four() -> TimeMap:
    # 4/4, bars 1-3, a beat every second from 0: downbeats at 0, 4 and 8.
    return _map(_timeline({0: {"number": 1}, 4: {}, 8: {}}, last=11))


def _point(time_map: TimeMap, t: float):
    return time_map.positions(t, t)


def test_timemap_every_pass():
    # T12: bar 1 played three times, from 1, 7 and 11 s, in 2/4.
    marks = {
        1: {"number": 1},
        3: {},
        5: {},
        7: {"number": 1},
        9: {},
        11: {"number": 1},
        13: {},
    }
    time_map = _map(_timeline(marks, last=14, first=1))

    starts = [time_map.positions(t, t + 1.0) for t in (1.5, 7.5, 11.5)]

    assert [p.bar for p in starts] == [1, 1, 1]
    assert [p.pass_ for p in starts] == [1, 2, 3]
    assert [p.bar_count for p in starts] == [1, 4, 6]
    assert [p.bar for p in (_point(time_map, 9.0), _point(time_map, 13.0))] == [2, 2]
    assert [p.pass_ for p in (_point(time_map, 9.0), _point(time_map, 13.0))] == [2, 3]


def test_timemap_end_excluded():
    time_map = _four_four()

    span = time_map.positions(0.0, 8.0)

    assert (span.bar, span.end_bar) == (1, 2)
    assert time_map.positions(0.0, 8.04).end_bar == 2  # snapped onto the downbeat
    assert time_map.positions(0.0, 7.96).end_bar == 2
    assert time_map.positions(0.0, 8.2).end_bar == 3
    assert time_map.positions(0.0, 4.0).end_bar == 1


def test_timemap_point_end_bar():
    time_map = _four_four()

    point = _point(time_map, 8.0)

    assert (point.bar, point.end_bar) == (3, 3)
    assert (_point(time_map, 6.5).bar, _point(time_map, 6.5).end_bar) == (2, 2)


def test_timemap_fractional_beat():
    time_map = _four_four()

    assert _point(time_map, 1.5).beat == 2.5
    assert _point(time_map, 5.25).beat == 2.25
    assert _point(time_map, 4.0).beat == 1.0
    assert _point(time_map, 7.0).beat == 4.0


def test_timemap_fractional_beat_follows_each_gap():
    # Beats at 0, 1, 1.5, 3: the fraction is linear between two beats.
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0},
            {"time": 1.5},
            {"time": 3.0},
        ]
    )
    time_map = _map(timeline)

    assert _point(time_map, 1.25).beat == 2.5
    assert _point(time_map, 2.25).beat == 3.5


def test_timemap_snapping():
    time_map = _four_four()

    on = _point(time_map, 3.95)
    before = _point(time_map, 3.85)

    assert (on.bar, on.beat, on.bar_count, on.downbeat) == (2, 1.0, 2, True)
    assert before.bar == 1 and before.beat == pytest.approx(4.85)
    assert not before.downbeat
    # within the tolerance after a beat is on it too
    assert _point(time_map, 4.08).beat == 1.0
    assert _point(time_map, 1.08).beat == 2.0
    assert _point(time_map, 1.38).beat == pytest.approx(2.38)


def test_timemap_snapping_onto_the_nearer_beat():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 0.12},
            {"time": 1.0, "measure": {}},
            {"time": 2.0},
        ]
    )
    time_map = _map(timeline)

    assert _point(time_map, 0.07).beat == 2.0
    assert _point(time_map, 0.05).beat == 1.0


def test_timemap_float_noise_never_moves_a_downbeat():
    time_map = _four_four()

    assert _point(time_map, 4.0 - 1e-9).bar == 2
    assert time_map.positions(0.0, 4.0 + 1e-9).end_bar == 1


def test_timemap_downbeat():
    time_map = _four_four()

    assert _point(time_map, 4.0).downbeat
    assert _point(time_map, 4.08).downbeat and _point(time_map, 3.93).downbeat
    assert not _point(time_map, 4.2).downbeat
    assert not _point(time_map, 5.0).downbeat
    assert _point(time_map, -0.05).downbeat


def test_timemap_off_the_map():
    time_map = _four_four()

    assert (time_map.start, time_map.end) == (0.0, 12.0)
    assert time_map.positions(-0.15, 1.0) is None
    assert _point(time_map, -0.05).bar == 1  # within the tolerance of the first beat
    assert time_map.positions(12.0, 12.5) is None
    assert time_map.positions(12.5, 13.0) is None
    assert time_map.positions(11.95, 12.0) is None  # snapped onto the closing barline
    assert time_map.positions(math.nan, 1.0) is None
    assert time_map.positions(None, None) is None


def test_timemap_end_after_the_closing_barline():
    time_map = _four_four()

    assert time_map.positions(9.0, 12.0).end_bar == 3
    assert time_map.positions(9.0, 12.05).end_bar == 3  # snapped onto it
    over = time_map.positions(9.0, 12.2)
    assert (over.bar, over.end_bar) == (3, None)
    assert time_map.positions(9.0, math.nan).end_bar is None


def test_timemap_closing_barline():
    # Spec, US1 scenario 8.
    time_map = _map(pickup_piece())

    assert time_map.end == 21.0
    last = _point(time_map, 20.5)
    assert (last.bar, last.beat, last.bar_beat_count) == (5, 3.5, 3)
    assert time_map.positions(21.5, 21.5) is None
    assert time_map.positions(21.0, 21.0) is None
    assert time_map.positions(18.0, 21.0).end_bar == 5
    assert time_map.measures()[-1] == (18.0, 21.0, 5, "5")


def test_timemap_closing_barline_at_the_end_of_the_media():
    time_map = _map(pickup_piece(), media_length=20.4)

    assert time_map.end == 20.4
    assert _point(time_map, 20.2).beat == pytest.approx(3.5)
    assert time_map.positions(20.45, 20.45) is None
    assert time_map.positions(18.0, 20.4).end_bar == 5


def test_timemap_labels():
    timeline = _timeline(
        {0: {"number": 15}, 2: {"number": 16, "label": "16a"}, 4: {}}, last=5
    )
    time_map = _map(timeline)

    labelled = _point(time_map, 2.5)
    plain = _point(time_map, 4.5)

    assert (labelled.bar, labelled.bar_label) == (16, "16a")
    assert (plain.bar, plain.bar_label) == (17, "17")
    assert [m[2:] for m in time_map.measures()] == [(15, "15"), (16, "16a"), (17, "17")]


def test_timemap_cadenza_and_restart():
    # Spec, US1 scenarios 9 and 10.
    cadenza = _map(
        _timeline(
            {
                0: {"number": 1},
                2: {},
                4: {"number": 2, "label": "2c", "cadenza": True},
                6: {},
            },
            last=7,
        )
    )
    in_cadenza = _point(cadenza, 4.5)
    assert (in_cadenza.bar, in_cadenza.bar_label) == (2, "2c")
    assert in_cadenza.pass_ is None and in_cadenza.cadenza
    assert [_point(cadenza, t).pass_ for t in (0.5, 2.5, 6.5)] == [1, 1, 1]
    assert not _point(cadenza, 2.5).cadenza

    songs = _map(
        _timeline(
            {0: {"number": 1}, 2: {}, 4: {"number": 1, "restart": True}, 6: {}},
            last=7,
        )
    )
    first, second = _point(songs, 0.5), _point(songs, 4.5)
    assert (first.bar, first.pass_, first.movement, first.bar_count) == (1, 1, 1, 1)
    assert (second.bar, second.pass_, second.movement, second.bar_count) == (1, 1, 2, 3)
    assert (_point(songs, 6.5).movement, _point(songs, 6.5).bar_count) == (2, 4)


def test_timemap_tapped_example():
    # Spec, US1 scenario 2: the layout's tapped recording, a beat every second
    # from 0 s: a pickup, bars 1 and 2 with endings and a repeat, then bar 3 in
    # 6/8 tapped in two.
    marks = {
        0: {"number": 0},
        1: {},
        4: {"label": "2a"},
        7: {"number": 1},
        10: {"label": "2b"},
        13: {},
    }
    timeline = _timeline(marks, last=14)
    timeline.components[timeline.measures.rows[-1].id].attrs["beat_unit"] = {
        "denominator": 8,
        "units": "3",
    }
    time_map = _map(timeline)

    pickup = _point(time_map, 0.0)
    assert (pickup.bar, pickup.bar_count, pickup.beat, pickup.downbeat) == (
        0,
        1,
        1.0,
        True,
    )
    second_bar_one = _point(time_map, 7.0)
    assert (second_bar_one.bar, second_bar_one.pass_, second_bar_one.bar_count) == (
        1,
        2,
        4,
    )
    second_ending = _point(time_map, 10.0)
    assert (
        second_ending.bar,
        second_ending.bar_label,
        second_ending.pass_,
        second_ending.bar_count,
    ) == (2, "2b", 2, 5)
    six_eight = _point(time_map, 14.0)
    assert (six_eight.bar, six_eight.beat, six_eight.bar_beat_count) == (3, 2.0, 2)
    assert time_map.end == 15.0
    assert [(m[0], m[1]) for m in time_map.measures()] == [
        (0.0, 1.0),
        (1.0, 4.0),
        (4.0, 7.0),
        (7.0, 10.0),
        (10.0, 13.0),
        (13.0, 15.0),
    ]


def test_timemap_fields():
    timeline = _timeline({0: {"number": 1}, 4: {}}, last=7)
    doc = document(timeline)
    time_map = _map(timeline)

    assert time_map.timeline_id == timeline.id
    assert not time_map.guessed
    assert (time_map.start, time_map.end, time_map.tolerance) == (0.0, 8.0, 0.1)
    assert time_map.measure_rows() == build_rows(doc, timeline)


def test_timemap_is_immutable():
    timeline = _timeline({0: {"number": 1}, 4: {}, 8: {}}, last=11)
    doc = document(timeline)
    time_map = time_map_for(doc, timeline.id)

    with pytest.raises(dataclasses.FrozenInstanceError):
        time_map.end = 20.0  # type: ignore[misc]
    rows = time_map.measure_rows()
    with pytest.raises(TypeError):
        rows[0].metadata["key"] = "value"  # type: ignore[index]
    rows.clear()
    assert len(time_map.measure_rows()) == 3
    assert time_map.measure_rows()[0].metadata == {}
    again = time_map_for(doc, timeline.id)
    assert time_map == again and hash(time_map) == hash(again)


def test_timemap_does_not_follow_later_edits():
    timeline = _timeline({0: {"number": 1}, 4: {}}, last=7)
    doc = document(timeline)
    time_map = time_map_for(doc, timeline.id)

    timeline.measures.rows[0].metadata["tags"] = ["edited"]
    del timeline.measures.rows[1]

    assert len(time_map.measures()) == 2
    assert time_map.measure_rows()[0].metadata == {}
    assert len(time_map_for(doc, timeline.id).measures()) == 1


def test_timemap_no_time_map():
    one_beat = beat_timeline([{"time": 0.0, "measure": {"number": 1}}])
    no_beats = beat_timeline([])
    same_time = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 12.5},
            {"time": 12.5},
            {"time": 13.0},
        ]
    )
    nearly_same_time = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0},
            {"time": 1.0 + 1e-9},
            {"time": 2.0},
        ]
    )
    out_of_order = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0},
            {"time": 3.0},
            {"time": 2.0},
        ]
    )
    no_table = _timeline({0: {"number": 1}, 2: {}}, last=3)
    no_table.measures = None
    empty_table = _timeline({0: {"number": 1}, 2: {}}, last=3)
    empty_table.measures.rows.clear()
    timeless_downbeat = _timeline({0: {"number": 1}, 2: {}, 4: {}}, last=5)
    second_downbeat = timeless_downbeat.measures.rows[1].id
    del timeless_downbeat.components[second_downbeat].attrs["time"]
    folded = _timeline({0: {"number": 1}, 2: {}}, last=3)
    folded.measures.rows[1].next = [folded.measures.rows[0].id]

    reasons = {}
    for name, timeline in [
        ("one beat", one_beat),
        ("no beats", no_beats),
        ("same time", same_time),
        ("nearly the same time", nearly_same_time),
        ("out of order", out_of_order),
        ("no table", no_table),
        ("empty table", empty_table),
        ("timeless downbeat", timeless_downbeat),
        ("folded", folded),
    ]:
        doc = document(timeline)
        assert time_map_for(doc, timeline.id) is None
        time_map, reasons[name] = build_time_map(doc, timeline)
        assert time_map is None

    assert reasons == {
        "one beat": "fewer than two beats",
        "no beats": "fewer than two beats",
        "same time": "two beats at the same time (12.5)",
        "nearly the same time": "two beats at the same time (1.0)",
        "out of order": "beats out of time order (at 2.0)",
        "no table": "no measure table",
        "empty table": "no measure table",
        "timeless downbeat": "a downbeat without a time",
        "folded": "the table lists the measures played next (`next`), "
        "which positions don't handle yet",
    }


def test_timemap_rows_of_a_folded_table_are_still_computed():
    folded = _timeline({0: {"number": 1}, 2: {}}, last=3)
    folded.measures.rows[1].next = [folded.measures.rows[0].id]

    rows = build_rows(document(folded), folded)

    assert [(r.start, r.end, r.folded) for r in rows] == [
        (0.0, 2.0, True),
        (2.0, 4.0, True),
    ]


def test_timemap_for_a_timeline_that_is_not_a_beat_timeline():
    beats = _timeline({0: {"number": 1}}, last=3)
    markers = tla.Timeline(id=tla.new_id(), kind="marker", ordinal=2)
    doc = document(beats, markers)

    assert time_map_for(doc, markers.id) is None
    assert time_map_for(doc, tla.new_id()) is None
    assert time_map_for(doc, beats.id) is not None


def test_timemap_guessed_is_kept():
    timeline = _timeline({0: {"number": 1}}, last=3)

    time_map, reason = build_time_map(document(timeline), timeline, guessed=True)

    assert time_map.guessed and reason is None
