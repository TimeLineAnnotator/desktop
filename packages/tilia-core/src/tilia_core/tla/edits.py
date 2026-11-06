"""The two edits to measure marks that FR-081 gives, kept once for TiLiA's
editor, the bulk edits and `tilia migrate`
(TimeLineAnnotator/project-management#416).

- `delete_beat`: when a downbeat is deleted, its mark moves to the next beat,
  and every `next` that named it names the new downbeat.
- `mark_edited` and `mark_moved`: a measure a person edits gets the source
  "edited", unless it is "tapped"; moving a downbeat edits two measures.

The cases FR-081 does not settle are refused with `CantMoveMark`, and the
document is left as it was, until the package's owner decides them.
"""

from __future__ import annotations

from collections.abc import Iterable

from tilia_core.tla.model import (
    Component,
    Document,
    Timeline,
    beat_order,
    measure_table,
)


class CantMoveMark(ValueError):
    """A deleted downbeat's mark has nowhere it can move to. Nothing changed."""


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


def delete_beat(doc: Document, timeline_id: str, beat_id: str) -> None:
    """Delete a beat from a beat timeline. A downbeat's mark moves to the next
    beat in time order, and every `next` that named the downbeat names that
    beat. Raises `KeyError` for a timeline or beat that isn't there, and
    `CantMoveMark` (changing nothing) when the next beat can't take the mark:
    there is none, it has no time, it is a closing tap, or it has a mark of
    its own; or when the downbeat states a beat unit, which would be lost."""
    timeline = _beat_timeline(doc, timeline_id)
    beats = _beats(timeline)
    deleted = beats[beat_id]
    if not _is_downbeat(deleted):
        del timeline.components[beat_id]
        _refresh(timeline)
        return
    unit = deleted.attrs.get("beat_unit")
    if isinstance(unit, dict) and not unit.get("assumed"):
        raise CantMoveMark("the downbeat states a beat unit, which would be lost")
    order = beat_order({k: c.attrs for k, c in beats.items()})
    later = order[order.index(beat_id) + 1 :]
    if not later:
        raise CantMoveMark("there is no next beat")
    target = beats[later[0]]
    if target.attrs.get("closing"):
        raise CantMoveMark("the next beat is a closing tap")
    if not isinstance(target.attrs.get("time"), (int, float)):
        raise CantMoveMark("the next beat has no time")
    if "measure" in target.attrs and target.attrs["measure"] is not None:
        raise CantMoveMark("the next beat has a mark of its own")
    new_id = later[0]
    target.attrs["measure"] = deleted.attrs["measure"]
    del timeline.components[beat_id]
    for component in timeline.components.values():
        mark = component.attrs.get("measure")
        following = mark.get("next") if isinstance(mark, dict) else None
        if isinstance(following, list):
            mark["next"] = [new_id if n == beat_id else n for n in following]
    _refresh(timeline)


def _refresh(timeline: Timeline) -> None:
    timeline.measures = measure_table(timeline)


def _mark_source(timeline: Timeline, downbeat_id: str, table_source: str) -> None:
    mark = timeline.components[downbeat_id].attrs["measure"]
    if mark.get("source", table_source) in ("tapped", "edited"):
        return
    mark["source"] = "edited"


def _downbeats(timeline: Timeline, ids: Iterable[str]) -> list[str]:
    table = measure_table(timeline)
    assert table is not None
    starts = {row.id for row in table.rows}
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
    table = measure_table(timeline)
    assert table is not None
    for downbeat_id in chosen:
        _mark_source(timeline, downbeat_id, table.source)
    _refresh(timeline)


def mark_moved(doc: Document, timeline_id: str, downbeat_id: str) -> None:
    """A downbeat was moved: edit the measure it starts and the one before."""
    timeline = _beat_timeline(doc, timeline_id)
    _downbeats(timeline, [downbeat_id])
    table = measure_table(timeline)
    assert table is not None
    ids = [row.id for row in table.rows]
    index = ids.index(downbeat_id)
    mark_edited(doc, timeline_id, ids[max(index - 1, 0) : index + 1])
