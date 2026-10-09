from docs import beat_timeline
from tilia_core import tla
from tilia_core.timemap._rows import rows_of


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


def test_cadenza_and_restart_fall_back_to_the_downbeat_mark():
    timeline = beat_timeline(
        [
            {"time": 0.0, "measure": {"number": 1}},
            {"time": 1.0, "measure": {"cadenza": True}},
            {"time": 2.0, "measure": {"restart": True}},
        ]
    )
    for row in timeline.measures.rows:
        row.cadenza = row.restart = False

    assert [(r.cadenza, r.restart) for r in rows_of(timeline)] == [
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
