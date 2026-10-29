"""Old beat timelines: their lists by measure fitted to their beats as TiLiA
fits them when it opens a file, then turned into marks on the downbeats, and
desktop#621's beat units moved onto the beats they name
(contracts/migration.md, *Beat timelines*)."""

import json
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla.migrate import beats, to_1

OLD = Path(__file__).parent / "old"
BEAT_TIMELINE = "9"


# The fitting, case by case: TiLiA's `recalculate_measures` as it runs when a
# file is opened, and the prototype's tests of it (ql_timemap.py, 15800fb).


def fit(beat_count, counts, numbers, pattern=(4,)):
    return beats.fit(beat_count, counts, numbers, list(pattern))


def test_lists_that_agree_with_the_beats_are_kept():
    assert fit(8, [4, 4], [1, 2]) == beats.Fitted([4, 4], [1, 2])


@pytest.mark.parametrize(
    "beat_count, pattern, counts, numbers",
    [
        # many_beats.tla: 1000 beats, 250 measures of 4.
        (1000, [4], [4] * 250, list(range(1, 251))),
        (10, [4], [4, 4, 2], [1, 2, 3]),
        (12, [3, 4], [3, 4, 3, 2], [1, 2, 3, 4]),
        (1, [4], [1], [1]),
        (0, [4], [], []),
    ],
)
def test_empty_lists_are_filled_from_the_beat_pattern(
    beat_count, pattern, counts, numbers
):
    assert fit(beat_count, [], [], pattern) == beats.Fitted(counts, numbers)


def test_missing_lists_are_empty_ones():
    assert fit(10, None, None) == beats.Fitted([4, 4, 2], [1, 2, 3])


def test_extra_beats_make_new_measures_numbered_on():
    assert fit(11, [4, 4], [1, 2]) == beats.Fitted([4, 4, 3], [1, 2, 3])


def test_an_incomplete_last_measure_is_topped_up_first():
    assert fit(9, [4, 2], [7, 8]) == beats.Fitted([4, 4, 1], [7, 8, 9])
    # TiLiA's own test of the extension: 3 beats after a measure of 2 of 4.
    assert fit(5, [2], [1]) == beats.Fitted([4, 1], [1, 2])


def test_new_measures_follow_the_pattern_from_the_last_measures_entry():
    # Measure 2 is the pattern's second entry (4), complete; the new ones
    # take the next entries, 3 then 4.
    assert fit(14, [3, 4], [1, 2], [3, 4]) == beats.Fitted([3, 4, 3, 4], [1, 2, 3, 4])
    # Measure 3 is the first entry again (3), with 1 of its 3 beats.
    assert fit(12, [3, 4, 1], [1, 2, 3], [3, 4]) == beats.Fitted(
        [3, 4, 3, 2], [1, 2, 3, 4]
    )


def test_a_number_beyond_the_measures_is_kept_for_a_new_measure():
    # TiLiA numbers only the measures that have no number yet.
    assert fit(9, [4], [5, 9, 12]) == beats.Fitted([4, 4, 1], [5, 9, 12])


def test_missing_beats_come_off_the_end_with_their_numbers():
    assert fit(9, [4, 4, 4], [1, 2, 3]) == beats.Fitted([4, 4, 1], [1, 2, 3])
    assert fit(7, [4, 4, 4], [1, 2, 3]) == beats.Fitted([4, 3], [1, 2])
    assert fit(0, [4, 4], [1, 2]) == beats.Fitted([], [])


def test_renumbered_measures_keep_their_numbers():
    numbers = [41, 42, 44, 45]
    assert fit(8, [2, 2, 2, 2], numbers, [2]) == beats.Fitted([2] * 4, numbers)


def test_surplus_numbers_are_left_out():
    assert fit(8, [4, 4], [1, 2, 3]) == beats.Fitted([4, 4], [1, 2])


def test_whole_numbers_written_with_a_fraction_are_read():
    assert fit(8, [4.0, 4.0], [1.0, 2.0]) == beats.Fitted([4, 4], [1, 2])


def test_a_last_measure_fuller_than_its_pattern_entry_ends_before_new_beats():
    # TiLiA 0.7.1 and later: the new beats start a measure of their own.
    # TiLiA 0.7.0 couldn't open such a timeline, and the prototype follows
    # it (TimeLineAnnotator/project-management#360, a decision).
    assert fit(8, [6], [1]) == beats.Fitted([6, 2], [1, 2])
    assert fit(13, [4, 6], [1, 2], [4]) == beats.Fitted([4, 6, 3], [1, 2, 3])


@pytest.mark.parametrize(
    "beat_count, counts, numbers, shown",
    [
        # TiLiA can't show a measure without a printed number: it shows the
        # measures before it, and stops.
        (8, [4, 4], [1], ([4], [1])),
        (8, [4, 4], [], ([], [])),
        (12, [4, 4, 4], [1, 2], ([4, 4], [1, 2])),
        # Lists TiLiA can't read: the measures before the first entry it can't.
        (8, [4, "4"], [1, 2], ([4], [1])),
        (8, [4, 0, 4], [1, 2, 3], ([4], [1])),
        (8, [4, -4, 8], [1, 2, 3], ([4], [1])),
        (8, [4, True], [1, 2], ([4], [1])),
        (8, [4, 4], [1.5, 2], ([], [])),
        (8, [4, 4], [1, None], ([4], [1])),
        (8, "4 4", [1, 2], ([], [])),
        (8, [4, 4], {"1": 4}, ([], [])),
        # ...and never past the last beat.
        (6, [4, 4, "x"], [1, 2, 3], ([4, 2], [1, 2])),
        (4, [4, 4, "x"], [1, 2, 3], ([4], [1])),
    ],
)
def test_lists_tilia_cant_open_keep_the_measures_it_would_show(
    beat_count, counts, numbers, shown
):
    fitted = fit(beat_count, counts, numbers)
    assert (fitted.counts, fitted.numbers) == shown
    assert fitted.problem


@pytest.mark.parametrize(
    "pattern, bars",
    [
        ("4", [4]),
        ("4 4 3", [4, 4, 3]),
        ("2[3 4] 1", [3, 4, 3, 4, 1]),
        # One that doesn't parse counts as "4"
        # (TimeLineAnnotator/project-management#310).
        ("", [4]),
        ("4 x", [4]),
        ("0", [4]),
        ("[", [4]),
        (None, [4]),
        (4, [4]),
    ],
)
def test_the_beat_pattern_is_read_by_the_cores_parser(pattern, bars):
    assert beats.pattern_bars(pattern) == bars


# The marks on the downbeats


def marks(counts, numbers, force=(), beat_count=None):
    if beat_count is None:
        beat_count = sum(counts)
    return beats.marks(beats.Fitted(counts, numbers), list(force), beat_count)


def test_a_mark_on_each_measures_first_beat():
    assert marks([4, 4, 2], [1, 2, 3]) == {0: {"number": 1}, 4: {}, 8: {}}


@pytest.mark.parametrize(
    "numbers, expected",
    [
        # The first measure always has its number; the others only when it
        # isn't the previous measure's plus one.
        ([1, 2, 3, 4], [1, None, None, None]),
        ([0, 1, 2, 3], [0, None, None, None]),  # a pickup
        ([41, 42, 44, 45], [41, None, 44, None]),  # a jump
        ([1, 2, 1, 2], [1, None, 1, None]),  # a repeat written out
        ([5, 5, 6, 6], [5, 5, None, 6]),
        ([3, 2, 1, 0], [3, 2, 1, 0]),
    ],
)
def test_a_number_on_the_first_measure_and_where_it_doesnt_follow(numbers, expected):
    found = marks([2, 2, 2, 2], numbers)
    assert [found[index].get("number") for index in (0, 2, 4, 6)] == expected
    assert all(set(mark) <= {"number"} for mark in found.values())


def test_measures_to_force_display_become_force_display():
    found = marks([4, 4, 4], [1, 2, 3], force=[2, 0, 2])
    assert found == {
        0: {"number": 1, "force_display": True},
        4: {},
        8: {"force_display": True},
    }


@pytest.mark.parametrize("force", [[3], [-1], [7], ["1"], [1.5], [True], [None]])
def test_measures_to_force_display_tilia_wouldnt_show_are_left_out(force):
    # Out of range, as TiLiA drops them when it opens the file, or not a
    # measure's index.
    assert marks([4, 4, 4], [1, 2, 3], force=force) == {
        0: {"number": 1},
        4: {},
        8: {},
    }


def test_force_display_written_with_a_fraction_is_read():
    assert marks([4, 4], [1, 2], force=[1.0])[4] == {"force_display": True}


def test_no_measure_gives_a_mark_on_the_first_beat():
    # The first beat always has one (FR-081); TiLiA shows no measure there.
    assert marks([], [], beat_count=8) == {0: {"number": 1}}
    assert marks([], [], beat_count=0) == {}


# Through the migration


def old_file(*timelines, version="0.7.0"):
    """An old file holding these timelines, each a pair (old id, timeline)."""
    return {
        "file_path": "C:/Users/user/Documents/TiLiA/piece.tla",
        "media_path": "",
        "media_metadata": {"title": "Piece", "media length": 100},
        "timelines": {
            "1": {
                "kind": "Slider",
                "ordinal": 1,
                "height": 40,
                "is_visible": True,
                "components": {},
            },
            **dict(timelines),
        },
        "version": version,
        "app_name": "TiLiA",
    }


def beat_timeline(times, *, ordinal=2, ids=None, **keys):
    """An old beat timeline with a beat at each time, its ids from 10 on,
    in the order given."""
    ids = ids or [str(10 + index) for index in range(len(times))]
    timeline = {
        "kind": "Beat",
        "beat_pattern": [4],
        "measure_numbers": [],
        "beats_in_measure": [],
        "measures_to_force_display": [],
        "height": 35,
        "is_visible": True,
        "name": "Beats",
        "ordinal": ordinal,
        "components": {
            beat_id: {"time": time, "kind": "BEAT"}
            for beat_id, time in zip(ids, times, strict=True)
        },
    }
    timeline.update(keys)
    return BEAT_TIMELINE, timeline


def read(content):
    return tla.loads(json.dumps(content).encode())


def beat_timeline_of(doc):
    return next(tl for tl in doc.timelines.values() if tl.kind == "beat")


def written(doc):
    """The beat timeline as written, and its beats in time order."""
    content = json.loads(tla.canonical_bytes(doc))
    timeline = next(tl for tl in content["timelines"].values() if tl["kind"] == "Beat")
    components = sorted(timeline["components"].values(), key=lambda b: b["time"])
    return timeline, components


def table(doc):
    rows = beat_timeline_of(doc).measures.rows
    return [(row.number, row.label, len(row.beats)) for row in rows]


def test_many_beats_gives_250_measures_of_4():
    doc = tla.read(OLD / "0.5.15.0-many-beats.tla")
    rows = beat_timeline_of(doc).measures.rows
    assert [len(row.beats) for row in rows] == [4] * 250
    assert [row.number for row in rows] == list(range(1, 251))
    timeline, components = written(doc)
    assert [b.get("measure") for b in components[:9]] == [
        {"number": 1},
        None,
        None,
        None,
        {},
        None,
        None,
        None,
        {},
    ]
    assert sum("measure" in b for b in components) == 250


def test_the_s4_file_has_the_measures_tilia_shows():
    # Its lists agree with its 273 beats, so TiLiA keeps them as they are.
    path = OLD / "0.6.0-s4-10.tla"
    old = next(
        tl
        for tl in json.loads(path.read_bytes())["timelines"].values()
        if tl["kind"] == "Beat"
    )
    timeline = beat_timeline_of(tla.read(path))
    rows = timeline.measures.rows
    assert [len(row.beats) for row in rows] == old["beats_in_measure"]
    assert [row.number for row in rows] == old["measure_numbers"]
    times = sorted(c["time"] for c in old["components"].values())
    downbeats = [timeline.components[row.id].attrs["time"] for row in rows]
    starts = [0]
    for count in old["beats_in_measure"][:-1]:
        starts.append(starts[-1] + count)
    assert downbeats == [times[start] for start in starts]


@pytest.mark.parametrize(
    "name",
    [
        "0.0.96.tla",
        "0.0.96-saved-by-0.7.0.tla",
        "0.5.15.tla",
        "0.5.15-saved-by-0.7.0.tla",
        "0.7.0.tla",
    ],
)
def test_each_old_fixture_has_three_measures_of_four(name):
    # 0.0.96 saved its lists empty: they are filled from the pattern, [4].
    doc = tla.read(OLD / name)
    assert table(doc) == [(1, "1", 4), (2, "2", 4), (3, "3", 4)]
    timeline = beat_timeline_of(doc)
    times = [
        timeline.components[b].attrs["time"] for b in timeline.measures.rows[0].beats
    ]
    assert times == sorted(times)


def test_the_beats_are_taken_in_time_order_whatever_the_files_order():
    doc = read(
        old_file(
            beat_timeline(
                [5.0, 1.0, 0.0, 3.0, 2.0, 4.0],
                beats_in_measure=[2, 4],
                measure_numbers=[0, 1],
            )
        )
    )
    _, components = written(doc)
    assert [(b["time"], b.get("measure")) for b in components] == [
        (0.0, {"number": 0}),
        (1.0, None),
        (2.0, {}),
        (3.0, None),
        (4.0, None),
        (5.0, None),
    ]
    assert table(doc) == [(0, "0", 2), (1, "1", 4)]


def test_a_beat_at_the_time_of_an_earlier_one_is_dropped_with_a_warning():
    # As TiLiA drops it when it opens the file: the first in the file's order
    # stays. 1 and 1.0 are the same time.
    doc = read(
        old_file(
            beat_timeline(
                [3.0, 0.0, 1.0, 2.0, 1, 4.0, 5.0, 6.0, 7.0],
                ids=["13", "10", "11", "12", "21", "14", "15", "16", "17"],
                beats_in_measure=[4, 4],
                measure_numbers=[1, 2],
            )
        )
    )
    timeline = beat_timeline_of(doc)
    assert len(timeline.components) == 8
    assert table(doc) == [(1, "1", 4), (2, "2", 4)]
    assert [(w.place, w.line) for w in doc.warnings] == [
        ("/timelines/9/components/21", None)
    ]
    assert "same time" in doc.warnings[0].message


def test_a_beat_without_a_time_is_dropped_with_a_warning():
    # TiLiA can't make a beat without a time, so it skips it when it opens the
    # file, and so does the migration.
    _, timeline = beat_timeline([0.0, 1.0, 2.0, 3.0, 4.0])
    timeline["components"]["20"] = {"kind": "BEAT"}
    timeline["components"]["21"] = {"kind": "BEAT", "time": None}
    doc = read(old_file((BEAT_TIMELINE, timeline)))
    assert len(beat_timeline_of(doc).components) == 5
    assert table(doc) == [(1, "1", 4), (2, "2", 1)]
    assert [w.place for w in doc.warnings] == [
        "/timelines/9/components/20",
        "/timelines/9/components/21",
    ]


def test_a_number_on_the_first_measure_and_where_it_doesnt_follow_on_through():
    doc = read(
        old_file(
            beat_timeline(
                [float(t) for t in range(8)],
                beats_in_measure=[2, 2, 2, 2],
                measure_numbers=[41, 42, 44, 45],
                beat_pattern=[2],
            )
        )
    )
    _, components = written(doc)
    assert [b.get("measure") for b in components[::2]] == [
        {"number": 41},
        {},
        {"number": 44},
        {},
    ]
    assert table(doc) == [(41, "41", 2), (42, "42", 2), (44, "44", 2), (45, "45", 2)]


def test_measures_to_force_display_become_marks():
    doc = read(
        old_file(
            beat_timeline(
                [float(t) for t in range(12)],
                beats_in_measure=[4, 4, 4],
                measure_numbers=[1, 2, 3],
                measures_to_force_display=[2, 0, 2, 9],
            )
        )
    )
    _, components = written(doc)
    assert [b.get("measure") for b in components[::4]] == [
        {"number": 1, "force_display": True},
        {},
        {"force_display": True},
    ]
    rows = beat_timeline_of(doc).measures.rows
    assert [row.force_display for row in rows] == [True, False, True]


def test_the_lists_by_measure_are_gone_and_the_source_is_unknown():
    doc = read(old_file(beat_timeline([0.0, 1.0, 2.0, 3.0, 4.0])))
    timeline, components = written(doc)
    for key in ("measure_numbers", "beats_in_measure", "measures_to_force_display"):
        assert key not in timeline
    assert timeline["measure_source"] == "unknown"
    assert beat_timeline_of(doc).measures.source == "unknown"
    assert all("source" not in b.get("measure", {}) for b in components)
    assert {row.source for row in beat_timeline_of(doc).measures.rows} == {"unknown"}


def test_the_beat_pattern_becomes_text_and_stays_the_rule_for_new_measures():
    doc = read(
        old_file(beat_timeline([float(t) for t in range(11)], beat_pattern=[4, 4, 3]))
    )
    timeline, _ = written(doc)
    assert timeline["beat_pattern"] == "4 4 3"
    assert table(doc) == [(1, "1", 4), (2, "2", 4), (3, "3", 3)]


def test_a_beat_pattern_that_doesnt_parse_counts_as_4_and_is_kept():
    doc = read(
        old_file(beat_timeline([float(t) for t in range(6)], beat_pattern=[3, "x"]))
    )
    timeline, _ = written(doc)
    assert timeline["beat_pattern"] == "3 x"
    assert table(doc) == [(1, "1", 4), (2, "2", 2)]


@pytest.mark.parametrize(
    "keys, written_value",
    [
        ({}, False),  # before time signatures: written, since the default is true
        ({"show_time_signatures": None}, False),
        ({"show_time_signatures": False}, False),
        ({"show_time_signatures": True}, None),  # desktop#621's: left out, true
    ],
)
def test_show_time_signatures_is_false_when_the_old_file_has_none(keys, written_value):
    doc = read(old_file(beat_timeline([0.0, 1.0], **keys)))
    timeline, _ = written(doc)
    assert timeline.get("show_time_signatures") == written_value
    assert beat_timeline_of(doc).attrs["show_time_signatures"] is bool(
        written_value is None
    )


def test_without_beat_units_the_first_beat_gets_the_default_assumed():
    # The first by time, not in the file's order.
    doc = read(old_file(beat_timeline([2.0, 1.0, 0.5, 3.0])))
    _, components = written(doc)
    assert components[0]["beat_unit"] == {
        "denominator": 4,
        "units": "1",
        "assumed": True,
    }
    assert ["beat_unit" in b for b in components] == [True, False, False, False]


def beat_unit(beat_id, denominator=4, units="1", **keys):
    return {
        "kind": "BEAT_UNIT",
        "beat_id": beat_id,
        "denominator": denominator,
        "units": units,
        **keys,
    }


def with_beat_units(times, *units, **keys):
    """An old file whose beat timeline has desktop#621's beat units, with ids
    from 100 on, in the order given."""
    key, timeline = beat_timeline(times, **keys)
    for index, unit in enumerate(units):
        timeline["components"][str(100 + index)] = unit
    return old_file((key, timeline))


def test_beat_units_move_onto_the_beats_they_name():
    doc = read(
        with_beat_units(
            [float(t) for t in range(10)],
            beat_unit(10, 4, "1", assumed=True),
            beat_unit("16", 8, "3", assumed=False),
        )
    )
    timeline = beat_timeline_of(doc)
    assert len(timeline.components) == 10  # no BEAT_UNIT left
    _, components = written(doc)
    assert components[0]["beat_unit"] == {
        "denominator": 4,
        "units": "1",
        "assumed": True,
    }
    assert components[6]["beat_unit"] == {"denominator": 8, "units": "3"}
    assert sum("beat_unit" in b for b in components) == 2
    rows = timeline.measures.rows
    assert [(r.beat_unit.denominator, r.beat_unit.units) for r in rows] == [
        (4, "1"),
        (8, "3"),
        (8, "3"),
    ]
    assert doc.warnings == []


def test_a_beat_unit_keeps_units_tilia_cant_read_with_the_readers_warning():
    doc = read(with_beat_units([0.0, 1.0], beat_unit(10, 4, "x")))
    _, components = written(doc)
    assert components[0]["beat_unit"] == {"denominator": 4, "units": "x"}
    (warning,) = doc.warnings
    assert warning.place.endswith("/beat_unit/units")


def test_two_beat_units_in_one_measure_are_kept_with_a_warning_and_counted():
    content = with_beat_units(
        [float(t) for t in range(8)],
        beat_unit(10, 4, "1"),
        beat_unit(12, 8, "3"),
    )
    doc = read(content)
    _, components = written(doc)
    assert [b.get("beat_unit") for b in components[:3]] == [
        {"denominator": 4, "units": "1"},
        None,
        {"denominator": 8, "units": "3"},
    ]
    (warning,) = doc.warnings
    assert "more than one beat unit" in warning.message
    assert len(beat_timeline_of(doc).measures.rows[0].beat_units) == 2
    changes = to_1.migrate(json.loads(json.dumps(content))).changes
    assert changes["measures_with_two_beat_units"] == 1


def test_a_beat_unit_naming_no_beat_is_dropped_with_a_warning():
    doc = read(
        with_beat_units(
            [0.0, 1.0, 2.0],
            beat_unit(10, 8, "3"),
            beat_unit(99, 4, "1"),
            beat_unit(10, 4, "2"),  # a second on one beat
        )
    )
    _, components = written(doc)
    assert components[0]["beat_unit"] == {"denominator": 8, "units": "3"}
    assert sum("beat_unit" in b for b in components) == 1
    assert [w.place for w in doc.warnings] == [
        "/timelines/9/components/101",
        "/timelines/9/components/102",
    ]


def test_a_beat_unit_on_a_dropped_beat_goes_with_it():
    doc = read(
        with_beat_units(
            [0.0, 1.0, 1.0],
            beat_unit(12, 8, "3"),
        )
    )
    _, components = written(doc)
    # Its beat was dropped: none is left, so the first beat gets the default.
    assert components[0]["beat_unit"] == {
        "denominator": 4,
        "units": "1",
        "assumed": True,
    }
    assert [w.place for w in doc.warnings] == [
        "/timelines/9/components/12",
        "/timelines/9/components/100",
    ]


def test_a_timeline_tilia_cant_open_keeps_its_beats_with_a_warning():
    doc = read(
        old_file(
            beat_timeline(
                [float(t) for t in range(12)],
                beats_in_measure=[4, 4, 4],
                measure_numbers=[1, 2],
            )
        )
    )
    assert len(beat_timeline_of(doc).components) == 12
    # The measures TiLiA would show before the one without a number.
    assert table(doc) == [(1, "1", 4), (2, "2", 8)]
    (warning,) = doc.warnings
    assert warning.place == "/timelines/9/measure_numbers"
    assert warning.line is None
    assert "can't open" in warning.message


def test_a_timeline_without_beats_gets_no_mark_and_no_unit():
    doc = read(old_file(beat_timeline([])))
    timeline, components = written(doc)
    assert components == []
    assert beat_timeline_of(doc).measures.rows == []
    assert timeline["measure_source"] == "unknown"
    assert doc.warnings == []


def test_beat_units_in_another_timeline_are_left_as_they_are():
    content = old_file(beat_timeline([0.0, 1.0]))
    content["timelines"]["5"] = {
        "kind": "Marker",
        "ordinal": 3,
        "height": 30,
        "components": {"6": beat_unit(10)},
    }
    doc = read(content)
    marker = next(tl for tl in doc.timelines.values() if tl.kind == "marker")
    (unit,) = marker.components.values()
    assert unit.extra["beat_id"] == 10


def test_the_marks_are_part_of_the_content_the_document_id_is_derived_from():
    first = read(old_file(beat_timeline([0.0, 1.0, 2.0], measure_numbers=[1])))
    renumbered = read(old_file(beat_timeline([0.0, 1.0, 2.0], measure_numbers=[0])))
    same = read(
        old_file(
            beat_timeline([0.0, 1.0, 2.0], beats_in_measure=[3], measure_numbers=[1])
        )
    )
    assert first.document_id != renumbered.document_id
    assert first.document_id == same.document_id


def test_a_migrated_file_reads_back_to_the_same_bytes():
    doc = read(
        with_beat_units(
            [float(t) for t in range(9)],
            beat_unit(10, 4, "1"),
            beat_unit(14, 8, "2+3"),
            beats_in_measure=[1, 4],
            measure_numbers=[0, 1],
            measures_to_force_display=[1],
        )
    )
    data = tla.canonical_bytes(doc)
    again = tla.loads(data)
    assert tla.canonical_bytes(again) == data
    assert table(again) == table(doc) == [(0, "0", 1), (1, "1", 4), (2, "2", 4)]
