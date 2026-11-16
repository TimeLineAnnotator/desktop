"""The time map on files read through the core's reader, with the rows and
positions the spec's scenarios give.

The layout's examples (WP3's contracts/layout.md, *Beat timelines and their
measures*) are written here as files, key by key, and read with `tla.read`.
The golden file `every-kind.tla`, the core's example of every timeline kind,
holds the layout's tapped recording with a cadenza, and its folded score with
a restart. The old files are read through the migration: their time maps must
give the measures their own lists describe.
"""

import difflib
import hashlib
import json
import shutil
import uuid
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.timemap import (
    BarRef,
    TimeSignature,
    apply_plan,
    find_time_map,
    measure_rows,
    plan_time_signatures,
    time_map_for,
)
from tilia_core.timemap.timemap import FOLDED

TLA = Path(__file__).resolve().parent.parent / "tla"
EVERY_KIND = TLA / "golden" / "every-kind.tla"
OLD_FILES = sorted((TLA / "old").glob("*.tla"))
BASE_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z


def make_id(n):
    """The n-th id of these files: a UUIDv7, the same on every run, in order."""
    digest = hashlib.sha256(f"timemap-files:{n}".encode()).digest()
    bits = int.from_bytes(digest[:10], "big")
    rand_a, rand_b = bits >> 68, bits & ((1 << 62) - 1)
    value = (BASE_MS + n) << 80 | 7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


DOCUMENT, BEATS = make_id(0), make_id(1)
B = [make_id(100 + n) for n in range(40)]  # beats, in time order


def beat(time, measure=None, beat_unit=None, closing=None):
    """A beat as the writer writes it, its keys in their order."""
    value = {"kind": "BEAT", "time": time}
    for key, item in (
        ("measure", measure),
        ("beat_unit", beat_unit),
        ("closing", closing),
    ):
        if item is not None:
            value[key] = item
    return value


def file_of(beats, *, time_unit="seconds"):
    """A file holding one beat timeline of `beats`, a list of (id, beat)."""
    content = {
        "app_name": "TiLiA",
        "version": tla.FORMAT_VERSION,
        "document_id": DOCUMENT,
        "time_unit": time_unit,
        "media": {"path": "", "length": None},
        "metadata": {},
        "timelines": {
            BEATS: {
                "kind": "Beat",
                "name": "Beats",
                "ordinal": 1,
                "height": 35,
                "components": dict(beats),
            }
        },
        "scores": [],
    }
    return (json.dumps(content, indent=2, ensure_ascii=False) + "\n").encode()


def read(data, tmp_path, name="piece.tla"):
    path = tmp_path / name
    path.write_bytes(data)
    return tla.read(path)


def unit(denominator, units, assumed=False):
    value = {"denominator": denominator, "units": units}
    if assumed:
        value["assumed"] = True
    return value


def tapped(first_unit=None, last_unit=None):
    """The layout's recording, tapped: a pickup, bars 1 and 2 with first and
    second endings and a repeat, then bar 3 in 6/8 tapped in two, a beat
    every second from 0 s."""
    marks = {
        0: {"number": 0},
        1: {},
        4: {"label": "2a"},
        7: {"number": 1},
        10: {"label": "2b"},
        13: {},
    }
    units = {0: first_unit or unit(4, "1"), 13: last_unit}
    return [
        (B[n], beat(float(n), measure=marks.get(n), beat_unit=units.get(n)))
        for n in range(15)
    ]


def table(rows):
    """What WP9 computes for each row, as the layout's table prints it."""
    return [
        (r.count, r.number, r.label, r.pass_, r.beats, r.start, r.end, r.time_signature)
        for r in rows
    ]


def where(positions):
    return (
        positions.bar,
        positions.bar_label,
        positions.pass_,
        positions.bar_count,
        positions.beat,
        positions.downbeat,
    )


# The layout's tapped recording


def test_the_layouts_tapped_example_is_a_file_the_writer_writes():
    data = file_of(tapped(last_unit=unit(8, "3")))
    assert tla.canonical_bytes(tla.loads(data)) == data


def test_the_layouts_tapped_example_gives_the_layouts_table(tmp_path):
    doc = read(file_of(tapped(last_unit=unit(8, "3"))), tmp_path)

    found = find_time_map(doc)

    assert (found.timeline_id, found.guessed, found.reason) == (BEATS, True, None)
    assert table(found.time_map.measure_rows()) == [
        (1, 0, "0", 1, 1, 0.0, 1.0, "1/4"),
        (2, 1, "1", 1, 3, 1.0, 4.0, "3/4"),
        (3, 2, "2a", 1, 3, 4.0, 7.0, "3/4"),
        (4, 1, "1", 2, 3, 7.0, 10.0, "3/4"),
        (5, 2, "2b", 2, 3, 10.0, 13.0, "3/4"),
        (6, 3, "3", 1, 2, 13.0, 15.0, "6/8"),
    ]
    assert measure_rows(doc, BEATS) == found.time_map.measure_rows()
    assert not any(r.assumed for r in found.time_map.measure_rows())


def test_the_layouts_tapped_example_gives_the_positions_of_us1(tmp_path):
    time_map = time_map_for(
        read(file_of(tapped(last_unit=unit(8, "3"))), tmp_path), BEATS
    )

    # Scenario 2: the pickup, the second time through bar 1, the second ending.
    assert where(time_map.positions(0.0, 0.0)) == (0, "0", 1, 1, 1.0, True)
    assert where(time_map.positions(7.0, 7.0)) == (1, "1", 2, 4, 1.0, True)
    assert where(time_map.positions(10.0, 10.0)) == (2, "2b", 2, 5, 1.0, True)
    # Scenario 3: from the downbeat of bar 1 to the downbeat of bar 3, the end
    # excluded: bars 1, 2a, 1 and 2b.
    assert time_map.positions(1.0, 13.0).end_bar == 2
    assert time_map.length(1.0, 13.0, "bar") == 4.0
    # Scenario 4: a point on the downbeat of bar 3.
    on_bar_3 = time_map.positions(13.0, 13.0)
    assert (on_bar_3.bar, on_bar_3.end_bar, on_bar_3.downbeat) == (3, 3, True)
    # Scenario 5: halfway between beats 2 and 3 of bar 1; 0.05 s before 2a's
    # downbeat, and 0.15 s before it.
    assert where(time_map.positions(2.5, 2.5)) == (1, "1", 1, 2, 2.5, False)
    assert where(time_map.positions(3.95, 3.95)) == (2, "2a", 1, 3, 1.0, True)
    before = time_map.positions(3.85, 3.85)
    assert (before.bar, before.bar_count) == (1, 2)
    assert before.beat == pytest.approx(3.85)
    # Scenario 6: before the first beat by more than 0.1 s, on the closing
    # barline (one beat's length after the last beat), past it; and a span
    # that ends past it.
    assert time_map.positions(-0.15, -0.15) is None
    assert time_map.end == 15.0
    assert time_map.positions(15.0, 15.0) is None
    assert time_map.positions(15.5, 15.5) is None
    assert time_map.positions(13.0, 15.5).end_bar is None


def test_the_layouts_tapped_example_gives_quarter_notes_from_its_units(tmp_path):
    time_map = time_map_for(
        read(file_of(tapped(last_unit=unit(8, "3"))), tmp_path), BEATS
    )

    # US3 scenario 1: the pickup's beat, bar 1's downbeat, 2a's.
    assert [time_map.qstamp(t) for t in (0.0, 1.0, 4.0)] == [0, 1, 4]
    # US2 scenario 2: bar 3 in 6/8, counted in two, each beat 1.5 quarters.
    bar_3 = time_map.measure_rows()[-1]
    assert (bar_3.time_signature, bar_3.assumed, bar_3.quarters) == ("6/8", False, 3)
    assert [time_map.positions(t, t).beat for t in (13.0, 14.0)] == [1.0, 2.0]
    assert time_map.qstamp(14.0) - time_map.qstamp(13.0) == 1.5


def test_a_unit_set_on_the_6_8_bar_changes_the_quarters_after_it_and_the_file_by_it(
    tmp_path,
):
    # US3 scenario 2, on a file whose only unit is the default the migration
    # gives the first beat: bar 3 reads 2/4, assumed, until it is set.
    original = file_of(tapped(first_unit=unit(4, "1", assumed=True)))
    path = tmp_path / "piece.tla"
    path.write_bytes(original)
    doc = tla.read(path)
    before = time_map_for(doc, BEATS)
    unset = before.measure_rows()[-1]
    assert (unset.time_signature, unset.assumed, before.qstamp(14.0)) == (
        "2/4",
        True,
        14,
    )

    plan = plan_time_signatures(
        doc, BEATS, [(BarRef(3), TimeSignature.parse("6/8"))], source="edit"
    )
    apply_plan(doc, plan)
    after = time_map_for(doc, BEATS)
    tla.write(path, doc, expect=doc.fingerprint)

    bar_3 = after.measure_rows()[-1]
    assert (bar_3.time_signature, bar_3.assumed) == ("6/8", False)
    assert after.qstamp(14.0) == 14.5
    # The bars before keep theirs, and the map ends where it did.
    assert after.measure_rows()[:-1] == before.measure_rows()[:-1]
    assert after.end == before.end == 15.0
    # The file changes by that beat unit alone.
    diff = difflib.unified_diff(
        original.decode().splitlines(), path.read_text("utf-8").splitlines(), n=0
    )
    changed = [line for line in list(diff)[2:] if not line.startswith("@@")]
    assert changed == [
        '-          "measure": {}',
        '+          "measure": {},',
        '+          "beat_unit": {',
        '+            "denominator": 8,',
        '+            "units": "3"',
        "+          }",
    ]


# The layout's folded score, a cadenza, and two songs


def folded():
    """The layout's score, folded, in quarter notes: each written bar once, and
    `next` for the playing order; bar 3 in 6/8."""
    marks = {
        0: {"number": 0},
        1: {"next": [B[4], B[7]]},
        4: {"label": "2a", "next": [B[1]]},
        7: {"number": 2, "label": "2b"},
        10: {},
    }
    units = {0: unit(4, "1"), 10: unit(8, "3")}
    times = [*range(11), 11.5]
    return [
        (B[n], beat(time, measure=marks.get(n), beat_unit=units.get(n)))
        for n, time in enumerate(times)
    ]


def test_the_layouts_folded_score_gives_its_rows_in_written_order(tmp_path):
    data = file_of(folded(), time_unit="quarters")
    assert tla.canonical_bytes(tla.loads(data)) == data
    doc = read(data, tmp_path)

    rows = measure_rows(doc, BEATS)

    assert [(r.number, r.label, r.start, r.time_signature) for r in rows] == [
        (0, "0", 0, "1/4"),
        (1, "1", 1, "3/4"),
        (2, "2a", 4, "3/4"),
        (2, "2b", 7, "3/4"),
        (3, "3", 10, "6/8"),
    ]
    assert all(r.folded for r in rows)
    assert [r.next for r in rows] == [None, (B[4], B[7]), (B[1],), None, None]
    # Walking `next` gives the recording's order.
    assert [r.label for r in played(rows)] == ["0", "1", "2a", "1", "2b", "3"]
    # Positions don't take a folded table yet: it has no time map.
    found = find_time_map(doc)
    assert (found.timeline_id, found.time_map, found.reason) == (BEATS, None, FOLDED)


def played(rows):
    """The rows in playing order: each row's `next`, one per time through it,
    else the row after it."""
    by_id = {row.id: index for index, row in enumerate(rows)}
    visits = {}
    order = []
    index = 0
    while index < len(rows):
        row = rows[index]
        order.append(row)
        visits[row.id] = visits.get(row.id, 0) + 1
        if row.next is None:
            index += 1
        elif visits[row.id] <= len(row.next):
            index = by_id[row.next[visits[row.id] - 1]]
        else:
            index += 1
    return order


def test_a_cadenza_has_its_bars_number_and_no_pass(tmp_path):
    # The layout's cadenza between bars 2 and 3; US1 scenario 9.
    marks = {
        0: {"number": 1},
        3: {},
        6: {"number": 2, "label": "2c", "cadenza": True},
        8: {},
    }
    beats = [
        (
            B[n],
            beat(
                float(n),
                measure=marks.get(n),
                beat_unit=unit(4, "1") if n == 0 else None,
            ),
        )
        for n in range(11)
    ]
    time_map = time_map_for(read(file_of(beats), tmp_path), BEATS)

    rows = time_map.measure_rows()
    assert [(r.number, r.label, r.pass_, r.cadenza) for r in rows] == [
        (1, "1", 1, False),
        (2, "2", 1, False),
        (2, "2c", None, True),
        (3, "3", 1, False),
    ]
    in_it = time_map.positions(6.5, 6.5)
    assert (in_it.bar, in_it.bar_label, in_it.pass_, in_it.cadenza) == (
        2,
        "2c",
        None,
        True,
    )
    assert [r.label for r in time_map.find(2)] == ["2"]
    assert [r.label for r in time_map.find(label="2c")] == ["2c"]


def test_a_second_song_counts_its_passes_again(tmp_path):
    # US1 scenario 10, with the first song ended by a closing tap: bars 1 and
    # 2 from 0 s, then, after a pause, bars 1 and 2 again from 5 s.
    beats = [
        (B[0], beat(0.0, measure={"number": 1}, beat_unit=unit(4, "1"))),
        (B[1], beat(1.0)),
        (B[2], beat(2.0, measure={})),
        (B[3], beat(3.0)),
        (B[4], beat(4.0, closing=True)),
        (B[5], beat(5.0, measure={"number": 1, "restart": True})),
        (B[6], beat(6.0)),
        (B[7], beat(7.0, measure={})),
        (B[8], beat(8.0)),
    ]
    time_map = time_map_for(read(file_of(beats), tmp_path), BEATS)

    rows = time_map.measure_rows()
    assert [(r.count, r.number, r.pass_, r.movement, r.end) for r in rows] == [
        (1, 1, 1, 1, 2.0),
        (2, 2, 1, 1, 4.0),
        (3, 1, 1, 2, 7.0),
        (4, 2, 1, 2, 9.0),
    ]
    second = time_map.positions(5.0, 5.0)
    assert (second.bar, second.pass_, second.movement, second.bar_count) == (1, 1, 2, 3)
    assert time_map.positions(4.5, 4.5) is None  # the pause between the songs


# WP3's example file


@pytest.fixture
def every_kind(tmp_path):
    shutil.copy(EVERY_KIND, tmp_path / EVERY_KIND.name)
    return tla.read(tmp_path / EVERY_KIND.name)


def timeline_named(doc, name):
    return next(tl for tl in doc.timelines.values() if tl.name == name)


def test_the_example_file_s_time_map_is_its_timeline_with_the_role(every_kind):
    found = find_time_map(every_kind)

    assert found.timeline_id == timeline_named(every_kind, "Beats").id
    assert (found.guessed, found.reason, found.warnings) == (False, None, ())


def test_the_example_file_gives_its_table(every_kind):
    # Bar 3 (6/8, its beats 0.75 s apart) is followed by a bar of one beat,
    # 3/8, which lasts its own length at that tempo: the map ends at 16.75,
    # before the media's end, at 17.5.
    rows = find_time_map(every_kind).time_map.measure_rows()

    assert [
        (r.count, r.number, r.label, r.pass_, r.beats, r.start, r.end) for r in rows
    ] == [
        (1, 0, "0", 1, 1, 0.0, 1.0),
        (2, 1, "1", 1, 3, 1.0, 4.0),
        (3, 2, "2a", 1, 3, 4.0, 7.0),
        (4, 1, "1", 2, 3, 7.0, 10.0),
        (5, 2, "2b", 2, 3, 10.0, 13.0),
        (6, 2, "2c", None, 1, 13.0, 14.5),
        (7, 3, "3", 1, 2, 14.5, 16.0),
        (8, 4, "4", 1, 1, 16.0, 16.75),
    ]
    assert [(r.time_signature, r.assumed) for r in rows] == [
        ("1/4", False),
        *[("3/4", False)] * 4,
        ("1/4", False),
        ("6/8", False),
        ("3/8", False),
    ]
    assert [r.qstamp for r in rows] == [0, 1, 4, 7, 10, 13, 14, 17]
    # What the marks hold besides the numbers: 2a always shows its number, and
    # the repeat of bar 1 was edited and tagged.
    assert [r.force_display for r in rows] == [False, False, True] + [False] * 5
    assert [r.source for r in rows] == ["tapped"] * 3 + ["edited"] + ["tapped"] * 4
    assert rows[3].metadata == {"tags": ("repeat",)}


def test_the_example_file_gives_positions_in_its_cadenza_and_its_6_8_bar(
    every_kind,
):
    time_map = find_time_map(every_kind).time_map

    in_the_cadenza = time_map.positions(13.5, 13.5)
    assert (
        in_the_cadenza.bar,
        in_the_cadenza.bar_label,
        in_the_cadenza.pass_,
        in_the_cadenza.cadenza,
        in_the_cadenza.bar_count,
    ) == (2, "2c", None, True, 6)
    assert in_the_cadenza.beat == pytest.approx(1 + 1 / 3)
    assert where(time_map.positions(15.625, 15.625)) == (3, "3", 1, 7, 2.5, False)
    assert time_map.qstamp(15.25) - time_map.qstamp(14.5) == 1.5
    assert time_map.positions(16.75, 16.75) is None


def test_the_example_file_s_score_table_is_folded_and_has_two_movements(every_kind):
    score = timeline_named(every_kind, "Bars of the score")

    rows = measure_rows(every_kind, score.id)

    assert [(r.number, r.label, r.movement, r.start) for r in rows] == [
        (0, "0", 1, 0.0),
        (1, "1", 1, 1.0),
        (2, "2a", 1, 4.0),
        (2, "2b", 1, 10.0),
        (3, "3", 1, 14.5),
        (1, "1", 2, 16.0),
    ]
    assert all(r.folded for r in rows)
    assert [r.label for r in played(rows)] == ["0", "1", "2a", "1", "2b", "3", "1"]
    assert time_map_for(every_kind, score.id) is None


# Old files, read through the migration


def old_measures(path):
    """Each measure an old file's beat timeline describes, from its own lists:
    (number, beats, first beat's time), and its beats' times. Where the
    lists are empty, TiLiA makes the measures from a one-entry beat pattern."""
    content = json.loads(path.read_text("utf-8"))
    (timeline,) = [
        tl for tl in content["timelines"].values() if "BEAT" in tl["kind"].upper()
    ]
    times = sorted(beat["time"] for beat in timeline["components"].values())
    counts = list(timeline["beats_in_measure"])
    numbers = list(timeline["measure_numbers"])
    if not counts:
        (taps,) = timeline["beat_pattern"]
        counts = [taps] * (len(times) // taps)
        numbers = list(range(1, len(counts) + 1))
    assert sum(counts) == len(times), "these files' lists fit their beats"
    firsts = [sum(counts[:i]) for i in range(len(counts))]
    measures = [
        (number, count, times[first])
        for number, count, first in zip(numbers, counts, firsts, strict=True)
    ]
    return measures, times


@pytest.mark.parametrize("path", OLD_FILES, ids=lambda path: path.name)
def test_an_old_file_s_time_map_gives_the_measures_its_lists_describe(path, tmp_path):
    shutil.copy(path, tmp_path / path.name)
    doc = tla.read(tmp_path / path.name)
    measures, times = old_measures(path)

    found = find_time_map(doc)
    rows = found.time_map.measure_rows()

    # No timeline has the role time_map in an old file.
    assert found.guessed
    assert [(r.number, r.label, r.beats, r.start) for r in rows] == [
        (number, str(number), count, start) for number, count, start in measures
    ]
    # The migration's default unit, assumed: a quarter note per beat.
    assert [(r.time_signature, r.assumed) for r in rows] == [
        (f"{count}/4", True) for _, count, _ in measures
    ]
    assert [r.end for r in rows[:-1]] == [r.start for r in rows[1:]]
    last_gap = times[-1] - times[-2]
    ends = [times[-1] + last_gap]
    if doc.media_length is not None:
        ends.append(doc.media_length)
    assert rows[-1].end == pytest.approx(min(ends))
    # Every beat is where its measure and its place in it say.
    expected = [
        (number, float(beat + 1), beat == 0)
        for number, count, _ in measures
        for beat in range(count)
    ]
    found_at = [found.time_map.positions(t, t) for t in times]
    assert [(p.bar, p.beat, p.downbeat) for p in found_at] == expected
