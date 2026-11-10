"""The seam between a `tla.Document` and TiLiA's state, as pure functions.

TiLiA keeps its own objects and, beside them, the document it read. It holds the
state it last gave the document, and applies only what differs from it. So what
TiLiA fills in on loading is the same on both sides and never reaches the file,
and what TiLiA doesn't know stays in the document, which nothing rewrites.

This module imports neither Qt nor the requests. Of the app, it imports only
TiLiA's digest, so that the digests it gives are those TiLiA's objects give.
"""

from __future__ import annotations

import copy
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from tilia.timelines.hash_timelines import hash_function
from tilia_core import tla
from tilia_core.timemap import pattern

State = dict[str, Any]
# What `apply_changes` took out of the document this session, so that it comes
# back whole: timelines, components and scores by their ids; under keys of their own,
# the state each timeline and component had, a range row, a measure mark, a number
# the bridge wrote, the scores a timeline held, and the stored ordinals of each order
# the timelines left.
Removed = dict[str, tla.Timeline | tla.Component | tla.Score | dict[str, Any]]

# `Timeline.type_name()` and `ComponentKind.NAME`, and the document's names for them.
TIMELINE_KINDS: dict[str, str] = {
    name: name.lower()
    for name in (
        "Slider",
        "Hierarchy",
        "Marker",
        "Beat",
        "Harmony",
        "Range",
        "Score",
        "Pdf",
        "AudioWave",
    )
}
# No AudioWave: its amplitude bars aren't stored, since TiLiA computes them.
COMPONENT_KINDS: dict[str, str] = {
    name: name.lower()
    for name in (
        "HIERARCHY",
        "MARKER",
        "RANGE",
        "HARMONY",
        "MODE",
        "BEAT",
        "PDF_MARKER",
        "NOTE",
        "STAFF",
        "CLEF",
        "KEY_SIGNATURE",
        "TIME_SIGNATURE",
        "BAR_LINE",
        "SCORE_ANNOTATION",
    )
}
_TIMELINE_NAMES = {kind: name for name, kind in TIMELINE_KINDS.items()}
_COMPONENT_NAMES = {kind: name for name, kind in COMPONENT_KINDS.items()}

# A timeline's attributes kept in `Timeline.attrs` under the same name. The name,
# the ordinal, the fields, a range's rows, a beat timeline's pattern and lists and
# a score timeline's score have mappings of their own.
_EVERY_TIMELINE = ("height", "is_visible", "measure_table")
TIMELINE_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "slider": _EVERY_TIMELINE,
    "hierarchy": _EVERY_TIMELINE,
    "marker": _EVERY_TIMELINE,
    "beat": (*_EVERY_TIMELINE, "measure_source"),
    "harmony": (
        "is_visible",
        "level_count",
        "level_height",
        "visible_level_count",
        "measure_table",
    ),
    "range": (*_EVERY_TIMELINE, "default_row_height"),
    "score": _EVERY_TIMELINE,
    "pdf": (*_EVERY_TIMELINE, "path"),
    "audiowave": _EVERY_TIMELINE,
}
# A component's attributes in TiLiA's order, its kind's `SERIALIZABLE`, which is
# what its digest goes through. The names are the same on both sides. A beat has
# only its time until the beat timeline is on the marks: see `_apply_measures`.
COMPONENT_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "hierarchy": (
        "start",
        "pre_start",
        "end",
        "post_end",
        "level",
        "label",
        "color",
        "comments",
    ),
    "marker": ("time", "comments", "label", "color"),
    "range": (
        "start",
        "end",
        "row_id",
        "label",
        "color",
        "comments",
        "joined_right",
        "pre_start",
        "post_end",
    ),
    "harmony": (
        "time",
        "comments",
        "step",
        "accidental",
        "quality",
        "inversion",
        "applied_to",
        "level",
        "display_mode",
        "custom_text",
        "custom_text_font_type",
    ),
    "mode": ("time", "step", "accidental", "type", "comments", "level"),
    "beat": ("time",),
    "pdf_marker": ("time", "page_number"),
    "note": (
        "start",
        "end",
        "step",
        "accidental",
        "octave",
        "staff_index",
        "color",
        "comments",
        "display_accidental",
    ),
    "staff": ("line_count", "index"),
    "clef": ("staff_index", "time", "line_number", "step", "octave", "icon"),
    "key_signature": ("staff_index", "time", "fifths"),
    "time_signature": ("staff_index", "time", "numerator", "denominator", "pairs"),
    "bar_line": ("time",),
    "score_annotation": ("x", "y", "viewer_id", "text", "font_size"),
}
# TiLiA's, and not in the format's layout: to the core, a key it doesn't know
# (TimeLineAnnotator/project-management#511, a time signature's pairs).
_UNKNOWN_TO_THE_CORE = frozenset({"pairs"})
# TiLiA fills these from another attribute when they are unset.
_FOLLOWS = {"pre_start": "start", "post_end": "end"}
_ROW_KEYS = ("id", "name", "color", "height")
_MEDIA_LENGTH = "media length"
_DEFAULT_BEAT_PATTERN = [4]
_LEGACY_SCORE = "svg-osmd-legacy"


def state_of(doc: tla.Document) -> dict[str, State]:
    """The state's `timelines`: every timeline and component of a kind TiLiA knows,
    in display order, each with a digest. The live ordinal is a position from 1."""
    known = [tl for tl in doc.timelines.values() if tl.kind in _TIMELINE_NAMES]
    known.sort(key=lambda timeline: (timeline.ordinal, timeline.id))
    return {
        timeline.id: _timeline_state(doc, timeline, position)
        for position, timeline in enumerate(known, start=1)
    }


def apply_changes(
    doc: tla.Document, synced: State, current: State, *, removed: Removed
) -> list[str]:
    """Changes the document by what differs from `synced` to `current`, two states as
    `App.get_app_state` gives them. A timeline or component is looked at only if its
    digest differs, then attribute by attribute: an attribute that differs is written,
    and one that doesn't is left as the document has it.

    What it takes out goes into `removed`, with the state it had in `synced`, and comes
    back from there whole if its id returns.

    Gives a note, for the caller to log, for each thing of the file it couldn't keep as
    it was: a measure mark a beat no longer holds, and a repeat that names another
    measure, or none."""
    notes: list[str] = []
    _apply_file_fields(doc, synced, current)
    _apply_timelines(doc, synced["timelines"], current["timelines"], removed, notes)
    return notes


def component_for_rules(id: str, kind: str, attrs: Mapping[str, Any]) -> tla.Component:
    """One component of the state, as `rules.check_timeline` takes it. A kind that
    isn't stored is one the rules don't cover."""
    document_kind = COMPONENT_KINDS.get(kind)
    if document_kind is None:
        return tla.Component(id=id, kind=tla.UnknownKind(kind))
    names = COMPONENT_ATTRIBUTES[document_kind]
    return tla.Component(
        id=id,
        kind=document_kind,
        attrs={name: attrs[name] for name in names if name in attrs},
    )


def stored_ordinals(
    doc: tla.Document, order: Sequence[str], *, removed: Removed | None = None
) -> dict[str, int]:
    """The ordinals the file stores for these timelines, given by id in display order.

    The slots are the stored ordinals of those the document has, sorted, then one free
    ordinal for each new one: above every stored one, unknown kinds included, and above
    those of the timelines in `removed`, which an undo can bring back. They take the
    slots in display order, so a deletion changes no other timeline, a swap two, and a
    new timeline at the end takes the next ordinal. A timeline of a kind TiLiA doesn't
    know keeps its own, and isn't given one."""
    timelines = doc.timelines
    known = [
        id
        for id in order
        if id not in timelines or timelines[id].kind in _TIMELINE_NAMES
    ]
    slots = sorted(timelines[id].ordinal for id in known if id in timelines)
    taken = [timeline.ordinal for timeline in timelines.values()]
    taken += [
        item.ordinal
        for item in (removed or {}).values()
        if isinstance(item, tla.Timeline)
    ]
    top = max(taken, default=0)
    new_count = sum(id not in timelines for id in known)
    slots.extend(range(top + 1, top + 1 + new_count))
    return dict(zip(known, slots, strict=True))


# From the document to the state


def _timeline_state(doc: tla.Document, timeline: tla.Timeline, ordinal: int) -> State:
    kind = timeline.kind
    state: State = {"kind": _TIMELINE_NAMES[kind], "ordinal": ordinal}
    if kind != "slider":
        state["name"] = timeline.name
    for attr in TIMELINE_ATTRIBUTES[kind]:
        state[attr] = timeline.attrs.get(attr)
    state["fields"] = copy.deepcopy(timeline.metadata)
    components: Iterable[tla.Component] = timeline.components.values()
    if kind == "range":
        state["rows"] = [
            {key: row.get(key) for key in _ROW_KEYS}
            for row in timeline.attrs.get("rows") or ()
        ]
    elif kind == "score":
        state.update(_score_state(doc, timeline))
    elif kind == "beat":
        state["beat_pattern"] = _beat_pattern(timeline)
        rows = _measure_rows(timeline)
        state["beats_in_measure"] = [len(row.beats) for row in rows]
        state["measure_numbers"] = [row.number for row in rows]
        state["measures_to_force_display"] = [
            index for index, row in enumerate(rows) if row.force_display
        ]
        # In no measure, a beat has no place in these lists, so it stays out: one
        # without a time (FR-048), a tap on a closing barline, one before the first mark.
        in_a_measure = {beat_id for row in rows for beat_id in row.beats}
        components = [c for c in components if c.id in in_a_measure]
    state["hash"] = hash_function("|".join(str(value) for value in state.values()))
    state["components"] = {
        component.id: _component_state(component)
        for component in components
        if component.kind in _COMPONENT_NAMES
    }
    state["components_hash"] = hash_function(
        "".join(
            f"{digest}|"
            for digest in sorted(c["hash"] for c in state["components"].values())
        )
    )
    return state


def _component_state(component: tla.Component) -> State:
    """With the digest TiLiA's object gives, from the same function."""
    state: State = {}
    digest = ""
    for attr in COMPONENT_ATTRIBUTES[component.kind]:
        value = component.attrs.get(attr, component.extra.get(attr))
        if value is None and attr in _FOLLOWS:
            value = component.attrs.get(_FOLLOWS[attr])
        digest += f"|{value}"
        if attr in component.attrs or attr in _FOLLOWS or attr in _UNKNOWN_TO_THE_CORE:
            state[attr] = copy.deepcopy(value)
    state["kind"] = _COMPONENT_NAMES[component.kind]
    state["hash"] = hash_function(digest)
    return state


def _beat_pattern(timeline: tla.Timeline) -> list[int]:
    text = timeline.attrs.get("beat_pattern")
    parsed = pattern.parse(text) if isinstance(text, str) else None
    if parsed is None or not parsed.is_complete or not parsed.bars:
        return list(_DEFAULT_BEAT_PATTERN)
    return parsed.bars


def _measure_rows(timeline: tla.Timeline) -> list[tla.Measure]:
    table = tla.measure_table(timeline)
    return table.rows if table is not None else []


def _score_state(doc: tla.Document, timeline: tla.Timeline) -> State:
    """A legacy score, for today's viewer. That viewer can't draw another format, so
    one of those isn't given to it, and stays in the document as it is."""
    score = doc.scores.get(timeline.attrs.get("score"))
    if score is None or score.format != _LEGACY_SCORE:
        return {"svg_data": "", "viewer_beat_x": {}}
    return {"svg_data": score.text, "viewer_beat_x": _beat_positions(score)}


def _beat_positions(score: tla.Score) -> dict[float, float]:
    """`beat_x`, `[position, x]` pairs, as the viewer holds it. The reader refuses
    anything but lists of numbers, and doesn't look at their length."""
    return {
        float(pair[0]): pair[1]
        for pair in score.extra.get("beat_x", ())
        if len(pair) >= 2
    }


# From the state to the document: the file's fields


def _apply_file_fields(doc: tla.Document, synced: State, current: State) -> None:
    before = dict(synced["media_metadata"])
    after = dict(current["media_metadata"])
    length_before = before.pop(_MEDIA_LENGTH, None)
    length_after = after.pop(_MEDIA_LENGTH, None)
    if length_after != length_before:
        doc.media_length = length_after or None  # TiLiA's 0 is unknown
    _apply_fields(doc.metadata, before, after)
    if current["media_path"] != synced["media_path"]:
        doc.media_path = tla.as_media_path(current["media_path"])


def _apply_fields(
    fields: dict[str, Any], before: Mapping[str, Any], after: Mapping[str, Any]
) -> None:
    """An added field goes last, a removed one goes, a changed value stays in its
    place, and the others aren't touched, whatever the order or the fields that
    TiLiA adds on loading, which are the same on both sides."""
    for name in before.keys() - after.keys():
        fields.pop(name, None)
    for name, value in after.items():
        if name not in before or value != before[name]:
            fields[name] = copy.deepcopy(value)


# Timelines


def _apply_timelines(
    doc: tla.Document,
    before: Mapping[str, State],
    after: Mapping[str, State],
    removed: Removed,
    notes: list[str],
) -> None:
    order = _display_order(after)
    order_changed = order != _display_order(before)
    if order_changed:
        _remember_ordinals(doc, _display_order(before), removed)
    for timeline_id in before.keys() - after.keys():
        _take_out_timeline(doc, timeline_id, before[timeline_id], removed)
    for timeline_id, state in after.items():
        was = before.get(timeline_id)
        if was is None:
            back = removed.get(timeline_id)
            if not isinstance(back, tla.Timeline):
                continue
            del removed[timeline_id]
            _put_back_timeline(doc, back, removed)
            was = removed.pop(_state_key(timeline_id), None) or _timeline_state(
                doc, back, state["ordinal"]
            )
        timeline = doc.timelines.get(timeline_id)
        if timeline is not None:
            _apply_timeline(doc, timeline, was, state, removed, notes)
    if not order_changed:
        return
    # A timeline both states hold and the document doesn't isn't stored, and has
    # no slot: a slider nobody has changed (FR-007).
    stored = [id for id in order if id in doc.timelines or id not in before]
    ordinals = _remembered_ordinals(stored, removed) or stored_ordinals(
        doc, stored, removed=removed
    )
    for timeline_id, ordinal in ordinals.items():
        if timeline_id in doc.timelines:
            doc.timelines[timeline_id].ordinal = ordinal
        else:
            _add_timeline(doc, timeline_id, after[timeline_id], ordinal, removed, notes)


def _display_order(timelines: Mapping[str, State]) -> list[str]:
    return sorted(timelines, key=lambda id: (timelines[id]["ordinal"], id))


def _remember_ordinals(doc: tla.Document, order: list[str], removed: Removed) -> None:
    """The stored ordinals of an order the timelines are leaving, so that going back
    to it, as an undo does, gives them back, rather than new slots."""
    stored = [id for id in order if id in doc.timelines]
    ordinals = {id: doc.timelines[id].ordinal for id in stored}
    removed[_ordinals_key(stored)] = ordinals


def _remembered_ordinals(order: list[str], removed: Removed) -> dict[str, int] | None:
    remembered = removed.get(_ordinals_key(order))
    return remembered if isinstance(remembered, dict) else None


def _ordinals_key(order: list[str]) -> str:
    return "ordinals/" + "|".join(order)


def _state_key(id: str) -> str:
    """Where `removed` keeps the state a timeline or component had in `synced`, so
    that it comes back compared with what TiLiA held, not with the document: what
    TiLiA fills in, such as a PDF's path where it was found, isn't written then."""
    return f"{id}/state"


def _take_out_timeline(
    doc: tla.Document, timeline_id: str, was: State, removed: Removed
) -> None:
    timeline = doc.timelines.pop(timeline_id, None)
    if timeline is not None:
        removed[timeline_id] = timeline
        removed[_state_key(timeline_id)] = copy.deepcopy(was)
        _release_score(doc, timeline.attrs.get("score"), removed)


def _put_back_timeline(
    doc: tla.Document, timeline: tla.Timeline, removed: Removed
) -> None:
    doc.timelines[timeline.id] = timeline
    doc.timelines = dict(sorted(doc.timelines.items()))
    score_id = timeline.attrs.get("score")
    if isinstance(removed.get(score_id), tla.Score):
        doc.scores[score_id] = removed.pop(score_id)
        doc.scores = dict(sorted(doc.scores.items()))


def _add_timeline(
    doc: tla.Document,
    timeline_id: str,
    state: State,
    ordinal: int,
    removed: Removed,
    notes: list[str],
) -> None:
    kind = TIMELINE_KINDS.get(state["kind"])
    if kind is None:
        return
    timeline = tla.Timeline(id=timeline_id, kind=kind, ordinal=ordinal)
    doc.timelines[timeline_id] = timeline
    doc.timelines = dict(sorted(doc.timelines.items()))
    _apply_timeline(doc, timeline, {}, state, removed, notes)


def _apply_timeline(
    doc: tla.Document,
    timeline: tla.Timeline,
    was: State,
    state: State,
    removed: Removed,
    notes: list[str],
) -> None:
    attributes_may_differ = _digest_differs(was, state)
    if attributes_may_differ:
        _apply_timeline_attributes(doc, timeline, was, state, removed)
    components_changed = _apply_components(
        timeline, was.get("components", {}), state.get("components", {}), removed
    )
    if timeline.kind == "range" and components_changed:
        _store_rows_named(timeline, state, removed)
    if timeline.kind == "beat" and (attributes_may_differ or components_changed):
        _apply_measures(timeline, was, state, removed, notes)
        timeline.measures = tla.measure_table(timeline)


def _digest_differs(was: State, state: State) -> bool:
    """An empty digest says nothing: a slider's always is."""
    digest = state.get("hash")
    return not digest or digest != was.get("hash")


def _apply_timeline_attributes(
    doc: tla.Document,
    timeline: tla.Timeline,
    was: State,
    state: State,
    removed: Removed,
) -> None:
    if "name" in state and state["name"] != was.get("name"):
        timeline.name = state["name"]
    for attr in TIMELINE_ATTRIBUTES[timeline.kind]:
        if attr in state and state[attr] != was.get(attr):
            timeline.attrs[attr] = state[attr]
    if "fields" in state:
        _apply_fields(timeline.metadata, was.get("fields", {}), state["fields"])
    if timeline.kind == "range" and state.get("rows") != was.get("rows"):
        _apply_rows(timeline, state.get("rows") or [], removed)
    elif timeline.kind == "score":
        _apply_score(doc, timeline, was, state, removed)
    elif timeline.kind == "beat" and state.get("beat_pattern") != was.get(
        "beat_pattern"
    ):
        timeline.attrs["beat_pattern"] = pattern.format_bars(state["beat_pattern"])


def _apply_rows(
    timeline: tla.Timeline, rows: list[dict[str, Any]], removed: Removed
) -> None:
    """A row that stays keeps the keys TiLiA doesn't show, and one that goes keeps them
    in `removed`."""
    stored = {row["id"]: row for row in timeline.attrs.get("rows") or ()}
    staying = {row["id"] for row in rows}
    for row_id, row in stored.items():
        if row_id not in staying:
            removed[_row_key(timeline.id, row_id)] = row
    timeline.attrs["rows"] = [
        {
            **(
                stored.get(row["id"])
                or removed.pop(_row_key(timeline.id, row["id"]), {})
            ),
            **row,
        }
        for row in rows
    ]


def _store_rows_named(timeline: tla.Timeline, state: State, removed: Removed) -> None:
    """A row TiLiA filled in, such as "Row 0" of a range timeline with none, is
    stored once a range names it, so that the file names no row it doesn't have."""
    stored = {row["id"] for row in timeline.attrs.get("rows") or ()}
    named = {
        component.attrs.get("row_id")
        for component in timeline.components.values()
        if component.kind == "range"
    }
    rows = state.get("rows") or []
    if (named - stored) & {row["id"] for row in rows}:
        _apply_rows(timeline, rows, removed)


def _row_key(timeline_id: str, row_id: str) -> str:
    # Row ids are unique only in their timeline: a duplicate's rows keep them.
    return f"{timeline_id}/{row_id}"


# Legacy scores


def _apply_score(
    doc: tla.Document,
    timeline: tla.Timeline,
    was: State,
    state: State,
    removed: Removed,
) -> None:
    svg = state.get("svg_data") or ""
    positions = state.get("viewer_beat_x") or {}
    had_svg = was.get("svg_data") or ""
    if svg == had_svg and positions == (was.get("viewer_beat_x") or {}):
        return
    score = doc.scores.get(timeline.attrs.get("score"))
    if svg != had_svg:
        # An import makes a new score, and clearing leaves none (R16). The score the
        # timeline held is set aside whole, so that an undo gives it back.
        held = removed.setdefault(_held_key(timeline.id), {})
        if score is not None:
            timeline.attrs["score"] = None
            held.pop(score.id, None)
            held[score.id] = score
            _release_score(doc, score.id, removed)
        score = _held_score(held, svg)
        if score is None:
            return
        _put_back_score(doc, timeline, score, removed)
    if score is None or score.format != _LEGACY_SCORE:
        return
    if "beat_x" in score.extra and _beat_positions(score) == positions:
        return
    if _named_elsewhere(doc, timeline, score.id):
        # Another timeline names it, and keeps it as it is.
        score = copy.deepcopy(score)
        score.id = tla.new_id()
        _put_back_score(doc, timeline, score, removed)
    score.extra["beat_x"] = [[at, positions[at]] for at in sorted(positions)]


def _held_key(timeline_id: str) -> str:
    """Where `removed` keeps the scores a timeline held, by id, the last one last."""
    return f"{timeline_id}/scores"


def _held_score(held: dict[str, tla.Score], svg: str) -> tla.Score | None:
    """For a drawing, the last score the timeline held with it, or a new one. For no
    drawing, the last one of another format an import replaced, or none: an undo of
    that import gives it back."""
    for score in reversed(list(held.values())):
        if svg and score.format == _LEGACY_SCORE and score.text == svg:
            return held.pop(score.id)
        if not svg and score.format != _LEGACY_SCORE:
            return held.pop(score.id)
    if not svg:
        return None
    score = tla.Score(id=tla.new_id(), format=_LEGACY_SCORE)
    score.text = svg
    return score


def _put_back_score(
    doc: tla.Document, timeline: tla.Timeline, score: tla.Score, removed: Removed
) -> None:
    if removed.get(score.id) is score:
        del removed[score.id]
    doc.scores[score.id] = score
    doc.scores = dict(sorted(doc.scores.items()))
    timeline.attrs["score"] = score.id


def _release_score(doc: tla.Document, score_id: str | None, removed: Removed) -> None:
    """Takes out a score no timeline names any more, so no entry is left that nothing
    names."""
    if score_id not in doc.scores:
        return
    if not any(_names_score(tl, score_id) for tl in doc.timelines.values()):
        removed[score_id] = doc.scores.pop(score_id)


def _named_elsewhere(doc: tla.Document, timeline: tla.Timeline, score_id: str) -> bool:
    return any(
        tl is not timeline and _names_score(tl, score_id)
        for tl in doc.timelines.values()
    )


def _names_score(timeline: tla.Timeline, score_id: str) -> bool:
    """A timeline of a kind TiLiA doesn't know keeps its keys in `raw`."""
    raw = timeline.raw or {}
    return score_id in (timeline.attrs.get("score"), raw.get("score"))


# Components


def _apply_components(
    timeline: tla.Timeline,
    before: Mapping[str, State],
    after: Mapping[str, State],
    removed: Removed,
) -> bool:
    """Whether anything changed. Each component's own digest is looked at, since
    `components_hash` can't tell: it doesn't know whose values they are."""
    components = timeline.components
    changed = False
    for component_id in before.keys() - after.keys():
        component = components.pop(component_id, None)
        if component is not None:
            removed[component_id] = component
            removed[_state_key(component_id)] = copy.deepcopy(before[component_id])
            changed = True
    added = False
    for component_id, state in after.items():
        was = before.get(component_id)
        if was is None:
            back = removed.get(component_id)
            if isinstance(back, tla.Component):
                del removed[component_id]
                components[component_id] = back
                was = removed.pop(_state_key(component_id), None) or _component_state(
                    back
                )
                added = True
            else:
                kind = COMPONENT_KINDS.get(state.get("kind"))
                if kind is not None:
                    components[component_id] = _new_component(component_id, kind, state)
                    added = True
                continue
        if not _digest_differs(was, state):
            continue
        component = components.get(component_id)
        if component is not None:
            changed = _apply_component(component, was, state) or changed
        elif (kind := COMPONENT_KINDS.get(state.get("kind"))) is not None:
            # One TiLiA filled in, such as the unit of an empty hierarchy timeline:
            # stored once it is edited.
            components[component_id] = _new_component(component_id, kind, state)
            added = True
    if added:
        timeline.components = dict(sorted(components.items()))
    return changed or added


def _new_component(component_id: str, kind: str, state: State) -> tla.Component:
    component = tla.Component(id=component_id, kind=kind)
    for attr in COMPONENT_ATTRIBUTES[kind]:
        if attr in state and not (
            attr in _FOLLOWS and state[attr] == state.get(_FOLLOWS[attr])
        ):
            _set_attribute(component, attr, state[attr])
    return component


def _apply_component(component: tla.Component, was: State, state: State) -> bool:
    """Whether an attribute differs. A `pre_start` or `post_end` follows its `start` or
    `end` when it equals it, so once the component is edited, one that does is unset,
    and one that doesn't is written: unset, it would read as the `start` or `end`.
    Until then it stays as the file has it."""
    edited = False
    for attr in COMPONENT_ATTRIBUTES.get(component.kind, ()):
        if attr in state and state[attr] != was.get(attr):
            edited = True
            if attr not in _FOLLOWS:
                _set_attribute(component, attr, state[attr])
    if edited:
        for attr, followed in _FOLLOWS.items():
            if attr not in state:
                continue
            if state[attr] == state.get(followed):
                component.attrs.pop(attr, None)
            elif component.attrs.get(attr) != state[attr]:
                component.attrs[attr] = state[attr]
    return edited


def _set_attribute(component: tla.Component, attr: str, value: Any) -> None:
    if attr not in _UNKNOWN_TO_THE_CORE:
        component.attrs[attr] = copy.deepcopy(value)
    elif value is None:
        component.extra.pop(attr, None)
    else:
        component.extra[attr] = copy.deepcopy(value)


# A beat timeline's measures, until it is on the marks: TiLiA's lists from the marks
# (`_timeline_state`), and back. This goes when the beat timeline is on the marks
# (TimeLineAnnotator/project-management#466).


def _apply_measures(
    timeline: tla.Timeline,
    was: State,
    state: State,
    removed: Removed,
    notes: list[str],
) -> None:
    if _measures_of(was) != _measures_of(state):
        _rewrite_marks(timeline, state, removed, notes)


def _measures_of(state: State) -> tuple[Any, ...]:
    return (
        _beats_in_order(state.get("components", {})),
        state.get("beats_in_measure"),
        state.get("measure_numbers"),
        state.get("measures_to_force_display"),
    )


def _beats_in_order(beats: Mapping[str, State]) -> list[str]:
    return sorted(beats, key=lambda id: (beats[id]["time"], id))


def _rewrite_marks(
    timeline: tla.Timeline,
    state: State,
    removed: Removed,
    notes: list[str],
) -> None:
    """TiLiA's lists say which beats start a measure, by position. Each measure's mark,
    with all its keys, follows its measure (`_match_measures`), and a `next` keeps
    naming the same measure, so that nothing is lost and the file says what TiLiA
    shows. A measure that is gone leaves its mark in `removed`, a deleted downbeat's
    staying with the beat, and hands its `restart` and the `next`s naming it to the next
    measure that stays, as the core does when a downbeat is deleted. What a mark has
    that way is kept in `removed` with it, so that an undo gives it back. The measures
    before are the document's table, as it was after the last change."""
    components = timeline.components
    # A beat both states hold and the document doesn't can't have a mark.
    order = [
        id for id in _beats_in_order(state.get("components", {})) if id in components
    ]
    # No counts, with beats: one measure, so the first beat keeps its mark.
    counts = state.get("beats_in_measure") or [len(order)]
    numbers = state.get("measure_numbers") or []
    forced = set(state.get("measures_to_force_display") or ())
    starts = _measure_starts(order, counts)
    indexes = sorted(starts.values())
    after = [beat_id for beat_id, _ in sorted(starts.items(), key=lambda s: s[1])]
    rows = timeline.measures.rows if timeline.measures is not None else []
    before = [row.id for row in rows]
    pairs = _match_measures(before, after)
    sources = {place: source for source, place in pairs.items()}
    marks = _take_marks(rows, components, removed)
    # What `removed` keeps of a mark is under the beat it is on, so it moves with the
    # mark: all is taken first, since a beat can end one measure's mark and start
    # another's.
    carried = {
        source: _take_records(started, removed)
        for source, (started, _) in marks.items()
    }
    renamed = {before[source]: after[place] for source, place in pairs.items()}
    restarts, gone = _hand_on(rows, pairs, marks, renamed)
    for beat_id in order:
        attrs = components[beat_id].attrs
        if beat_id not in starts and "measure" in attrs:
            _set_aside_mark(timeline, beat_id, attrs.pop("measure"), removed, notes)
    following = 1
    for place, beat_id in enumerate(after):
        index = indexes[place]
        attrs = components[beat_id].attrs
        source = sources.get(place)
        taken = marks.pop(source, None) if source is not None else None
        if isinstance(attrs.get("measure"), dict):
            # A beat back from `removed`, with its own mark: what its measure's
            # downbeat held meanwhile is a copy of it.
            if taken is not None and taken[1] != attrs["measure"]:
                _set_aside_mark(timeline, taken[0], taken[1], removed, notes)
        elif taken is not None:
            attrs["measure"] = taken[1]
            _take_records(beat_id, removed)
            _put_records(beat_id, carried.get(source, {}), removed)
        else:
            attrs["measure"] = removed.pop(_mark_key(beat_id), {})
        mark = attrs["measure"]
        _restart(mark, beat_id, starts, restarts, removed)
        # More numbers than measures, or fewer, as TiLiA's lists can be for a moment.
        number = numbers[index] if index < len(numbers) else following
        _set_measure_number(mark, number, following, _number_key(beat_id), removed)
        if bool(mark.get("force_display")) != (index in forced):
            mark["force_display"] = index in forced
        following = number + 1
    # Measures that are gone: their marks wait in `removed` for an undo, and a
    # deleted downbeat's stays with the beat.
    for source, (started, mark) in marks.items():
        if started in components:
            _set_aside_mark(timeline, started, mark, removed, notes)
        elif _carries_more_than_a_number(mark):
            notes.append(
                f"Beat {started} of timeline {timeline.id}, which started a measure"
                f" that is gone, is deleted: its mark, {mark}, left the file with it."
            )
        _put_records(started, carried.get(source, {}), removed)
    _rename_next(timeline, starts, renamed, set(before), gone, removed, notes)


def _match_measures(before: Sequence[str], after: Sequence[str]) -> dict[int, int]:
    """Each measure before, by its place, with the place of the measure after it is.

    The beats that start a measure before and after, in the longest run they keep
    their order, are the same measures, so each keeps its own mark: so it goes when
    "Add measure zero" adds a measure before them, or when a measure goes. Between two
    of them, measures are matched by their places from the first: TiLiA moves later
    downbeats to other beats when a beat is added or deleted inside a measure, and a
    measure there is the one at its place before, as TiLiA shows it. A measure before
    with none after is gone, and one after with none before is new."""
    where = {beat_id: place for place, beat_id in enumerate(after)}
    common = [(place, where[b]) for place, b in enumerate(before) if b in where]
    pairs: dict[int, int] = {}
    previous = (-1, -1)
    for anchor in [*_longest_increasing(common), (len(before), len(after))]:
        start_before, start_after = previous[0] + 1, previous[1] + 1
        for step in range(min(anchor[0] - start_before, anchor[1] - start_after)):
            pairs[start_before + step] = start_after + step
        if anchor[0] < len(before):
            pairs[anchor[0]] = anchor[1]
        previous = anchor
    return pairs


def _longest_increasing(pairs: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """The longest run of `pairs` whose second items increase, in order: n log n."""
    tails: list[int] = []  # for each length, the pair that ends the best run so far
    ends: list[int] = []  # the second item of that pair
    back: list[int | None] = []
    for position, (_, value) in enumerate(pairs):
        length = bisect_left(ends, value)
        back.append(tails[length - 1] if length else None)
        if length == len(tails):
            tails.append(position)
            ends.append(value)
        else:
            tails[length] = position
            ends[length] = value
    run: list[tuple[int, int]] = []
    position = tails[-1] if tails else None
    while position is not None:
        run.append(pairs[position])
        position = back[position]
    return run[::-1]


def _hand_on(
    rows: Sequence[tla.Measure],
    pairs: Mapping[int, int],
    marks: Mapping[int, tuple[str, dict[str, Any]]],
    renamed: dict[str, str],
) -> tuple[dict[str, tuple[str, int]], set[str]]:
    """What a measure that is gone hands on to the next measure that stays, as the core
    does when a downbeat is deleted: its `restart`, the next one then stating the number
    it read, and the `next`s that named it, which `renamed` gets. Gives, by the downbeat
    after, the gone measure's downbeat and that number, for each `restart`; and the
    downbeats of the measures that are gone."""
    restarts: dict[str, tuple[str, int]] = {}
    gone: set[str] = set()
    for source, row in enumerate(rows):
        if source in pairs:
            continue
        gone.add(row.id)
        stays = next(
            (later for later in range(source + 1, len(rows)) if later in pairs), None
        )
        if stays is None:
            continue
        downbeat = renamed[rows[stays].id]
        renamed[row.id] = downbeat
        mark = marks.get(source, (row.id, {}))[1]
        if mark.get("restart"):
            restarts[downbeat] = (row.id, rows[stays].number)
    return restarts, gone


def _restart(
    mark: dict[str, Any],
    beat_id: str,
    starts: Mapping[str, int],
    restarts: Mapping[str, tuple[str, int]],
    removed: Removed,
) -> None:
    """Hands a gone measure's `restart` on to this mark, or takes it back once that
    measure is back."""
    key = _record_key(beat_id, "restart")
    record = removed.get(key)
    if isinstance(record, dict) and record["from"] in starts:
        del removed[key]
        mark.pop("restart", None)
        if record["number"] is None:
            mark.pop("number", None)
        else:
            mark["number"] = record["number"]
    if beat_id in restarts and not mark.get("restart"):
        gone, number = restarts[beat_id]
        removed[key] = {"from": gone, "number": mark.get("number")}
        mark["restart"] = True
        mark.setdefault("number", number)


def _take_marks(
    rows: Sequence[tla.Measure],
    components: Mapping[str, tla.Component],
    removed: Removed,
) -> dict[int, tuple[str, dict[str, Any]]]:
    """Each measure's mark, by the measure's place, with the beat that started it,
    taken off that beat. A beat deleted since keeps its own, whole, in `removed`, so its
    measure gets a copy."""
    marks: dict[int, tuple[str, dict[str, Any]]] = {}
    for place, row in enumerate(rows):
        component = components.get(row.id)
        if component is not None:
            mark = component.attrs.pop("measure", None)
        else:
            gone = removed.get(row.id)
            held = (
                gone.attrs.get("measure") if isinstance(gone, tla.Component) else None
            )
            mark = copy.deepcopy(held)
        if isinstance(mark, dict):
            marks[place] = (row.id, mark)
    return marks


# What `removed` keeps of a mark, under the beat it is on: a number the bridge wrote,
# a `next` as it was before a name in it changed with a measure that went, and a
# `restart` a gone measure handed on.
_RECORDS = ("number", "next", "restart")


def _record_key(beat_id: str, record: str) -> str:
    return f"{beat_id}/{record}"


def _take_records(beat_id: str, removed: Removed) -> dict[str, Any]:
    taken = {}
    for record in _RECORDS:
        key = _record_key(beat_id, record)
        if key in removed:
            taken[record] = removed.pop(key)
    return taken


def _put_records(beat_id: str, records: Mapping[str, Any], removed: Removed) -> None:
    for record, value in records.items():
        removed[_record_key(beat_id, record)] = value


def _set_aside_mark(
    timeline: tla.Timeline,
    beat_id: str,
    mark: dict[str, Any],
    removed: Removed,
    notes: list[str],
) -> None:
    removed[_mark_key(beat_id)] = mark
    if _carries_more_than_a_number(mark):
        notes.append(
            f"The measure that beat {beat_id} of timeline {timeline.id} started is"
            f" gone: its mark, {mark}, left the file."
        )


def _carries_more_than_a_number(mark: Mapping[str, Any]) -> bool:
    return any(
        value not in (None, False, {}, [])
        for key, value in mark.items()
        if key not in ("number", "force_display")
    )


def _measure_starts(order: Sequence[str], counts: Iterable[int]) -> dict[str, int]:
    """The beats that start a measure, each with its measure's index. A measure of no
    beats starts at none, and a count past the last beat starts nothing."""
    starts: dict[str, int] = {}
    place = 0
    for index, count in enumerate(counts):
        if count > 0 and place < len(order):
            starts[order[place]] = index
            place += count
    return starts


def _set_measure_number(
    mark: dict[str, Any], number: int, following: int, key: str, removed: Removed
) -> None:
    """Without a number, a measure is the one before it plus one. So one a mark didn't
    have is written where it differs from that, and goes again when it no longer does,
    while one the file stores stays a number, as the same edit through `attrs` leaves
    it. `key` in `removed` says the number is one this wrote."""
    if number == following and key in removed:
        mark.pop("number", None)
        del removed[key]
        return
    if mark.get("number", following) == number:
        return
    if "number" not in mark:
        removed[key] = {}
    mark["number"] = number


def _mark_key(beat_id: str) -> str:
    return f"{beat_id}/measure"


def _number_key(beat_id: str) -> str:
    return _record_key(beat_id, "number")


def _rename_next(
    timeline: tla.Timeline,
    starts: Mapping[str, int],
    renamed: Mapping[str, str],
    started_before: set[str],
    gone: set[str],
    removed: Removed,
    notes: list[str],
) -> None:
    """A `next` keeps naming the same measure, at its downbeat now. One that named a
    measure that is gone names the next measure that stays, as `renamed` has it; with
    none, or for a beat that starts no measure, the name goes, since the writer refuses
    a `next` that names no measure. A name of a downbeat the state doesn't hold, such
    as a beat without a time, stays while it is one. A list changed that way is kept as
    it was in `removed`, and comes back once all it named start measures again."""
    components = timeline.components
    for beat_id in starts:
        mark = components[beat_id].attrs["measure"]
        key = _record_key(beat_id, "next")
        record = removed.get(key)
        if isinstance(record, list) and all(
            name in starts or _is_downbeat(components.get(name)) for name in record
        ):
            del removed[key]
            mark["next"] = list(record)
            continue
        following = mark.get("next")
        if not following:
            continue
        followed = []
        for name in following:
            if name in renamed:
                followed.append(renamed[name])
            elif name not in started_before and _is_downbeat(components.get(name)):
                followed.append(name)
        if followed == following:
            continue
        if key not in removed and (
            len(followed) < len(following) or any(name in gone for name in following)
        ):
            removed[key] = list(following)
        if len(followed) < len(following):
            notes.append(
                f"The measure at beat {beat_id} of timeline {timeline.id} was followed"
                f" by {following}, some of which are gone: it is followed by"
                f" {followed or 'the next measure'}."
            )
        if followed:
            mark["next"] = followed
        else:
            del mark["next"]


def _is_downbeat(component: tla.Component | None) -> bool:
    """As the writer reads it: a beat with a mark that isn't a closing tap."""
    if component is None or component.kind != "beat":
        return False
    attrs = component.attrs
    return isinstance(attrs.get("measure"), dict) and not attrs.get("closing")
