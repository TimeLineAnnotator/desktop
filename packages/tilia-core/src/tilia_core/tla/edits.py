"""The two edits to measure marks that FR-081 gives, kept once for TiLiA's
editor, the bulk edits and `tilia migrate`
(TimeLineAnnotator/project-management#416).

- `delete_beat`: a beat is deleted. A downbeat's mark, the `next`s that name
  it and its beat unit go where contracts/layout.md says, and the measures a
  person's deletion changes get the source "edited"
  (TimeLineAnnotator/project-management#512).
- `mark_edited` and `mark_moved`: a measure a person edits gets the source
  "edited", unless it is "tapped"; moving a downbeat edits two measures.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from tilia_core.tla.model import (
    Component,
    Document,
    MeasureTable,
    Timeline,
    beat_order,
    measure_table,
)


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
    beat that isn't there.

    A downbeat's mark moves to the next beat in time order, with its beat
    unit, and every `next` that named the downbeat names that beat. When the
    next beat has a mark of its own, it keeps it: the deleted mark goes, and
    every `next` still names that beat. A `restart` on the deleted mark moves
    to it, and it then states the number it read, unless it states its own.
    When there is no next beat, or it is a closing tap or has no time, the
    mark goes, and every `next` that named the downbeat drops it, a list
    left empty going with it. The beat unit is dropped when the next beat
    states its own, or when the mark goes; no default takes its place, since
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
    if _is_downbeat(deleted):
        changed = _delete_downbeat(timeline, beats, beat_id, table)
    else:
        del timeline.components[beat_id]
        changed = [row.id for row in table.rows if beat_id in row.beats]
    if by_person:
        for downbeat_id in changed:
            _mark_source(timeline, downbeat_id, table.source)
    _refresh(timeline)


def _delete_downbeat(
    timeline: Timeline,
    beats: dict[str, Component],
    beat_id: str,
    table: MeasureTable,
) -> list[str]:
    """Delete the downbeat `beat_id`, as `delete_beat` says, and give the
    downbeats of the measures it changed: the one before, and the one it
    started if that remains."""
    order = beat_order({k: c.attrs for k, c in beats.items()})
    later = order[order.index(beat_id) + 1 :]
    # A closing tap and a beat without a time are in no measure.
    in_measures = {key for row in table.rows for key in row.beats}
    target_id = later[0] if later and later[0] in in_measures else None
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
    if isinstance(unit, dict) and target.get("beat_unit") is None:
        target["beat_unit"] = unit
    _follow_next(timeline, beat_id, target_id)
    return changed


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
    for downbeat_id in chosen:
        _mark_source(timeline, downbeat_id, source)
    _refresh(timeline)


def mark_moved(doc: Document, timeline_id: str, downbeat_id: str) -> None:
    """A downbeat was moved: edit the measure it starts and the one before."""
    timeline = _beat_timeline(doc, timeline_id)
    _downbeats(timeline, [downbeat_id])
    before = _measure_before(_table(timeline), downbeat_id)
    mark_edited(doc, timeline_id, [*before, downbeat_id])
