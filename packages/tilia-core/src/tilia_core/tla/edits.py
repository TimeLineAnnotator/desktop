"""The two edits to measure marks that FR-081 gives, kept once for TiLiA's
editor, the bulk edits and `tilia migrate`
(TimeLineAnnotator/project-management#416).

- `delete_beat`: a beat is deleted. A downbeat's mark, the `next`s that name
  it and the beat units go where contracts/layout.md says, and the measures a
  person's deletion changes get the source "edited"
  (TimeLineAnnotator/project-management#512 and #528).
- `mark_edited` and `mark_moved`: a measure a person edits gets the source
  "edited", unless it is "tapped"; moving a downbeat edits two measures.

What they change on a beat doesn't make a problem the file was read with new
for `write`: it stays old, and so does one that moves with a mark
(TimeLineAnnotator/project-management#528, point 4).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

from tilia_core.tla import problems
from tilia_core.tla.model import (
    Component,
    Document,
    Measure,
    MeasureTable,
    Timeline,
    beat_order,
    measure_table,
)


class CantDeleteDownbeat(ValueError):
    """A downbeat can't be deleted: a closing tap follows it, so its mark
    would go, and the timeline's first beat would have no mark while a
    later measure remains. Nothing changed. Deleting the closing tap first
    lets the mark move on (TimeLineAnnotator/project-management#528,
    point 1)."""

    def __init__(self, message: str, beat_id: str, closing_tap_id: str):
        super().__init__(message)
        self.beat_id = beat_id
        self.closing_tap_id = closing_tap_id


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


def _table(timeline: Timeline) -> MeasureTable:
    table = measure_table(timeline)
    assert table is not None
    return table


def delete_beat(
    doc: Document, timeline_id: str, beat_id: str, *, by_person: bool = True
) -> None:
    """Delete a beat from a beat timeline. Raises `KeyError` for a timeline or
    beat that isn't there, and `CantDeleteDownbeat`, changing nothing, where
    the mark would go and leave the timeline's first beat without one while
    a later measure remains: a closing tap inside the first measure.

    A downbeat's mark moves to the next beat in time order, with its beat
    unit, and every `next` that named the downbeat names that beat. When the
    next beat has a mark of its own, it keeps it: the deleted mark goes, and
    every `next` still names that beat. A `restart` on the deleted mark moves
    to it, and it then states the number it read, unless it states its own.
    When there is no next beat, or it is a closing tap or has no time, the
    mark goes, and every `next` that named the downbeat drops it, a list
    left empty going with it. The beat unit is dropped when the measure it
    would move into states a unit on any of its beats, or when the mark goes.
    An ordinary beat's unit moves to its measure's first beat, or is dropped
    if that beat has one. No default takes the place of a unit dropped, since
    an edit adds none (contracts/layout.md).

    The measures the deletion changes get the source "edited", unless it is
    "tapped" or already "edited": a beat's measure, or a downbeat's measure
    and the one before, or what remains of them. `by_person=False` leaves
    the sources alone, for deletions that aren't a person's edit, such as
    `tilia migrate` dropping beats without a time."""
    timeline = _beat_timeline(doc, timeline_id)
    beats = _beats(timeline)
    deleted = beats[beat_id]
    table = _table(timeline)
    order = beat_order({k: c.attrs for k, c in beats.items()})
    later = order[order.index(beat_id) + 1 :]
    _refuse_an_unmarked_first_beat(timeline, beats, beat_id, order, later)
    before = problems.states_of(
        doc, timeline_id, _may_change(timeline, table, beat_id, later[:1])
    )
    moved: dict[str, str] = {}
    if _is_downbeat(deleted):
        changed = _delete_downbeat(timeline, beats, beat_id, table, later, moved)
    else:
        changed = _delete_beat(timeline, beats, beat_id, table)
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
    leave the timeline's first beat without a mark while another beat has
    one, as the reader refuses: when its mark goes, since a closing tap
    follows it. While a beat has no time, the reader reads such a file, and
    so the deletion goes on."""
    if not _is_downbeat(beats[beat_id]) or not later:
        return
    tap_id = later[0]
    if not beats[tap_id].attrs.get("closing"):
        return
    firsts = [key for key in order if not beats[key].attrs.get("closing")]
    left = firsts[1:]
    if firsts[0] != beat_id or not left:
        return
    if isinstance(beats[left[0]].attrs.get("measure"), dict):
        return
    if any(beats[key].attrs.get("time") is None for key in left):
        return
    if not any(
        isinstance(beats[key].attrs.get("measure"), dict)
        for key in beats
        if key != beat_id
    ):
        return
    name = json.dumps(timeline.name, ensure_ascii=False)
    raise CantDeleteDownbeat(
        f"the first downbeat of the timeline {name} can't be deleted while a"
        " closing tap follows it: its mark would go, and the timeline's first"
        " beat would have no measure mark. Delete the closing tap first.",
        beat_id,
        tap_id,
    )


def _may_change(
    timeline: Timeline, table: MeasureTable, beat_id: str, following: list[str]
) -> list[str]:
    """The beats deleting `beat_id` may change, itself included, so that the
    problems they were read with can be kept old: the next beat, its measure's
    downbeat and the one before, and every downbeat whose `next` names it."""
    ids = {beat_id, *following, *_measure_before(table, beat_id)}
    ids.update(row.id for row in table.rows if beat_id in row.beats)
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
) -> list[str]:
    """Delete the beat `beat_id`, which starts no measure, moving its unit to
    its measure's first beat unless that beat has one, as desktop#621 does;
    and give its measure's downbeat."""
    unit = beats[beat_id].attrs.get("beat_unit")
    del timeline.components[beat_id]
    downbeats = [row.id for row in table.rows if beat_id in row.beats]
    if downbeats and isinstance(unit, dict):
        first = beats[downbeats[0]].attrs
        if first.get("beat_unit") is None:
            first["beat_unit"] = unit
    return downbeats


def _delete_downbeat(
    timeline: Timeline,
    beats: dict[str, Component],
    beat_id: str,
    table: MeasureTable,
    later: list[str],
    moved: dict[str, str],
) -> list[str]:
    """Delete the downbeat `beat_id`, as `delete_beat` says, and give the
    downbeats of the measures it changed: the one before, and the one it
    started if that remains. `moved` gets where its mark went, if it went."""
    # A closing tap and a beat without a time are in no measure.
    measures = {key: row for row in table.rows for key in row.beats}
    target_id = later[0] if later and later[0] in measures else None
    mark = beats[beat_id].attrs["measure"]
    unit = beats[beat_id].attrs.get("beat_unit")
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
    else:
        target["measure"] = mark
        changed.append(target_id)
        moved[beat_id] = target_id
    if isinstance(unit, dict) and not _states_a_unit(
        beats, measures[target_id], beat_id
    ):
        target["beat_unit"] = unit
    _follow_next(timeline, beat_id, target_id)
    return changed


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
