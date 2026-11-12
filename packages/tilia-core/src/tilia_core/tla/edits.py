"""The two edits to measure marks that FR-081 gives, kept once for TiLiA's
editor, the bulk edits and `tilia migrate`
(TimeLineAnnotator/project-management#416).

- `delete_beat`: a beat is deleted. A downbeat's mark, the `next`s that name
  it and the beat units go where contracts/layout.md says, and the measures a
  person's deletion changes get the source "edited"
  (TimeLineAnnotator/project-management#512, #528 and #544).
- `mark_edited` and `mark_moved`: a measure a person edits gets the source
  "edited", unless it is "tapped"; moving a downbeat edits two measures.

What they change on a beat doesn't make a problem the file was read with new
for `write`: it stays old, and so does one that moves with a mark
(TimeLineAnnotator/project-management#528, point 4).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from tilia_core.rules import _media_time
from tilia_core.tla import problems
from tilia_core.tla.check import _which
from tilia_core.tla.errors import printable
from tilia_core.tla.model import (
    Component,
    Document,
    Measure,
    MeasureTable,
    Timeline,
    beat_order,
    measure_table,
    readable_beat_unit,
)


class CantDeleteBeat(ValueError):
    """A beat can't be deleted as the timeline stands; the message says why,
    and what to change first. Nothing changed."""

    def __init__(self, message: str, beat_id: str):
        super().__init__(message)
        self.beat_id = beat_id


class CantDeleteDownbeat(CantDeleteBeat):
    """The timeline's first downbeat can't be deleted: closing taps follow
    it, so its mark would go, and the first beat would have no mark while a
    later beat's mark starts a measure. A mark on a closing tap starts none,
    so it doesn't count. Deleting the closing taps first lets the mark move
    on (TimeLineAnnotator/project-management#528, point 1, and #544, point
    5). `closing_tap_ids` are those taps, `closing_tap_id` the first."""

    def __init__(self, message: str, beat_id: str, closing_tap_ids: list[str]):
        super().__init__(message, beat_id)
        self.closing_tap_ids = tuple(closing_tap_ids)
        self.closing_tap_id = closing_tap_ids[0]


class CantMoveBeatUnit(CantDeleteBeat):
    """A deleted beat's unit would move onto a beat holding a unit the reader
    can't read, which is never replaced: that unit is fixed first
    (TimeLineAnnotator/project-management#544, point 2, as #373 for plans).
    Only a unit the reader can read would move, and only where no other beat
    of the measure states one it can read: else the unit is dropped, as
    #528 point 2 says. `unit_beat_id` is the beat holding it."""

    def __init__(self, message: str, beat_id: str, unit_beat_id: str):
        super().__init__(message, beat_id)
        self.unit_beat_id = unit_beat_id


def _beat_timeline(doc: Document, timeline_id: str) -> Timeline:
    timeline = doc.timelines[timeline_id]
    if timeline.kind != "beat":
        raise ValueError(f"timeline {timeline_id} is not a beat timeline")
    return timeline


def _beats(timeline: Timeline) -> dict[str, Component]:
    return {k: c for k, c in timeline.components.items() if c.kind == "beat"}


def _is_downbeat(component: Component) -> bool:
    attrs = component.attrs
    return isinstance(attrs.get("measure"), dict) and not attrs.get("closing")


def _starts_a_measure(component: Component) -> bool:
    """Whether a beat's mark starts a measure: not on a closing tap, nor on
    a beat without a time, whose measure isn't known."""
    return _is_downbeat(component) and component.attrs.get("time") is not None


def _table(timeline: Timeline) -> MeasureTable:
    table = measure_table(timeline)
    assert table is not None
    return table


def delete_beat(
    doc: Document, timeline_id: str, beat_id: str, *, by_person: bool = True
) -> None:
    """Delete a beat from a beat timeline. Raises `KeyError` for a timeline or
    beat that isn't there, and a `CantDeleteBeat`, changing nothing:
    `CantDeleteDownbeat` where the mark would go and leave the timeline's
    first beat without one while a later beat's mark starts a measure (closing
    taps inside the first measure), and `CantMoveBeatUnit` where the beat's
    unit would move onto a beat holding a unit the reader can't read, rather
    than be dropped.

    A downbeat's mark moves to the next beat in time order, with its beat
    unit, and every `next` that named the downbeat names that beat. When the
    next beat has a mark of its own, it keeps it: the deleted mark goes, and
    every `next` still names that beat. A `restart` on the deleted mark moves
    to it, and it then states the number it read, unless it states its own;
    a problem of that number, which comes from the measure that states it,
    stays old as that measure's does.
    When there is no next beat, or it is a closing tap or has no time, the
    mark goes, and every `next` that named the downbeat drops it, a list
    left empty going with it. Deleting a beat without a time that leaves the
    first beat without a mark while a later beat's mark starts a measure gives
    the first beat an empty mark, as TiLiA marks its first beat.

    The beat unit is dropped when the measure it would move into states a
    unit on any of its beats, or when the mark goes. An ordinary beat's unit
    moves to its measure's first beat, or is dropped if that beat has one. Of
    moving and dropping, whichever keeps every other measure's reading is
    done; if neither does, these rules hold. No default takes the place of a
    unit dropped, since an edit adds none (contracts/layout.md). A closing tap
    read as an ordinary beat (one that ends no measure) is a beat of its
    measure.

    The measures the deletion changes get the source "edited", unless it is
    "tapped" or already "edited": a beat's measure, or a downbeat's measure
    and the one before, or what remains of them, and a measure an empty mark
    starts. `by_person=False` leaves the sources alone, for deletions that
    aren't a person's edit, such as `tilia migrate` dropping beats without a
    time."""
    timeline = _beat_timeline(doc, timeline_id)
    beats = _beats(timeline)
    deleted = beats[beat_id]
    table = _table(timeline)
    timeline.measures = table  # as it stands, for the closing taps
    readings = _readings(timeline)
    order = beat_order({k: c.attrs for k, c in beats.items()})
    later = order[order.index(beat_id) + 1 :]
    _refuse_an_unmarked_first_beat(timeline, beats, beat_id, order, later)
    measure_id = (
        None if _is_downbeat(deleted) else _measure_of(timeline, table, beat_id)
    )
    measures = {key: row for row in table.rows for key in row.beats}
    target_id = later[0] if later and later[0] in measures else None
    destination = target_id if _is_downbeat(deleted) else measure_id
    around = measures[destination].beats if destination in measures else []
    _refuse_an_unreadable_unit(timeline, beats, beat_id, destination, around)
    before = problems.states_of(
        doc,
        timeline_id,
        _may_change(timeline, table, beat_id, [*later[:1], *_first_beat(beats, order)]),
    )
    moved: dict[str, str] = {}
    if _is_downbeat(deleted):
        changed = _delete_downbeat(
            timeline, beats, beat_id, table, target_id, moved, readings
        )
    else:
        changed = _delete_beat(timeline, beats, beat_id, table, measure_id, readings)
    if deleted.attrs.get("time") is None:
        changed.extend(_mark_the_first_beat(beats, order, beat_id))
    if by_person:
        for downbeat_id in changed:
            _mark_source(timeline, downbeat_id, table.source)
    _refresh(timeline)
    problems.keep_old(doc, timeline_id, before, moved)


def _refuse_an_unmarked_first_beat(
    timeline: Timeline,
    beats: dict[str, Component],
    beat_id: str,
    order: list[str],
    later: list[str],
) -> None:
    """Raise `CantDeleteDownbeat` where deleting the downbeat `beat_id` would
    leave the timeline's first beat without a mark while another beat's mark
    starts a measure, as the reader refuses: when its mark goes, since a
    closing tap follows it."""
    if not _is_downbeat(beats[beat_id]) or not later:
        return
    taps = []
    for key in later:
        if not beats[key].attrs.get("closing"):
            break
        taps.append(key)
    if not taps:
        return
    firsts = [key for key in order if not beats[key].attrs.get("closing")]
    left = firsts[1:]
    if firsts[0] != beat_id or not left:
        return
    if isinstance(beats[left[0]].attrs.get("measure"), dict):
        return
    if not any(_starts_a_measure(beats[key]) for key in beats if key != beat_id):
        return
    which = _which({"name": timeline.name})
    what = "the closing taps" if len(taps) > 1 else "the closing tap"
    time = _media_time(beats[left[0]].attrs.get("time"))
    raise CantDeleteDownbeat(
        printable(
            f"the first downbeat of {which} can't be deleted: its measure mark"
            f" can't move onto {what} after it, so the beat at {time} would be"
            " the timeline's first beat, without a measure mark. Delete"
            f" {what} first."
        ),
        beat_id,
        taps,
    )


def _refuse_an_unreadable_unit(
    timeline: Timeline,
    beats: dict[str, Component],
    beat_id: str,
    destination: str | None,
    around: list[str],
) -> None:
    """Raise `CantMoveBeatUnit` where the unit of `beat_id` would move onto
    `destination`, which holds a unit the reader can't read: where the unit is
    one it can read, and no other beat of the measure `destination` is in,
    `around`, states one it can (then the unit is dropped, #528 point 2)."""
    if destination is None:
        return
    if readable_beat_unit(beats[beat_id].attrs.get("beat_unit")) is None:
        return
    held = beats[destination].attrs.get("beat_unit")
    if held is None or readable_beat_unit(held) is not None:
        return
    if any(
        readable_beat_unit(beats[key].attrs.get("beat_unit")) is not None
        for key in around
        if key not in (beat_id, destination)
    ):
        return
    which = _which({"name": timeline.name})
    at = _media_time(beats[beat_id].attrs.get("time"))
    onto = _media_time(beats[destination].attrs.get("time"))
    raise CantMoveBeatUnit(
        printable(
            f"the beat at {at} in {which} can't be deleted: its beat unit would"
            f" move onto the beat at {onto}, whose beat unit TiLiA can't read."
            " Fix that beat unit first."
        ),
        beat_id,
        destination,
    )


def _measure_of(timeline: Timeline, table: MeasureTable, beat_id: str) -> str | None:
    """The downbeat of the measure the beat `beat_id`, which starts none, is a
    beat of: a closing tap read as an ordinary beat, ending no measure, is one
    of its measure's beats, as the time map reads it (WP9's Q16;
    TimeLineAnnotator/project-management#544, point 4). None for a beat in no
    measure."""
    for row in table.rows:
        if beat_id in row.beats:
            return row.id
    if not timeline.components[beat_id].attrs.get("closing"):
        return None
    # Imported here: the time map imports this package.
    from tilia_core.timemap._rows import closing_taps

    for tap in closing_taps(timeline):
        if tap.id == beat_id and not tap.barline:
            return tap.row
    return None


def _first_beat(beats: dict[str, Component], order: list[str]) -> list[str]:
    firsts = [key for key in order if not beats[key].attrs.get("closing")]
    return firsts[:1]


def _mark_the_first_beat(
    beats: dict[str, Component], order: list[str], beat_id: str
) -> list[str]:
    """After a beat without a time was deleted: where every beat now has a
    time, the first has no mark, and a later beat's mark starts a measure, the
    first gets an empty mark, as TiLiA marks its first beat, and starts a
    measure (TimeLineAnnotator/project-management#544, point 1). Gives it."""
    left = [
        key for key in order if key != beat_id and not beats[key].attrs.get("closing")
    ]
    if not left or any(beats[key].attrs.get("time") is None for key in left):
        return []
    first = beats[left[0]].attrs
    if isinstance(first.get("measure"), dict):
        return []
    if not any(_is_downbeat(beats[key]) for key in left):
        return []
    first["measure"] = {}
    return [left[0]]


def _may_change(
    timeline: Timeline, table: MeasureTable, beat_id: str, following: list[str]
) -> list[str]:
    """The beats deleting `beat_id` may change, itself included, so that the
    problems they were read with can be kept old: the next beat and the first,
    its measure's downbeat and the one before, the one whose number it reads,
    and every downbeat whose `next` names it."""
    ids = {beat_id, *following, *_measure_before(table, beat_id)}
    ids.update(_number_source(timeline, table, beat_id))
    measure_id = _measure_of(timeline, table, beat_id)
    if measure_id is not None:
        ids.add(measure_id)
    for key, component in timeline.components.items():
        mark = component.attrs.get("measure")
        following_ids = mark.get("next") if isinstance(mark, dict) else None
        if isinstance(following_ids, list) and beat_id in following_ids:
            ids.add(key)
    return sorted(ids)


def _delete_beat(
    timeline: Timeline,
    beats: dict[str, Component],
    beat_id: str,
    table: MeasureTable,
    measure_id: str | None,
    readings: dict[str, tuple[Any, ...]],
) -> list[str]:
    """Delete the beat `beat_id`, which starts no measure, moving its unit to
    its measure's first beat unless that beat has one, as desktop#621 does, or
    as `_place_unit` chooses; and give its measure's downbeat."""
    unit = beats[beat_id].attrs.get("beat_unit")
    del timeline.components[beat_id]
    if measure_id is None:
        return []
    if isinstance(unit, dict):
        moves = beats[measure_id].attrs.get("beat_unit") is None
        _place_unit(timeline, readings, unit, measure_id, moves, {measure_id})
    return [measure_id]


def _delete_downbeat(
    timeline: Timeline,
    beats: dict[str, Component],
    beat_id: str,
    table: MeasureTable,
    target_id: str | None,
    moved: dict[str, str],
    readings: dict[str, tuple[Any, ...]],
) -> list[str]:
    """Delete the downbeat `beat_id`, as `delete_beat` says, and give the
    downbeats of the measures it changed: the one before, and the one it
    started if that remains. `moved` gets where its mark went, if it went."""
    mark = beats[beat_id].attrs["measure"]
    unit = beats[beat_id].attrs.get("beat_unit")
    sources = _number_source(timeline, table, beat_id)
    measures = {key: row for row in table.rows for key in row.beats}
    del timeline.components[beat_id]
    changed = _measure_before(table, beat_id)
    if target_id is None:
        _drop_next(timeline, beat_id)
        return changed
    target = beats[target_id].attrs
    own = target.get("measure")
    if isinstance(own, dict):
        if mark.get("restart"):
            # The number it read: its own, when it states one.
            numbers = {row.id: row.number for row in table.rows}
            own["restart"] = True
            own["number"] = numbers[target_id]
            for source in sources:
                moved[source] = target_id
        changes = set()  # its measure is another's, which must read as it did
    else:
        target["measure"] = mark
        changed.append(target_id)
        moved[beat_id] = target_id
        changes = {target_id}  # what remains of the downbeat's measure
    if isinstance(unit, dict):
        moves = not _states_a_unit(beats, measures[target_id], beat_id)
        _place_unit(timeline, readings, unit, target_id, moves, changes)
    _follow_next(timeline, beat_id, target_id)
    return changed


def _readings(timeline: Timeline) -> dict[str, tuple[Any, ...]]:
    """What each measure reads, by its downbeat, as the time map reads it, a
    closing tap read as an ordinary beat included (WP9's Q16): its
    denominator and units, and whether they are assumed or conflict."""
    # Imported here: the time map imports this package.
    from tilia_core.timemap._rows import rows_of
    from tilia_core.timemap.meters import meters_of

    rows = rows_of(timeline)
    return {
        row.id: (meter.denominator, meter.units, meter.is_assumed, meter.is_conflicting)
        for row, meter in zip(rows, meters_of(rows), strict=True)
    }


def _place_unit(
    timeline: Timeline,
    readings: dict[str, tuple[Any, ...]],
    unit: dict[str, Any],
    destination: str,
    moves: bool,
    changes: set[str],
) -> None:
    """Put a deleted beat's `unit` on `destination` (when `moves`, the rule's
    choice) or drop it, unless only the other keeps the reading of every
    measure but `changes`, those the deletion changes, from `readings`, as
    they read before it: then the other
    (TimeLineAnnotator/project-management#544, point 3). Moving is open only
    to a destination without a unit, so a unit is never replaced."""
    attrs = timeline.components[destination].attrs
    can_move = attrs.get("beat_unit") is None
    moves = moves and can_move
    before = {key: value for key, value in readings.items() if key not in changes}

    def keeps(move: bool) -> bool:
        if move:
            attrs["beat_unit"] = unit
        try:
            _refresh(timeline)
            now = _readings(timeline)
        finally:
            if move:
                del attrs["beat_unit"]
        return all(now[key] == value for key, value in before.items() if key in now)

    if not keeps(moves) and (can_move or moves) and keeps(not moves):
        moves = not moves
    if moves:
        attrs["beat_unit"] = unit


def _number_source(timeline: Timeline, table: MeasureTable, beat_id: str) -> list[str]:
    """The downbeat whose stated number the measure `beat_id` starts reads its
    number from: the nearest at or before it that states one, as
    `measure_numbers` reads them; none when no measure before it states one."""
    ids = [row.id for row in table.rows]
    if beat_id not in ids:
        return []
    for key in reversed(ids[: ids.index(beat_id) + 1]):
        number = timeline.components[key].attrs["measure"].get("number")
        if isinstance(number, float) and number.is_integer():
            return [key]
        if isinstance(number, int) and not isinstance(number, bool):
            return [key]
    return []


def _states_a_unit(beats: dict[str, Component], row: Measure, deleted: str) -> bool:
    """Whether a beat of the measure `row` other than `deleted` states a unit."""
    return any(
        isinstance(beats[key].attrs.get("beat_unit"), dict)
        for key in row.beats
        if key != deleted
    )


def _measure_before(table: MeasureTable, downbeat_id: str) -> list[str]:
    ids = [row.id for row in table.rows]
    if downbeat_id not in ids:
        return []
    index = ids.index(downbeat_id)
    return ids[max(index - 1, 0) : index]


def _marks(timeline: Timeline) -> Iterator[dict[str, Any]]:
    for component in timeline.components.values():
        mark = component.attrs.get("measure")
        if isinstance(mark, dict):
            yield mark


def _follow_next(timeline: Timeline, old_id: str, new_id: str) -> None:
    for mark in _marks(timeline):
        following = mark.get("next")
        if isinstance(following, list):
            mark["next"] = [new_id if n == old_id else n for n in following]


def _drop_next(timeline: Timeline, old_id: str) -> None:
    """Drop `old_id` from every `next`; a list it empties goes, as the layout
    leaves out a `next` where the next measure follows."""
    for mark in _marks(timeline):
        following = mark.get("next")
        if not isinstance(following, list) or old_id not in following:
            continue
        kept = [n for n in following if n != old_id]
        if kept:
            mark["next"] = kept
        else:
            del mark["next"]


def _refresh(timeline: Timeline) -> None:
    timeline.measures = measure_table(timeline)


def _mark_source(timeline: Timeline, downbeat_id: str, table_source: str) -> None:
    mark = timeline.components[downbeat_id].attrs["measure"]
    if mark.get("source", table_source) in ("tapped", "edited"):
        return
    mark["source"] = "edited"


def _downbeats(timeline: Timeline, ids: Iterable[str]) -> list[str]:
    starts = {row.id for row in _table(timeline).rows}
    chosen = list(ids)
    for downbeat_id in chosen:
        if downbeat_id not in starts:
            raise ValueError(f"{downbeat_id} starts no measure of the timeline")
    return chosen


def mark_edited(doc: Document, timeline_id: str, downbeat_ids: Iterable[str]) -> None:
    """Give the measures that start on `downbeat_ids` the source "edited",
    unless it is "tapped" (a measure whose source already reads "edited" is
    left as it is). Raises `ValueError`, changing nothing, for an id that
    starts no measure."""
    timeline = _beat_timeline(doc, timeline_id)
    chosen = _downbeats(timeline, downbeat_ids)
    source = _table(timeline).source
    before = problems.states_of(doc, timeline_id, chosen)
    for downbeat_id in chosen:
        _mark_source(timeline, downbeat_id, source)
    _refresh(timeline)
    problems.keep_old(doc, timeline_id, before)


def mark_moved(doc: Document, timeline_id: str, downbeat_id: str) -> None:
    """A downbeat was moved: edit the measure it starts and the one before."""
    timeline = _beat_timeline(doc, timeline_id)
    _downbeats(timeline, [downbeat_id])
    before = _measure_before(_table(timeline), downbeat_id)
    mark_edited(doc, timeline_id, [*before, downbeat_id])
