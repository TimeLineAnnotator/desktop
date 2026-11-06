import random

import pytest

from docs import beat_timeline, document, read_as_a_file
from tilia_core import tla
from tilia_core.timemap import _rows, measure_rows, meters_of, table_problem
from tilia_core.timemap._rows import closing_taps, rows_of
from tilia_core.tla.model import COMPONENT_KINDS


def _tapped_example() -> tla.Timeline:
    # The layout's tapped recording: a pickup, bars 1 and 2 with endings and a
    # repeat, then bar 3 in 6/8 tapped in two.
    marks = {
        0: {"number": 0},
        1: {},
        4: {"label": "2a"},
        7: {"number": 1},
        10: {"label": "2b"},
        13: {},
    }
    beats = [{"time": float(time), "measure": marks.get(time)} for time in range(15)]
    beats[0]["beat_unit"] = {"denominator": 4, "units": "1"}
    beats[13]["beat_unit"] = {"denominator": 8, "units": "3"}
    return beat_timeline(beats)


def test_tapped_example_gives_six_rows():
    rows = rows_of(_tapped_example())

    assert [(r.number, r.label) for r in rows] == [
        (0, "0"),
        (1, "1"),
        (2, "2a"),
        (1, "1"),
        (2, "2b"),
        (3, "3"),
    ]
    assert [len(r.beat_ids) for r in rows] == [1, 3, 3, 3, 3, 2]
    assert [r.beat_times[0] for r in rows] == [0.0, 1.0, 4.0, 7.0, 10.0, 13.0]
    assert [r.source for r in rows] == ["tapped"] * 6


def test_row_ids_are_the_downbeats():
    timeline = _tapped_example()
    rows = rows_of(timeline)

    assert [r.id for r in rows] == [r.beat_ids[0] for r in rows]
    assert rows[0].beat_times == (0.0,)


def test_unit_set_on_a_later_beat_is_listed_with_that_beat_id():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0},
            {
                "time": 2.0,
                "beat_unit": {"denominator": 8, "units": "3", "assumed": True},
            },
            {"time": 3.0},
        ]
    )
    (row,) = rows_of(timeline)

    assert row.units == (
        (row.beat_ids[2], tla.BeatUnit(denominator=8, units="3", assumed=True)),
    )


def test_unit_on_the_downbeat_and_none_elsewhere():
    timeline = _tapped_example()
    rows = rows_of(timeline)

    assert [len(r.units) for r in rows] == [1, 0, 0, 0, 0, 1]
    assert rows[5].units == (
        (rows[5].beat_ids[0], tla.BeatUnit(denominator=8, units="3")),
    )


def test_cadenza_and_restart_are_read_from_the_mark():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0, "measure": {"cadenza": True}},
            {"time": 2.0, "measure": {"restart": True, "number": 1}},
        ]
    )

    assert [(r.cadenza, r.restart) for r in rows_of(timeline)] == [
        (False, False),
        (True, False),
        (False, True),
    ]


def test_cadenza_and_restart_come_from_the_table_the_reader_builds():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0, "measure": {"cadenza": True}},
            {"time": 2.0, "measure": {"restart": True}},
        ]
    )
    read = read_as_a_file(timeline).timelines[timeline.id]

    assert [(r.cadenza, r.restart) for r in rows_of(read)] == [
        (False, False),
        (True, False),
        (False, True),
    ]


def test_other_fields_of_the_mark_are_kept():
    timeline = beat_timeline(
        [
            {
                "time": 0.0,
                "measure": {
                    "number": 1,
                    "force_display": True,
                    "source": "edited",
                    "metadata": {"tag": "a"},
                },
            },
            {"time": 1.0, "measure": {}},
        ],
        measure_source="score",
    )
    first, second = rows_of(timeline)

    assert first.force_display and first.source == "edited"
    assert first.metadata == {"tag": "a"}
    assert not second.force_display and second.source == "score"
    assert first.next is None


def test_a_timeline_without_measures_gives_no_rows():
    timeline = beat_timeline([{"time": 0.0}, {"time": 1.0}])
    timeline.measures = None

    assert rows_of(timeline) == []


def test_a_beat_unit_that_cannot_be_read_is_ignored(caplog):
    timeline = beat_timeline(
        [{"time": 0.0, "measure": {"number": 1}, "beat_unit": {"units": "1"}}]
    )
    (row,) = rows_of(timeline)

    assert row.units == ()
    assert "beat unit" in caplog.text


@pytest.mark.parametrize(
    "beat_unit",
    [
        {"denominator": 8, "units": "a"},
        {"denominator": 8, "units": "0"},
        {"denominator": 8, "units": "2+"},
        {"denominator": 8, "units": 3},
        {"denominator": 0, "units": "1"},
        {"denominator": 129, "units": "1"},
        {"denominator": "8", "units": "1"},
        {"denominator": 8, "units": "1" * 33},
    ],
)
def test_a_beat_unit_desktop_621_refuses_is_left_out(beat_unit, caplog):
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0, "beat_unit": beat_unit},
        ]
    )
    (row,) = rows_of(timeline)

    assert row.units == ()
    (warning,) = caplog.records
    assert timeline.id in warning.getMessage()
    assert row.beat_ids[1] in warning.getMessage()


def test_the_warning_shortens_a_long_unit(caplog):
    unit = {"denominator": 8, "units": "x" * 5000}
    timeline = beat_timeline([{"time": 0.0, "measure": {}, "beat_unit": unit}])
    (row,) = rows_of(timeline)

    assert row.units == ()
    assert len(caplog.records[0].getMessage()) < 300


def test_a_measure_whose_downbeat_has_no_time_is_skipped(caplog):
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0},
            {"time": 2.0, "measure": {"number": 2}},
            {"time": 3.0},
        ]
    )
    downbeat = timeline.measures.rows[1].id
    del timeline.components[downbeat].attrs["time"]

    rows = rows_of(timeline)

    assert [r.number for r in rows] == [1]
    assert all(r.id == r.beat_ids[0] for r in rows)
    assert "downbeat" in caplog.text


def test_another_beat_without_a_time_is_left_out_of_its_measure():
    timeline = beat_timeline(
        [{"time": 0.0, "measure": {"number": 1}}, {"time": 1.0}, {"time": 2.0}]
    )
    del timeline.components[timeline.measures.rows[0].beats[1]].attrs["time"]
    (row,) = rows_of(timeline)

    assert row.beat_times == (0.0, 2.0)
    assert len(row.beat_ids) == 2


def test_a_row_s_metadata_is_its_own_copy():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"metadata": {"tag": "a", "tags": ["b"]}}},
            {"time": 1.0},
        ]
    )
    (row,) = rows_of(timeline)

    row.metadata["other"] = "c"
    row.metadata["tags"].append("d")

    assert timeline.measures.rows[0].metadata == {"tag": "a", "tags": ["b"]}


def test_rows_are_read_from_a_table_with_a_problem():
    timeline = beat_timeline(
        [{"time": 1.0, "measure": {}}, {"time": 0.5}, {"time": 2.0}]
    )
    (row,) = rows_of(timeline)

    assert row.beat_times == (1.0, 0.5, 2.0)
    assert len(meters_of(rows_of(timeline))) == 1
    assert table_problem(timeline) == "beats out of time order (at 0.5)"
    assert measure_rows(document(timeline), timeline.id) == []


def test_the_helper_gives_beats_the_core_s_kind():
    timeline = _tapped_example()

    assert {c.kind for c in timeline.components.values()} == {"beat"}
    assert all(c.kind in COMPONENT_KINDS for c in timeline.components.values())


# Closing taps read as ordinary beats (TimeLineAnnotator/project-management#332),
# put among a row's beats.


def _names(timeline, names):
    """Each component's id, by what it is called in `names`, in the given order."""
    return dict(zip(names, timeline.components, strict=True))


def _beats_of_rows(timeline):
    return [row.beat_ids for row in rows_of(timeline)]


def test_closing_taps_out_of_order_on_several_rows():
    timeline = beat_timeline(
        [
            {"time": 3.5, "closing": True},
            {"time": 7.5, "closing": True},
            {"time": 2.5, "closing": True},
            {"time": 2.0, "measure": {}},
            {"time": 3.0},
            {"time": 4.0},
            {"time": 6.5, "closing": True},
            {"time": 6.0, "measure": {}},
            {"time": 7.0},
            {"time": 8.0},
        ]
    )
    id_of = _names(timeline, ["3.5", "7.5", "2.5", "2", "3", "4", "6.5", "6", "7", "8"])
    rows = rows_of(timeline)

    assert [row.beat_ids for row in rows] == [
        (id_of["2"], id_of["2.5"], id_of["3"], id_of["3.5"], id_of["4"]),
        (id_of["6"], id_of["6.5"], id_of["7"], id_of["7.5"], id_of["8"]),
    ]
    assert [row.beat_times for row in rows] == [
        (2.0, 2.5, 3.0, 3.5, 4.0),
        (6.0, 6.5, 7.0, 7.5, 8.0),
    ]
    assert [row.closing for row in rows] == [None, None]


def test_a_tap_goes_before_a_beat_at_its_time():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {}},
            {"time": 1.0},
            {"time": 1.0, "closing": True},
            {"time": 2.0},
        ]
    )
    id_of = _names(timeline, ["0", "1", "tap", "2"])

    assert _beats_of_rows(timeline) == [
        (id_of["0"], id_of["tap"], id_of["1"], id_of["2"])
    ]


def test_of_taps_at_one_time_the_last_by_id_goes_first():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {}},
            {"time": 1.0, "closing": True},
            {"time": 1.0, "closing": True},
            {"time": 1.0, "closing": True},
            {"time": 2.0},
        ]
    )
    id_of = _names(timeline, ["0", "a", "b", "c", "2"])

    assert _beats_of_rows(timeline) == [
        (id_of["0"], id_of["c"], id_of["b"], id_of["a"], id_of["2"])
    ]


def test_taps_at_one_time_given_as_an_integer_and_a_float_are_at_one_time():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {}},
            {"time": 1, "closing": True},
            {"time": 1.0, "closing": True},
            {"time": 2.0},
        ]
    )
    id_of = _names(timeline, ["0", "a", "b", "2"])

    assert _beats_of_rows(timeline) == [
        (id_of["0"], id_of["b"], id_of["a"], id_of["2"])
    ]


def test_a_tap_among_beats_out_of_order_goes_by_how_many_are_before_it():
    # Of a table `table_problem` calls broken: two of these are before the tap, so
    # it goes after two beats, wherever those two stand.
    timeline = beat_timeline(
        [
            {"time": 1.0, "measure": {}},
            {"time": 3.0},
            {"time": 2.0},
            {"time": 2.5, "closing": True},
            {"time": 4.0},
        ]
    )
    id_of = _names(timeline, ["1", "3", "2", "tap", "4"])

    assert _beats_of_rows(timeline) == [
        (id_of["1"], id_of["3"], id_of["tap"], id_of["2"], id_of["4"])
    ]


def test_a_beat_without_a_time_counts_as_before_a_tap():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {}},
            {"time": None},
            {"time": 2.0},
            {"time": 1.0, "closing": True},
            {"time": 3.0},
        ]
    )
    id_of = _names(timeline, ["0", "none", "2", "tap", "3"])

    assert _beats_of_rows(timeline) == [
        (id_of["0"], id_of["tap"], id_of["2"], id_of["3"])
    ]


def test_a_tap_in_no_row_is_in_none_of_them():
    timeline = beat_timeline(
        [
            {"time": 0.5, "closing": True},
            {"time": 1.0, "measure": {}},
            {"time": 2.0},
        ]
    )
    id_of = _names(timeline, ["tap", "1", "2"])

    assert _beats_of_rows(timeline) == [(id_of["1"], id_of["2"])]


def test_the_barline_of_a_row_closes_it_and_is_not_among_its_beats():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {}},
            {"time": 1.0, "closing": True},
            {"time": 2.0},
            {"time": 3.0, "closing": True},
            {"time": 4.0, "measure": {"restart": True}},
            {"time": 5.0, "closing": True},
        ]
    )
    id_of = _names(timeline, ["0", "misplaced", "2", "first", "4", "last"])
    rows = rows_of(timeline)

    assert [row.beat_ids for row in rows] == [
        (id_of["0"], id_of["misplaced"], id_of["2"]),
        (id_of["4"],),
    ]
    assert [row.closing for row in rows] == [3.0, 5.0]


def _as_each_is_put_in(timeline, row, taps):
    """The row's beats with its taps, as the definition has it: each tap in turn,
    after as many as are before it, those put in before it among them."""

    def before(beat, time):
        component = timeline.components.get(beat)
        at = component.attrs.get("time") if component is not None else None
        return not _rows._is_number(at) or at < time

    beats = list(row.beats)
    for tap in taps:
        if not tap.barline:
            beats.insert(sum(before(beat, tap.time) for beat in beats), tap.id)
    return beats


@pytest.mark.parametrize("seed", range(300))
def test_the_beats_with_the_taps_are_as_each_is_put_in(seed):
    pick = random.Random(seed)
    times = [0.0, 0.5, 1, 1.0, 1.5, 2, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0]
    beats = []
    for n in range(pick.randint(1, 16)):
        beat = {"time": pick.choice(times)}
        if n == 0 or pick.random() < 0.25:
            beat["measure"] = pick.choice([{}, {"restart": True}])
        if pick.random() < 0.3:
            beat["closing"] = True
        elif pick.random() < 0.1:
            beat["time"] = pick.choice([None, "soon", True, 10**400, float("nan")])
        beats.append(beat)
    if not any("measure" in beat and not beat.get("closing") for beat in beats):
        beats.append({"time": 0.0, "measure": {}})
    pick.shuffle(beats)
    timeline = beat_timeline(beats)
    taps = closing_taps(timeline)

    for row in timeline.measures.rows:
        expected = _as_each_is_put_in(
            timeline, row, [tap for tap in taps if tap.row == row.id]
        )
        assert (
            _rows._beats_with(timeline, row, [tap for tap in taps if tap.row == row.id])
            == expected
        )


def test_a_bar_of_misplaced_taps_doesnt_look_at_its_beats_for_each():
    taps = 300
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {}},
            *({"time": float(n + 1), "closing": True} for n in range(taps)),
            {"time": float(taps + 1)},
        ]
    )
    looked_at = []
    time_of = _rows._time_of

    def counted(timeline, beat_id):
        looked_at.append(beat_id)
        return time_of(timeline, beat_id)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(_rows, "_time_of", counted)
        rows = rows_of(timeline)

    assert len(rows[0].beat_ids) == taps + 2
    assert rows[0].beat_times == tuple(sorted(rows[0].beat_times))
    assert len(looked_at) < 20


def test_many_closed_movements_go_through_the_taps_once():
    class Taps(list):
        gone_through = 0

        def __iter__(self):
            Taps.gone_through += 1
            return super().__iter__()

    timeline = beat_timeline(
        [
            beat
            for n in range(20)
            for beat in (
                {"time": n * 4.0, "measure": {"restart": True} if n else {}},
                {"time": n * 4.0 + 1.0},
                {"time": n * 4.0 + 2.0, "closing": True},
            )
        ]
    )
    taps = closing_taps(timeline)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(_rows, "closing_taps", lambda timeline: Taps(taps))
        rows = rows_of(timeline)

    assert [row.closing for row in rows] == [n * 4.0 + 2.0 for n in range(20)]
    assert Taps.gone_through == 1
