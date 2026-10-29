"""A beat timeline's measures, marked on their downbeats, and the measure
table the reader builds from the marks (contracts/layout.md, *Beat timelines
and their measures*; data-model.md, *MeasureTable and Measure*)."""

import copy
import hashlib
import json
import uuid
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla import layout, writer

GOLDEN = Path(__file__).parent / "golden"
BASE_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z


def make_id(n):
    """The n-th id of these tests: a UUIDv7, the same on every run, in order."""
    bits = int.from_bytes(hashlib.sha256(f"measures:{n}".encode()).digest()[:10], "big")
    rand_a, rand_b = bits >> 68, bits & ((1 << 62) - 1)
    value = (BASE_MS + n) << 80 | 7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


DOCUMENT, BEATS, BARS, MARKERS = (make_id(n) for n in range(4))
B = [make_id(100 + n) for n in range(40)]  # beats, in id order


def beat(time, measure=None, beat_unit=None, closing=None, metadata=None):
    """A beat as the writer writes it, its keys in their order."""
    value = {"kind": "BEAT"}
    if time is not None:
        value["time"] = time
    for key, item in (
        ("measure", measure),
        ("beat_unit", beat_unit),
        ("closing", closing),
        ("metadata", metadata),
    ):
        if item is not None:
            value[key] = item
    return value


def beat_timeline(beats, *, name="Beats", ordinal=1, **keys):
    """A beat timeline holding `beats`, a list of (id, beat)."""
    return {
        "kind": "Beat",
        "name": name,
        "ordinal": ordinal,
        "height": 35,
        **keys,
        "components": dict(beats),
    }


def file_of(timelines):
    content = {
        "app_name": "TiLiA",
        "version": tla.FORMAT_VERSION,
        "document_id": DOCUMENT,
        "time_unit": "seconds",
        "media": {"path": "", "length": None},
        "metadata": {},
        "timelines": dict(sorted(timelines.items())),
        "scores": [],
    }
    return (json.dumps(content, indent=2, ensure_ascii=False) + "\n").encode()


def one_timeline(beats, **keys):
    return file_of({BEATS: beat_timeline(beats, **keys)})


def rows_of(doc, timeline_id=BEATS):
    return doc.timelines[timeline_id].measures.rows


def unfolded():
    """The layout's recording, tapped: a pickup, bars 1 and 2 with first and
    second endings and a repeat, then bar 3 in 6/8 tapped in two."""
    marks = {
        0: {"number": 0},
        1: {},
        4: {"label": "2a"},
        7: {"number": 1},
        10: {"label": "2b"},
        13: {},
    }
    units = {0: {"denominator": 4, "units": "1"}, 13: {"denominator": 8, "units": "3"}}
    return [
        (B[n], beat(float(n), measure=marks.get(n), beat_unit=units.get(n)))
        for n in range(15)
    ]


def test_the_layouts_unfolded_example_gives_its_table():
    data = one_timeline(unfolded())
    doc = tla.loads(data)
    rows = rows_of(doc)
    # contracts/layout.md's table, but for what WP9 computes: count is the
    # row's position, pass, start, end and the time signature.
    assert [(r.number, r.label, len(r.beats)) for r in rows] == [
        (0, "0", 1),
        (1, "1", 3),
        (2, "2a", 3),
        (1, "1", 3),
        (2, "2b", 3),
        (3, "3", 2),
    ]
    assert [r.id for r in rows] == [B[0], B[1], B[4], B[7], B[10], B[13]]
    assert [r.beats for r in rows] == [
        [B[0]],
        B[1:4],
        B[4:7],
        B[7:10],
        B[10:13],
        B[13:15],
    ]
    starts = [doc.timelines[BEATS].components[r.id].attrs["time"] for r in rows]
    assert starts == [0.0, 1.0, 4.0, 7.0, 10.0, 13.0]
    assert doc.timelines[BEATS].measures.source == "tapped"
    assert {r.source for r in rows} == {"tapped"}
    assert doc.warnings == []
    assert tla.canonical_bytes(doc) == data


def test_a_measures_number_is_the_previous_ones_plus_one_and_the_first_is_1():
    doc = tla.loads(
        one_timeline(
            [
                (B[0], beat(0.0, measure={})),
                (B[1], beat(1.0, measure={})),
                (B[2], beat(2.0, measure={"number": 7})),
                (B[3], beat(3.0, measure={"label": "8a"})),
                (B[4], beat(4.0, measure={})),
            ]
        )
    )
    assert [(r.number, r.label) for r in rows_of(doc)] == [
        (1, "1"),
        (2, "2"),
        (7, "7"),
        (8, "8a"),
        (9, "9"),
    ]


def test_the_beats_of_a_measure_are_in_time_order_whatever_their_ids():
    doc = tla.loads(
        one_timeline(
            [
                (B[0], beat(2.0, measure={})),
                (B[1], beat(0.0, measure={"number": 0})),
                (B[2], beat(3.0)),
                (B[3], beat(1.0, measure={})),
                (B[4], beat(2.5)),
            ]
        )
    )
    assert [(r.id, r.number, r.beats) for r in rows_of(doc)] == [
        (B[1], 0, [B[1]]),
        (B[3], 1, [B[3]]),
        (B[0], 2, [B[0], B[4], B[2]]),
    ]


def test_marks_at_the_same_time_follow_each_other_in_id_order():
    doc = tla.loads(
        one_timeline(
            [
                (B[0], beat(1.0, measure={"label": "b"})),
                (B[1], beat(0.0, measure={})),
                (B[2], beat(1.0, measure={"label": "c"})),
            ]
        )
    )
    assert [r.label for r in rows_of(doc)] == ["1", "b", "c"]


def test_marks_at_the_same_time_are_in_id_order_whatever_the_components_order():
    # A timeline made or changed in memory need not hold its components in
    # id order, as the reader gives them.
    doc = tla.loads(
        one_timeline(
            [
                (B[0], beat(0.0, measure={})),
                (B[1], beat(1.0, measure={"label": "b"})),
                (B[2], beat(1.0, measure={"label": "c"})),
            ]
        )
    )
    timeline = doc.timelines[BEATS]
    timeline.components = dict(reversed(list(timeline.components.items())))
    assert [r.label for r in tla.measure_table(timeline).rows] == ["1", "b", "c"]


def test_an_empty_mark_survives_a_read_and_a_write_and_marks_its_downbeat():
    data = one_timeline([(B[0], beat(0.0, measure={})), (B[1], beat(1.0))])
    assert b'"measure": {}' in data
    doc = tla.loads(data)
    assert [(r.id, r.number, r.beats) for r in rows_of(doc)] == [
        (B[0], 1, [B[0], B[1]])
    ]
    written = tla.canonical_bytes(doc)
    assert written == data
    again = tla.loads(written)
    assert rows_of(again)[0].id == B[0]


def test_an_empty_mark_made_in_memory_is_written():
    doc = tla.loads(one_timeline([(B[0], beat(0.0, measure={})), (B[1], beat(1.0))]))
    doc.timelines[BEATS].components[B[1]].attrs["measure"] = {}
    content = json.loads(tla.canonical_bytes(doc))
    assert content["timelines"][BEATS]["components"][B[1]]["measure"] == {}


def cadenza_between_2_and_3():
    return [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0, measure={})),
        (B[2], beat(2.0, measure={"number": 2, "label": "2c", "cadenza": True})),
        (B[3], beat(3.0, measure={})),
    ]


def test_a_cadenza_holds_its_number_and_label_and_bar_3_follows_from_it():
    # US8 scenario 7: only the first mark and the cadenza's hold a number.
    data = one_timeline(cadenza_between_2_and_3())
    doc = tla.loads(data)
    rows = rows_of(doc)
    assert [(r.number, r.label, r.cadenza) for r in rows] == [
        (1, "1", False),
        (2, "2", False),
        (2, "2c", True),
        (3, "3", False),
    ]
    assert tla.canonical_bytes(doc) == data


@pytest.mark.parametrize("key", ["cadenza", "restart", "force_display"])
def test_a_marks_flag_is_left_out_when_false(key):
    doc = tla.loads(one_timeline([(B[0], beat(0.0, measure={key: True}))]))
    mark = doc.timelines[BEATS].components[B[0]].attrs["measure"]
    assert getattr(rows_of(doc)[0], key) is True
    mark[key] = False
    content = json.loads(tla.canonical_bytes(doc))
    assert content["timelines"][BEATS]["components"][B[0]]["measure"] == {}
    assert getattr(rows_of(tla.loads(tla.canonical_bytes(doc)))[0], key) is False


def test_a_restart_starts_a_new_movement():
    data = one_timeline(
        [
            (B[0], beat(0.0, measure={"number": 0})),
            (B[1], beat(1.0, measure={})),
            (B[2], beat(2.0, measure={"number": 0, "restart": True})),
            (B[3], beat(3.0, measure={})),
        ]
    )
    doc = tla.loads(data)
    assert [(r.number, r.restart) for r in rows_of(doc)] == [
        (0, False),
        (1, False),
        (0, True),
        (1, False),
    ]
    assert tla.canonical_bytes(doc) == data


def folded():
    """The layout's score, folded: each written bar once, `next` for the
    playing order."""
    return [
        (
            B[0],
            beat(0, measure={"number": 0}, beat_unit={"denominator": 4, "units": "1"}),
        ),
        (B[1], beat(1, measure={"next": [B[4], B[7]]})),
        (B[4], beat(4, measure={"label": "2a", "next": [B[1]]})),
        (B[7], beat(7, measure={"number": 2, "label": "2b"})),
        (B[10], beat(10, measure={}, beat_unit={"denominator": 8, "units": "3"})),
    ]


def test_a_folded_table_names_the_measures_played_next_by_their_downbeats():
    data = file_of({BEATS: beat_timeline(folded(), measure_source="score")})
    doc = tla.loads(data)
    rows = {r.id: r for r in rows_of(doc)}
    assert rows[B[1]].next == [B[4], B[7]]
    assert rows[B[4]].next == [B[1]]
    assert rows[B[0]].next is None
    # Walking next gives the recording's order: 0, 1, 2a, 1, 2b, 3.
    order, passes, current = [], {}, rows_of(doc)[0]
    while current is not None:
        order.append(current.label)
        following = current.next
        if following is None:
            index = rows_of(doc).index(current) + 1
            current = rows_of(doc)[index] if index < len(rows) else None
        else:
            seen = passes.get(current.id, 0)
            passes[current.id] = seen + 1
            current = rows[following[seen]] if seen < len(following) else None
    assert order == ["0", "1", "2a", "1", "2b", "3"]
    assert tla.canonical_bytes(doc) == data


def every_key():
    """A mark and a beat unit with every key the layout gives them."""
    return [
        (
            B[0],
            beat(
                0.0,
                measure={
                    "number": 16,
                    "label": "16a",
                    "force_display": True,
                    "cadenza": True,
                    "restart": True,
                    "next": [B[1]],
                    "source": "edited",
                    "metadata": {"tags": ["check"], "note": "a"},
                },
                beat_unit={"denominator": 8, "units": "2+3", "assumed": True},
                metadata={"tags": ["downbeat"]},
            ),
        ),
        (B[1], beat(1.0, measure={"label": "16b"})),
    ]


def test_marks_and_beat_units_round_trip_with_every_key_in_its_place():
    data = one_timeline(every_key())
    doc = tla.loads(data)
    assert tla.canonical_bytes(doc) == data
    beat_0 = json.loads(data)["timelines"][BEATS]["components"][B[0]]
    assert list(beat_0) == ["kind", "time", "measure", "beat_unit", "metadata"]
    assert list(beat_0["measure"]) == list(layout.MEASURE)
    assert list(beat_0["beat_unit"]) == list(layout.BEAT_UNIT)
    (first, second) = rows_of(doc)
    assert (first.number, first.label, first.source, first.next) == (
        16,
        "16a",
        "edited",
        [B[1]],
    )
    assert (first.force_display, first.cadenza, first.restart) == (True, True, True)
    # The measure's metadata, kept apart from its downbeat's.
    assert first.metadata == {"tags": ["check"], "note": "a"}
    assert doc.timelines[BEATS].components[B[0]].metadata == {"tags": ["downbeat"]}
    assert first.beat_units == [tla.BeatUnit(denominator=8, units="2+3", assumed=True)]
    assert (second.number, second.label) == (17, "16b")


def test_the_keys_of_a_mark_are_written_in_the_layouts_order():
    marks = every_key()[0][1]["measure"]
    shuffled = dict(reversed(list(marks.items())))
    data = one_timeline([(B[0], beat(0.0, measure=shuffled)), (B[1], beat(1.0))])
    written = json.loads(tla.canonical_bytes(tla.loads(data)))
    assert list(written["timelines"][BEATS]["components"][B[0]]["measure"]) == list(
        layout.MEASURE
    )


SOURCES = ["tapped", "score", "import", "unknown", "edited"]


@pytest.mark.parametrize("source", SOURCES)
def test_every_source_round_trips_on_a_mark(source):
    data = one_timeline([(B[0], beat(0.0, measure={"source": source}))])
    doc = tla.loads(data)
    assert rows_of(doc)[0].source == source
    assert tla.canonical_bytes(doc) == data


@pytest.mark.parametrize("source", SOURCES)
def test_every_source_round_trips_on_the_timeline(source):
    data = one_timeline(
        [
            (B[0], beat(0.0, measure={})),
            (B[1], beat(1.0, measure={"source": "edited"})),
        ],
        **({} if source == "tapped" else {"measure_source": source}),
    )
    doc = tla.loads(data)
    assert doc.timelines[BEATS].attrs["measure_source"] == source
    table = doc.timelines[BEATS].measures
    # A mark's source overrides the table's.
    assert (table.source, [r.source for r in table.rows]) == (
        source,
        [source, "edited"],
    )
    assert tla.canonical_bytes(doc) == data


def test_a_beat_unit_is_stored_once_and_the_measures_after_take_it():
    # US8 scenario 6: set on measure 5, none on measures 6 to 9.
    beats = []
    for n in range(18):
        mark = {} if n % 2 == 0 else None
        unit = {"denominator": 8, "units": "3"} if n == 8 else None
        if n == 0:
            unit = {"denominator": 4, "units": "1"}
        beats.append((B[n], beat(float(n), measure=mark, beat_unit=unit)))
    data = one_timeline(beats)
    doc = tla.loads(data)
    units = [(r.beat_unit.denominator, r.beat_unit.units) for r in rows_of(doc)]
    assert units == [(4, "1")] * 4 + [(8, "3")] * 5
    assert [len(r.beat_units) for r in rows_of(doc)] == [1, 0, 0, 0, 1, 0, 0, 0, 0]
    written = json.loads(tla.canonical_bytes(doc))
    components = written["timelines"][BEATS]["components"].values()
    assert sum("beat_unit" in b for b in components) == 2


def test_a_unit_set_later_in_a_measure_applies_from_its_start():
    doc = tla.loads(
        one_timeline(
            [
                (
                    B[0],
                    beat(0.0, measure={}, beat_unit={"denominator": 4, "units": "1"}),
                ),
                (B[1], beat(1.0, measure={})),
                (B[2], beat(2.0, beat_unit={"denominator": 8, "units": "3"})),
            ]
        )
    )
    assert [r.beat_unit for r in rows_of(doc)] == [
        tla.BeatUnit(denominator=4, units="1"),
        tla.BeatUnit(denominator=8, units="3"),
    ]


def test_without_a_beat_unit_the_measures_are_4_1_assumed():
    doc = tla.loads(one_timeline([(B[0], beat(0.0, measure={})), (B[1], beat(1.0))]))
    assert rows_of(doc)[0].beat_unit == tla.BeatUnit(
        denominator=4, units="1", assumed=True
    )


def test_the_unit_in_force_is_the_one_the_time_map_uses():
    # WP9's meters, from the units set on the beats, give each measure the
    # unit the table says is in force.
    from tilia_core.timemap._rows import rows_of as wp9_rows
    from tilia_core.timemap.meters import meters_of
    from tilia_core.timemap.units import parse_units

    doc = tla.read(GOLDEN / "every-kind.tla")
    for timeline in doc.timelines.values():
        if timeline.kind != "beat":
            continue
        meters = meters_of(wp9_rows(timeline))
        assert len(meters) == len(timeline.measures.rows)
        for row, meter in zip(timeline.measures.rows, meters, strict=True):
            unit = row.beat_unit
            assert (
                unit.denominator,
                tuple(parse_units(unit.units).units),
                unit.assumed,
            ) == (meter.denominator, meter.units, meter.is_assumed)


def test_two_beat_timelines_have_a_table_each():
    doc = tla.read(GOLDEN / "every-kind.tla")
    tables = [tl.measures for tl in doc.timelines.values() if tl.kind == "beat"]
    assert len(tables) == 2
    assert all(table is not None and table.rows for table in tables)
    assert tables[0] is not tables[1]
    others = [tl for tl in doc.timelines.values() if tl.kind != "beat"]
    assert all(tl.measures is None for tl in others)


def test_a_timeline_names_the_measure_table_it_was_imported_against():
    # FR-086: an import by measure names its beat timeline by id.
    data = file_of(
        {
            BEATS: beat_timeline([(B[0], beat(0.0, measure={}))]),
            BARS: beat_timeline(
                [(B[1], beat(0.0, measure={}))], name="Bars", ordinal=2
            ),
            MARKERS: {
                "kind": "Marker",
                "name": "Cadences",
                "ordinal": 3,
                "height": 30,
                "measure_table": BARS,
                "components": {B[2]: {"kind": "MARKER", "time": 1.0}},
            },
        }
    )
    doc = tla.loads(data)
    assert doc.timelines[MARKERS].attrs["measure_table"] == BARS
    assert tla.canonical_bytes(doc) == data


def test_nothing_the_table_computes_is_stored():
    # US8 scenario 5: no position, count of beats, start, end, length in
    # quarters or time signature, on a beat, a mark or a timeline.
    doc = tla.read(GOLDEN / "every-kind.tla")
    content = json.loads(tla.canonical_bytes(doc))
    for timeline in content["timelines"].values():
        if timeline["kind"] != "Beat":
            continue
        assert set(timeline) <= set(layout.TIMELINE_SHAPES["beat"].keys)
        for component in timeline["components"].values():
            assert set(component) <= {
                "kind",
                "time",
                "measure",
                "beat_unit",
                "closing",
                "metadata",
            }
            assert set(component.get("measure", {})) <= set(layout.MEASURE)


def test_the_table_is_never_written():
    data = (GOLDEN / "every-kind.tla").read_bytes()
    doc = tla.loads(data)
    for timeline in doc.timelines.values():
        if timeline.measures is not None:
            for row in timeline.measures.rows:
                row.number, row.label, row.beats = 99, "x", []
            timeline.measures.source = "import"
    assert tla.canonical_bytes(doc) == data


def test_the_table_is_built_again_from_a_timeline_as_it_now_is():
    # WP9 applies its plans in memory, then builds the table again.
    doc = tla.loads(one_timeline(unfolded()))
    timeline = doc.timelines[BEATS]
    timeline.components[B[2]].attrs["measure"] = {"label": "1b"}
    table = tla.measure_table(timeline)
    assert [r.label for r in table.rows] == ["0", "1", "1b", "2a", "1", "2b", "3"]
    assert table is not timeline.measures
    assert tla.measure_table(doc.timelines[BEATS]).source == "tapped"


def test_only_a_beat_timeline_has_a_table():
    doc = tla.read(GOLDEN / "every-kind.tla")
    marker = next(tl for tl in doc.timelines.values() if tl.kind == "marker")
    assert tla.measure_table(marker) is None


def test_a_timeline_without_beats_has_an_empty_table():
    doc = tla.loads(one_timeline([]))
    table = doc.timelines[BEATS].measures
    assert table is not None and table.rows == []


# The closing barline (TimeLineAnnotator/project-management#332)


def with_closing(value=True):
    return [
        (B[0], beat(0.0, measure={})),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={})),
        (B[3], beat(3.0)),
        (B[4], beat(4.0, closing=value)),
    ]


def test_a_closing_tap_round_trips_after_the_beat_unit():
    data = one_timeline(
        [
            (B[0], beat(0.0, measure={})),
            (
                B[1],
                beat(
                    1.0,
                    measure={},
                    beat_unit={"denominator": 4, "units": "1"},
                    closing=True,
                    metadata={"tags": ["end"]},
                ),
            ),
        ]
    )
    doc = tla.loads(data)
    assert doc.timelines[BEATS].components[B[1]].attrs["closing"] is True
    assert tla.canonical_bytes(doc) == data
    beat_1 = json.loads(data)["timelines"][BEATS]["components"][B[1]]
    assert list(beat_1) == [
        "kind",
        "time",
        "measure",
        "beat_unit",
        "closing",
        "metadata",
    ]


def test_closing_is_left_out_when_false():
    doc = tla.loads(one_timeline(with_closing()))
    doc.timelines[BEATS].components[B[4]].attrs["closing"] = False
    content = json.loads(tla.canonical_bytes(doc))
    assert "closing" not in content["timelines"][BEATS]["components"][B[4]]
    unclosed = tla.loads(one_timeline(with_closing(False)))
    assert unclosed.timelines[BEATS].components[B[4]].attrs["closing"] is False
    assert b"closing" not in tla.canonical_bytes(unclosed)


def test_a_closing_tap_is_kept_out_of_the_tables_beats():
    doc = tla.loads(one_timeline(with_closing()))
    assert [r.beats for r in rows_of(doc)] == [[B[0], B[1]], [B[2], B[3]]]
    assert B[4] in doc.timelines[BEATS].components


def test_a_closing_tap_before_a_restart_ends_its_movement():
    doc = tla.loads(
        one_timeline(
            [
                (B[0], beat(0.0, measure={})),
                (B[1], beat(1.0)),
                (B[2], beat(2.0, closing=True)),
                (B[3], beat(3.0, measure={"number": 1, "restart": True})),
                (B[4], beat(4.0)),
                (B[5], beat(5.0, closing=True)),
            ]
        )
    )
    assert [(r.number, r.beats) for r in rows_of(doc)] == [
        (1, [B[0], B[1]]),
        (1, [B[3], B[4]]),
    ]


# A beat without a time (TimeLineAnnotator/project-management#285)


def test_a_beat_without_a_time_is_kept_with_a_warning_and_written_back():
    data = one_timeline(
        [(B[0], beat(0.0, measure={})), (B[1], beat(None)), (B[2], beat(2.0))]
    )
    doc = tla.loads(data)
    assert "time" not in doc.timelines[BEATS].components[B[1]].attrs
    (warning,) = doc.warnings
    assert warning.place == f"/timelines/{BEATS}/components/{B[1]}"
    assert warning.line == data.decode().split("\n").index(f'        "{B[1]}": {{') + 1
    assert warning.message == 'a beat of the timeline "Beats" has no time'
    assert tla.canonical_bytes(doc) == data
    # The table keeps it, after the beats that have a time, so that the time
    # map can say which measure lacks one.
    assert rows_of(doc)[0].beats == [B[0], B[2], B[1]]


def test_a_beat_whose_time_is_null_is_a_beat_without_a_time():
    data = one_timeline(
        [(B[0], beat(0.0, measure={})), (B[1], {"kind": "BEAT", "time": None})]
    )
    doc = tla.loads(data)
    assert [w.message for w in doc.warnings] == [
        'a beat of the timeline "Beats" has no time'
    ]
    content = json.loads(tla.canonical_bytes(doc))
    assert content["timelines"][BEATS]["components"][B[1]] == {"kind": "BEAT"}


def test_beats_without_a_time_come_last_in_id_order():
    doc = tla.loads(
        one_timeline(
            [
                (B[0], beat(None)),
                (B[1], beat(1.0, measure={})),
                (B[2], beat(None, measure={"label": "x"})),
                (B[3], beat(2.0)),
            ]
        )
    )
    assert [(r.label, r.beats) for r in rows_of(doc)] == [
        ("1", [B[1], B[3], B[0]]),
        ("x", [B[2]]),
    ]


def test_a_document_with_a_beat_without_a_time_is_written():
    doc = tla.loads(one_timeline([(B[0], beat(0.0, measure={})), (B[1], beat(1.0))]))
    del doc.timelines[BEATS].components[B[1]].attrs["time"]
    data = writer.checked_bytes(doc)
    assert [w.place for w in tla.loads(data).warnings] == [
        f"/timelines/{BEATS}/components/{B[1]}"
    ]


def test_the_golden_files_read_without_warnings():
    for path in sorted(GOLDEN.glob("*.tla")):
        doc = tla.read(path)
        assert doc.warnings == [], path.name
        for timeline in doc.timelines.values():
            if timeline.kind == "beat":
                assert copy.deepcopy(timeline.measures) == tla.measure_table(timeline)
