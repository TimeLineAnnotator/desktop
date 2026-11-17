"""Nothing the time map computes is stored, and nothing it computes goes stale
(SC-007, FR-004).

A file read, measured in every way the time map measures, and written gives
the bytes a file read and written gives; the document is as it was read. After
edits to beats, marks and units, a time map built again from the document
gives what one built from the file it would be written as gives. Time maps
compare by identity, so their rows and positions are compared.

To check a corpus too, set `TILIA_TIMEMAP_CORPUS` to its folder: its files are
read where they are, and never written.
"""

import collections
import copy
import math
import os
import random
import shutil
from pathlib import Path

import pytest

import docs
from tilia_core import tla
from tilia_core.importers import harmony_available
from tilia_core.timemap import (
    BarRef,
    TimeSignature,
    apply_plan,
    find_time_map,
    measure_rows,
    meters_of,
    plan_time_signatures,
    rows_of,
    table_problem,
    time_map_for,
)
from tilia_core.tla.model import beat_order

TLA = Path(__file__).resolve().parent.parent / "tla"
GOLDEN = sorted((TLA / "golden").glob("*.tla"))
OLD = sorted((TLA / "old").glob("*.tla"))
EVERY_KIND = TLA / "golden" / "every-kind.tla"
S4 = TLA / "old" / "0.6.0-s4-10.tla"
CORPUS = "TILIA_TIMEMAP_CORPUS"

# Where components lie, by the keys that hold a time.
TIME_KEYS = ("time", "start", "end", "pre_start", "post_end")
TIME_SIGNATURES = ("2/4", "3/4", "4/4", "6/8", "3/8", "2+3/8", "3+3+2/8")
UNREADABLE = {"denominator": 200, "units": "x"}  # a unit the reader can't read


def is_time(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def component_times(doc):
    return sorted(
        {
            value
            for timeline in doc.timelines.values()
            for component in timeline.components.values()
            for key in TIME_KEYS
            if is_time(value := component.attrs.get(key))
        }
    )


def measure_everything(doc):
    """Asks the time map for every value it computes from `doc`, as its callers
    ask: the index, the query engine, the importers, the bulk edits and TiLiA."""
    find_time_map(doc)
    times = component_times(doc)
    for timeline in doc.timelines.values():
        if timeline.kind != "beat":
            continue
        table_problem(timeline)
        meters_of(rows_of(timeline))
        rows = measure_rows(doc, timeline.id)
        for after in ("restore", "carry"):
            for text in ("6/8", "2+2+3/8"):
                settings = [(row.id, TimeSignature.parse(text)) for row in rows]
                plan_time_signatures(
                    doc, timeline.id, settings, source="score", after=after
                )
        time_map = time_map_for(doc, timeline.id)
        if time_map is None:
            continue
        time_map.measures()
        middle = (time_map.start + time_map.end) / 2
        for t in [*times, time_map.start - 1, middle, time_map.end + 1]:
            time_map.positions(t, t)
            time_map.positions(t, t + 1.5)
            for unit in ("bar", "beat"):
                time_map.position(t, unit)
                time_map.length(t, t + 1.5, unit)
                time_map.unit_seconds(t, unit)
            qstamp = time_map.qstamp(t)
            if qstamp is not None:
                time_map.time_at_qstamp(qstamp)
            time_map.quarters(t, t + 1.5)
            time_map.assumed_between(t, t + 1.5)
        for row in time_map.measure_rows():
            time_map.find(row.number)
            time_map.find(label=row.label, pass_=row.pass_, movement=row.movement)
            time_map.times_of(row.number, 0.5)
            time_map.times_of(row.number, 1.0, segment_end=True)


def place(path, folder):
    folder.mkdir()
    return Path(shutil.copy(path, folder / path.name))


def written(path, folder, *, measured):
    """The bytes of `path` copied to `folder`, read, `measured` in every way
    the time map measures (the document is then as it was read), and written
    with `tla.write`. Without the `harmony` extra, the writer won't write
    chords and keys, which it can't check: for a file that has them, the
    bytes it would write, `canonical_bytes`."""
    copied = place(path, folder)
    doc = tla.read(copied)
    if measured:
        as_read = copy.deepcopy(doc)
        measure_everything(doc)
        assert doc == as_read
    if not harmony_available() and b'"HARMONY' in path.read_bytes().upper():
        return tla.canonical_bytes(doc)
    tla.write(copied, doc, expect=doc.fingerprint)
    return copied.read_bytes()


def assert_measuring_writes_nothing(path, tmp_path):
    """`path` read, measured and written gives the bytes it gives read and
    written, and the document is as it was read; returns them."""
    data = written(path, tmp_path / "measured", measured=True)
    assert data == written(path, tmp_path / "read", measured=False)
    return data


@pytest.mark.parametrize("path", GOLDEN, ids=lambda path: path.name)
def test_a_current_file_read_measured_and_written_keeps_its_bytes(path, tmp_path):
    assert assert_measuring_writes_nothing(path, tmp_path) == path.read_bytes()


@pytest.mark.parametrize("path", OLD, ids=lambda path: path.name)
def test_an_old_file_read_measured_and_written_is_converted_as_without(path, tmp_path):
    assert_measuring_writes_nothing(path, tmp_path)


def a_closing_tap_read_as_a_beat():
    """Bars 1 and 2, with a tap marked closing inside bar 1, which the time
    map reads as a beat, with a warning."""
    return docs.document(
        docs.beat_timeline(
            [
                {"time": 1.0, "measure": {"number": 1}},
                {"time": 2.0, "closing": True},
                {"time": 3.0, "measure": {}},
                {"time": 4.0},
                {"time": 5.0, "closing": True},
            ]
        )
    )


# Files the core writes that hold what the real ones don't: no beat unit at
# all, closing taps, a second movement, and a time map that warns.
WRITTEN = {
    "no beat unit": lambda: docs.document(docs.pickup_piece()),
    "a closing tap": lambda: docs.document(docs.closed_piece(), media_length=8.0),
    "two movements": lambda: docs.document(docs.two_movements(closed=True)),
    "a closing tap read as a beat": a_closing_tap_read_as_a_beat,
}


@pytest.mark.parametrize("name", WRITTEN)
def test_a_file_the_core_wrote_read_measured_and_written_keeps_its_bytes(
    name, tmp_path
):
    path = tmp_path / "piece.tla"
    tla.write(path, WRITTEN[name](), expect=tla.ABSENT)
    found = find_time_map(tla.read(path))
    assert found.time_map is not None
    assert bool(found.warnings) == (name == "a closing tap read as a beat")

    assert assert_measuring_writes_nothing(path, tmp_path) == path.read_bytes()


def test_a_corpus_read_and_measured_is_written_as_it_was_read():
    folder = os.environ.get(CORPUS)
    if not folder:
        pytest.skip(
            f"no corpus: set {CORPUS} to a folder of .tla files to check them"
            " (read where they are, never written)"
        )
    if not Path(folder).is_dir():
        pytest.skip(f"{CORPUS} is {folder!r}, which isn't a folder here")
    paths = sorted(Path(folder).rglob("*.tla"))
    if not paths:
        pytest.skip(f"{CORPUS} is {folder!r}, which holds no .tla file")
    changed, unreadable = [], []
    for path in paths:
        try:
            doc = tla.read(path)
        except (tla.UnreadableFile, OSError):
            unreadable.append(path)
            continue
        as_read, data = copy.deepcopy(doc), tla.canonical_bytes(doc)
        measure_everything(doc)
        if doc != as_read or tla.canonical_bytes(doc) != data:
            changed.append(path)
    print(f"\n{CORPUS}: {len(paths)} files, {len(unreadable)} unreadable")
    assert changed == []
    if len(unreadable) == len(paths):
        pytest.skip(f"{CORPUS} is {folder!r}, whose files the core can't read")


# Nothing goes stale


def assert_as_from_scratch(doc, times):
    """Every beat timeline of `doc` gives, as it now is, what it gives read
    from the file it would be written as: its table, its rows, the time map
    chosen, and that map's rows and positions. Returns the time map found."""
    fresh = tla.loads(tla.canonical_bytes(doc))
    for timeline_id, timeline in doc.timelines.items():
        if timeline.kind == "beat":
            assert timeline.measures == fresh.timelines[timeline_id].measures
            assert measure_rows(doc, timeline_id) == measure_rows(fresh, timeline_id)
    built, scratch = find_time_map(doc), find_time_map(fresh)
    assert (built.timeline_id, built.guessed, built.reason, built.warnings) == (
        scratch.timeline_id,
        scratch.guessed,
        scratch.reason,
        scratch.warnings,
    )
    assert (built.time_map is None) == (scratch.time_map is None)
    if built.time_map is not None:
        assert built.time_map is not scratch.time_map
        assert values(built.time_map, times) == values(scratch.time_map, times)
    return built


def values(time_map, times):
    """What a time map gives: its rows, its ends, and where `times` lie."""
    return (
        time_map.measure_rows(),
        (time_map.start, time_map.end),
        [time_map.positions(t, t + 0.75) for t in times],
        [time_map.qstamp(t) for t in times],
        [(time_map.position(t, "bar"), time_map.position(t, "beat")) for t in times],
    )


def beats_of(timeline):
    return [c for c in timeline.components.values() if c.kind == "beat"]


def downbeats(timeline):
    return [c for c in beats_of(timeline) if isinstance(c.attrs.get("measure"), dict)]


def a_time(rng, timeline):
    times = [
        c.attrs["time"] for c in beats_of(timeline) if is_time(c.attrs.get("time"))
    ]
    low, high = (min(times), max(times)) if times else (0.0, 10.0)
    return round(max(0.0, rng.uniform(low - 0.5, high + 1.5)), 3)


def set_mark(rng, timeline, key, value):
    marked = downbeats(timeline)
    if not marked:
        return
    component = rng.choice(marked)
    mark = dict(component.attrs["measure"])
    if value is None:
        mark.pop(key, None)
    else:
        mark[key] = value
    component.attrs["measure"] = mark


def move(rng, timeline):
    component = rng.choice(beats_of(timeline))
    component.attrs["time"] = round(
        max(0.0, component.attrs["time"] + rng.uniform(-1.5, 1.5)), 3
    )


def add(rng, timeline):
    attrs = {"time": a_time(rng, timeline)}
    if rng.random() < 0.3:
        attrs["measure"] = {}
    component = tla.Component(id=tla.new_id(), kind="beat", attrs=attrs)
    timeline.components[component.id] = component


def delete(rng, timeline):
    beats = beats_of(timeline)
    if len(beats) > 4:
        del timeline.components[rng.choice(beats).id]


def mark(rng, timeline):
    unmarked = [c for c in beats_of(timeline) if "measure" not in c.attrs]
    if unmarked:
        rng.choice(unmarked).attrs["measure"] = {}


def unmark(rng, timeline):
    marked = downbeats(timeline)
    if len(marked) > 1:
        del rng.choice(marked).attrs["measure"]


def number(rng, timeline):
    set_mark(rng, timeline, "number", rng.choice([None, *range(13)]))


def label(rng, timeline):
    set_mark(rng, timeline, "label", rng.choice([None, "1a", "2b", "16a", "x"]))


def flag(rng, timeline):
    key = rng.choice(["cadenza", "restart", "force_display"])
    set_mark(rng, timeline, key, rng.choice([None, True]))


def mark_source(rng, timeline):
    set_mark(rng, timeline, "source", rng.choice([None, "score", "edited", "import"]))


def mark_metadata(rng, timeline):
    set_mark(rng, timeline, "metadata", rng.choice([None, {"tags": ["check"]}]))


def beat_unit(rng, timeline):
    value = rng.choice(
        [
            {"denominator": 4, "units": "1"},
            {"denominator": 4, "units": "1", "assumed": True},
            {"denominator": 8, "units": "3"},
            {"denominator": 8, "units": "2+3"},
            {"denominator": 2, "units": "1"},
            {"denominator": 4, "units": "1/2"},
            UNREADABLE,
        ]
    )
    rng.choice(beats_of(timeline)).attrs["beat_unit"] = dict(value)


def no_beat_unit(rng, timeline):
    with_one = [c for c in beats_of(timeline) if "beat_unit" in c.attrs]
    if with_one:
        del rng.choice(with_one).attrs["beat_unit"]


def closing(rng, timeline):
    """Marks a beat closing, or a closing tap a beat again. The reader gives
    every beat `closing`, false where it isn't one."""
    component = rng.choice(beats_of(timeline))
    if component.attrs.get("closing"):
        del component.attrs["closing"]
    else:
        component.attrs["closing"] = True


def collide(rng, timeline):
    """Moves a beat to another's time: the table has a problem, and the
    timeline no time map, until `separate` moves one of them away."""
    beats = beats_of(timeline)
    if len(beats) > 1:
        moved, onto = rng.sample(beats, 2)
        moved.attrs["time"] = onto.attrs["time"]


def separate(rng, timeline):
    """Moves each beat that shares its time with another a little later."""
    times = set()
    for component in beats_of(timeline):
        time = component.attrs["time"]
        if time in times:
            component.attrs["time"] = round(time + rng.uniform(0.05, 0.5), 3)
        times.add(component.attrs["time"])


def timeline_source(rng, timeline):
    timeline.attrs["measure_source"] = rng.choice(["tapped", "score", "unknown"])


# Each edits the timeline through WP3's model, as an editor does.
EDITS = [
    move,
    add,
    delete,
    mark,
    unmark,
    number,
    label,
    flag,
    mark_source,
    mark_metadata,
    beat_unit,
    no_beat_unit,
    closing,
    collide,
    timeline_source,
]


def keep_the_first_beat_marked(timeline):
    """Marks the first beat that isn't a closing tap, as TiLiA marks its first
    beat (TimeLineAnnotator/project-management#544): the reader refuses a
    file whose first beat has no mark."""
    beats = {c.id: c.attrs for c in beats_of(timeline)}
    order = [key for key in beat_order(beats) if not beats[key].get("closing")]
    if order and not isinstance(beats[order[0]].get("measure"), dict):
        beats[order[0]]["measure"] = {}


def a_time_signature(rng):
    return TimeSignature.parse(rng.choice(TIME_SIGNATURES))


def a_plan(rng, doc, timeline):
    """Plans time signatures for a few of the timeline's bars, at times for a
    bar it doesn't have too, or over a unit the reader can't read; applies the
    plan, and returns it."""
    rows = measure_rows(doc, timeline.id)
    if not rows:
        return None
    settings = [
        (
            rng.choice([row.id, BarRef(row.number, pass_=row.pass_)]),
            a_time_signature(rng),
        )
        for row in rng.sample(rows, min(len(rows), rng.randint(1, 3)))
    ]
    after = rng.choice(["restore", "carry"])
    if rng.random() < 0.3:
        settings.append((BarRef(999), a_time_signature(rng)))
    if len(rows) > 1 and rng.random() < 0.3:
        # A bar after one set stores a unit the reader can't read: where the
        # bar would read otherwise, "restore" would write its old unit back
        # there, so the run is left out of the plan.
        index = rng.randrange(1, len(rows))
        timeline.components[rows[index].id].attrs["beat_unit"] = dict(UNREADABLE)
        timeline.measures = tla.measure_table(timeline)
        settings.append((rows[index - 1].id, a_time_signature(rng)))
        after = "restore"
    plan = plan_time_signatures(
        doc,
        timeline.id,
        settings,
        source=rng.choice(["score", "import", "edit"]),
        after=after,
    )
    apply_plan(doc, plan)
    return plan


def probes(rng, doc, timeline):
    """Times to look up: each beat, near it, and anywhere around them."""
    beats = [
        c.attrs["time"] for c in beats_of(timeline) if is_time(c.attrs.get("time"))
    ]
    near = [t + rng.choice([-0.15, -0.05, 0.05, 0.15]) for t in beats]
    anywhere = [a_time(rng, timeline) for _ in range(20)]
    return sorted([*beats, *near, *anywhere, -1.0])


def edit_at_random(seed, path, steps, plans):
    """Edits the time map's timeline of the file at `path` `steps` times, a
    share `plans` of them by applying a plan, and checks each step. Returns
    what the steps reached."""
    rng = random.Random(seed)
    doc = tla.read(path)
    timeline = doc.timelines[find_time_map(doc).timeline_id]
    reached = collections.Counter()
    for _ in range(steps):
        times = probes(rng, doc, timeline)
        before = find_time_map(doc).time_map
        kept = None if before is None else values(before, times)

        if rng.random() < plans:
            plan = a_plan(rng, doc, timeline)  # apply_plan builds the table itself
            if plan is not None:
                reached["a plan's writes"] += bool(plan.changes)
                reached["a bar the table doesn't have"] += bool(plan.unmatched)
                reached["a run left out"] += bool(plan.unreadable)
        else:
            # Beats that `collide` put at one time are moved apart half the
            # time, so that the timeline has no time map for a step or two,
            # not for the rest of the walk.
            if rng.random() < 0.5:
                separate(rng, timeline)
            rng.choice(EDITS)(rng, timeline)
            keep_the_first_beat_marked(timeline)
            timeline.measures = tla.measure_table(timeline)

        found = assert_as_from_scratch(doc, times)
        reached["no time map" if found.time_map is None else "a time map"] += 1
        reached["warnings"] += bool(found.warnings)
        reached["a closing tap"] += any(
            c.attrs.get("closing") for c in beats_of(timeline)
        )
        # A map built before the edit doesn't follow it.
        if before is not None:
            assert values(before, times) == kept
    return reached


@pytest.mark.parametrize("seed", range(8))
def test_after_random_edits_of_the_example_file_its_time_map_is_one_built_from_scratch(
    seed,
):
    edit_at_random(seed, EVERY_KIND, steps=20, plans=0.2)


@pytest.mark.parametrize("seed", range(2))
def test_after_random_edits_of_an_s4_file_its_time_map_is_one_built_from_scratch(
    seed,
):
    edit_at_random(100 + seed, S4, steps=12, plans=0.5)


def test_the_random_edits_reach_every_state_they_compare():
    # Fewer seeds than the tests above, so that this stays quick: no time map,
    # warnings, closing taps, and plans that write, leave a run out or report
    # a bar.
    reached = collections.Counter()
    for seed in range(3):
        reached += edit_at_random(seed, EVERY_KIND, steps=20, plans=0.2)
    reached += edit_at_random(100, S4, steps=12, plans=0.5)

    assert {state for state, count in reached.items() if count} == {
        "a time map",
        "no time map",
        "warnings",
        "a closing tap",
        "a plan's writes",
        "a bar the table doesn't have",
        "a run left out",
    }


def test_the_closing_edit_marks_a_beat_closing_and_back():
    doc = tla.read(EVERY_KIND)
    timeline = doc.timelines[find_time_map(doc).timeline_id]

    closing(random.Random(0), timeline)
    marked = [c.id for c in beats_of(timeline) if c.attrs.get("closing")]
    closing(random.Random(0), timeline)  # the same beat

    assert len(marked) == 1
    assert not any(c.attrs.get("closing") for c in beats_of(timeline))


def test_the_collide_edit_leaves_the_timeline_without_a_time_map():
    doc = tla.read(EVERY_KIND)
    timeline = doc.timelines[find_time_map(doc).timeline_id]

    collide(random.Random(0), timeline)
    timeline.measures = tla.measure_table(timeline)

    found = find_time_map(doc)
    assert found.timeline_id == timeline.id
    assert found.time_map is None and found.reason


def test_a_plan_applied_leaves_the_table_the_file_it_writes_reads(tmp_path):
    # Bar 1, both times through, set to 6/8: two eighths a tap, with 3/4
    # written back on 2a and 2b. The units in force are the reader's too.
    doc = tla.read(place(EVERY_KIND, tmp_path / "piece"))
    beats = doc.timelines[find_time_map(doc).timeline_id]

    apply_plan(
        doc,
        plan_time_signatures(
            doc, beats.id, [(BarRef(1), TimeSignature.parse("6/8"))], source="score"
        ),
    )

    rows = beats.measures.rows[:5]
    in_force = [(r.label, r.beat_unit.denominator, r.beat_unit.units) for r in rows]
    assert in_force == [
        ("0", 4, "1"),
        ("1", 8, "2"),
        ("2a", 4, "1"),
        ("1", 8, "2"),
        ("2b", 4, "1"),
    ]
    assert [r.source for r in rows] == ["tapped", "score", "tapped", "score", "tapped"]
    read_back = tla.loads(tla.canonical_bytes(doc))
    assert beats.measures == read_back.timelines[beats.id].measures
