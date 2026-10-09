"""Writing a `Document`: its canonical bytes, and atomic writes with expected fingerprints.

A document is written one way (T5): each object's keys in a fixed order, its
attributes at their default left out, timelines, components and scores in id
order, text in NFC except a score's lines, then `json.dumps` with two-space
indentation and a final newline, in UTF-8 without a byte-order mark. The
order and the defaults are the layout's (`tla.layout`).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping
from operator import itemgetter
from typing import Any

from tilia_core.tla.ids import new_id
from tilia_core.tla.layout import (
    BEAT_UNIT_SHAPE,
    COMPONENT_SHAPES,
    FORMAT_VERSION,
    MEASURE_SHAPE,
    MEDIA_SHAPE,
    NUMBER_AS_TEXT,
    PREVIOUS_NUMBER_PLUS_ONE,
    RANGE_ROW_SHAPE,
    SCORE_SHAPES,
    SCORE_SOURCE_SHAPE,
    TIME_UNITS,
    TIMELINE_MEASURE_SOURCE,
    TIMELINE_SHAPES,
    TOP_SHAPE,
    UNKNOWN_COMPONENT,
    UNKNOWN_COMPONENT_WITH_METADATA,
    UNKNOWN_SCORE,
    UNKNOWN_TIMELINE,
    Shape,
    ascii_keys,
    is_integer,
    nfc_keys,
    nfc_text,
    pointer_to,
)
from tilia_core.tla.model import (
    Component,
    Document,
    Kind,
    Score,
    Timeline,
    UnknownKind,
    component_kind_to_file,
    timeline_kind_to_file,
)

Writer = Callable[[Any, str, "str | int"], Any]

# Every Python reads an integer of fewer than 640 digits back, whatever its
# limit (sys.set_int_max_str_digits); 2000 bits are fewer than 610 digits.
_SHORT_INTEGER_BITS = 2000


def _readable(value: int) -> bool:
    """Whether the running Python can write this integer, and so read it back."""
    if value.bit_length() <= _SHORT_INTEGER_BITS:
        return True
    try:
        str(value)
    except ValueError:  # longer than the limit
        return False
    return True


def _value(value: Any, parent: str, key: str | int) -> Any:
    """`value` as written: text in NFC, objects in their own order. Raises
    ValueError, naming the place, for a value JSON can't hold."""
    kind = type(value)
    if kind is str:
        return value if value.isascii() else nfc_text(value)
    if kind is float and value - value == 0.0:  # finite: not NaN or infinite
        return value
    if isinstance(value, str):
        return nfc_text(value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if _readable(value):
            return value
        raise ValueError(f"{pointer_to(parent, key)}: an integer too long to read back")
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        raise ValueError(
            f"{pointer_to(parent, key)}: {value!r} can't be written: JSON has no"
            " NaN or infinity"
        )
    place = pointer_to(parent, key)
    if isinstance(value, dict):
        return {k: _value(v, place, k) for k, v in _text_keyed(value, place).items()}
    if isinstance(value, (list, tuple)):
        return [_value(item, place, index) for index, item in enumerate(value)]
    raise ValueError(f"{place}: a {type(value).__name__} can't be written in JSON")


def _text_keys(value: Mapping[Any, Any], place: str) -> list[str]:
    for key in value:
        if not isinstance(key, str):
            raise ValueError(f"{place}: a key must be text, not {key!r}")
    return nfc_keys(list(value))


def _text_keyed(value: Mapping[Any, Any], place: str) -> Mapping[str, Any]:
    """`value` with its keys in NFC, checked to be text."""
    try:
        if ascii_keys(value):
            return value
    except TypeError:
        pass  # a key that isn't text, which _text_keys names
    return dict(zip(_text_keys(value, place), value.values(), strict=True))


def _object(
    value: Mapping[str, Any],
    shape: Shape,
    place: str,
    defaults: Mapping[str, Any] | None = None,
    writers: Mapping[str, Writer] | None = None,
) -> dict[str, Any]:
    """An object as written: its known keys in order, then the others, in
    code-point order. A known key that isn't always written is left out when
    it equals its default, by type and value (0 isn't 0.0), or, without one,
    when it is None. `defaults` replaces the shape's own, for a measure's
    mark, whose defaults depend on the marks before it."""
    values = _text_keyed(value, place)
    if defaults is None:
        defaults = shape.defaults
    always, derived, empty = shape.always, shape.derived, shape.left_out_empty
    written: dict[str, Any] = {}
    found = 0
    for key in shape.keys:
        if key not in values:
            continue
        found += 1
        item = values[key]
        kind = type(item)
        if key not in always:
            if item is None and key in derived:
                continue  # a derived default is never null: None means unset
            if key in defaults:
                default = defaults[key]
                if kind is type(default) and item == default:
                    continue
            elif key in empty:
                if kind is dict and not item:
                    continue
            elif key in derived and derived[key] in values:
                # Derived from another key of the object: pre_start from start.
                default = values[derived[key]]
                if kind is type(default) and item == default:
                    continue
            elif item is None:
                continue
        writer = writers.get(key) if writers else None
        if writer is not None:
            written[key] = writer(item, place, key)
        elif (kind is str and item.isascii()) or (kind is float and item - item == 0):
            written[key] = item  # what most values are, written as they are
        else:
            written[key] = _value(item, place, key)
    if found < len(values):
        known = shape.known
        for key in sorted(key for key in values if key not in known):
            written[key] = _value(values[key], place, key)
    return written


def _merged(place: str, *parts: tuple[str, Mapping[str, Any]]) -> dict[str, Any]:
    """An entry's keys, from the places the API holds them: its fields,
    `attrs` and `extra`, named in `parts`, which may not share a key."""
    merged: dict[str, Any] = {}
    for _, part in parts:
        merged.update(part)
    if len(merged) < sum(len(part) for _, part in parts):
        seen: dict[str, str] = {}
        for name, part in parts:
            for key in part:
                if key in seen:
                    raise ValueError(
                        f"{pointer_to(place, key)}: set both in {seen[key]}"
                        f" and in {name}"
                    )
                seen[key] = name
    return merged


def _entries(entries: Mapping[str, Any], place: str) -> list[tuple[str, Any]]:
    """Timelines, components or scores in id order, each checked to be under its own id."""
    for given, entry in entries.items():
        if getattr(entry, "id", given) != given:
            raise ValueError(f"{pointer_to(place, given)}: holds the id {entry.id!r}")
    return sorted(_text_keyed(entries, place).items(), key=itemgetter(0))


def _spelling(to_file: Callable[[Kind], str], kind: Kind, place: str) -> str:
    try:
        return to_file(kind)
    except ValueError as error:
        raise ValueError(f"{place}/kind: {error}") from None


def _time_order(beat: Component) -> tuple[Any, ...]:
    time = beat.attrs.get("time")
    if isinstance(time, (int, float)) and not isinstance(time, bool) and time == time:
        return (0, time, beat.id)
    return (1, 0, beat.id)  # no time, or NaN, which can't be written anyway


def _mark_defaults(timeline: Timeline) -> dict[str, Mapping[str, Any]]:
    """The defaults of the measure marks on a beat timeline's downbeats, by the
    downbeat's id. They depend on the marks before them, in time order, and on
    ids where times are equal: a mark's number is the previous one's plus one,
    its label its number as text, and its source the timeline's
    `measure_source`."""
    source = timeline.attrs.get(
        "measure_source", TIMELINE_SHAPES["beat"].defaults["measure_source"]
    )
    downbeats = sorted(
        (
            c
            for c in timeline.components.values()
            if c.kind == "beat" and isinstance(c.attrs.get("measure"), dict)
        ),
        key=_time_order,
    )
    defaults: dict[str, Mapping[str, Any]] = {}
    previous = None
    for downbeat in downbeats:
        derived: dict[str, Any] = {TIMELINE_MEASURE_SOURCE: source}
        if previous is not None:
            derived[PREVIOUS_NUMBER_PLUS_ONE] = previous + 1
        number = downbeat.attrs["measure"].get("number")
        if number is None:
            number = derived.get(PREVIOUS_NUMBER_PLUS_ONE)
        if not is_integer(number) or not _readable(number):
            number = None  # nothing follows from it
        if number is not None:
            derived[NUMBER_AS_TEXT] = str(number)
        previous = number
        defaults[downbeat.id] = {
            **MEASURE_SHAPE.defaults,
            **{
                key: derived[name]
                for key, name in MEASURE_SHAPE.derived.items()
                if name in derived
            },
        }
    return defaults


def _shaped(shape: Shape) -> Writer:
    """A writer for an object of this shape, whose defaults depend on nothing else."""

    def write(value: Any, parent: str, key: str | int) -> Any:
        if not isinstance(value, dict):
            return _value(value, parent, key)
        return _object(value, shape, pointer_to(parent, key))

    return write


_beat_unit = _shaped(BEAT_UNIT_SHAPE)
_media = _shaped(MEDIA_SHAPE)
_score_source = _shaped(SCORE_SOURCE_SHAPE)
_range_row = _shaped(RANGE_ROW_SHAPE)


def _rows(value: Any, parent: str, key: str | int) -> Any:
    """A range timeline's rows, each in its layout; a tuple as a list."""
    if not isinstance(value, (list, tuple)):
        return _value(value, parent, key)
    place = pointer_to(parent, key)
    return [_range_row(row, place, index) for index, row in enumerate(value)]


def _lines(value: Any, parent: str, key: str | int) -> Any:
    """A score's lines, as they are: never in NFC, since they are the score imported."""
    if not isinstance(value, (list, tuple)):
        return _value(value, parent, key)
    place = pointer_to(parent, key)
    return [
        line if isinstance(line, str) else _value(line, place, index)
        for index, line in enumerate(value)
    ]


def _component(
    component: Component, place: str, mark_defaults: Mapping[str, Any] | None
) -> dict[str, Any]:
    kind = _spelling(component_kind_to_file, component.kind, place)
    value = _merged(
        place,
        (
            "the component's kind and metadata",
            {"kind": kind, "metadata": component.metadata},
        ),
        ("attrs", component.attrs),
        ("extra", component.extra),
    )
    if not isinstance(component.kind, UnknownKind):
        shape = COMPONENT_SHAPES[component.kind]
    elif component._metadata_in_file:
        shape = UNKNOWN_COMPONENT_WITH_METADATA  # kept as it is, even empty
    else:
        shape = UNKNOWN_COMPONENT
    writers: dict[str, Writer] = {}
    if component.kind == "beat":
        marks = MEASURE_SHAPE.defaults if mark_defaults is None else mark_defaults

        def mark(item: Any, parent: str, key: str | int) -> Any:
            # Always written, even empty: a mark is what makes a downbeat.
            if not isinstance(item, dict):
                return _value(item, parent, key)
            return _object(item, MEASURE_SHAPE, pointer_to(parent, key), marks)

        writers = {"measure": mark, "beat_unit": _beat_unit}
    return _object(value, shape, place, writers=writers)


def _components(
    components: Mapping[str, Component],
    place: str,
    marks: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        key: _component(component, pointer_to(place, key), marks.get(component.id))
        for key, component in _entries(components, place)
    }


# The fields a timeline of an unknown kind leaves out at their default, unless
# `raw` has the key.
_RAW_FIELD_DEFAULTS: dict[str, Any] = {"name": "", "ordinal": 0, "metadata": {}}


def _raw_timeline(
    timeline: Timeline, raw: Mapping[str, Any], place: str
) -> dict[str, Any]:
    """A timeline of a kind the core doesn't know, kept as it is: from `raw`,
    with its kind, name, ordinal and metadata from the timeline's fields (a
    field at its default is written only if `raw` has the key), and with
    `attrs` and `extra` set on it. A key set in two of these is refused, as
    for a known kind. Its components are in `raw`."""
    fields = {
        "kind": _spelling(timeline_kind_to_file, timeline.kind, place),
        "name": timeline.name,
        "ordinal": timeline.ordinal,
        "metadata": timeline.metadata,
    }
    edits = _merged(
        place,
        ("the timeline's fields", fields),
        ("attrs", timeline.attrs),
        ("extra", timeline.extra),
    )
    if timeline.components or "components" in edits:
        raise ValueError(
            f"{place}/components: a timeline of a kind the core doesn't know"
            " keeps its components in `raw`"
        )
    value = dict(raw)
    for key, item in edits.items():
        at_default = key in _RAW_FIELD_DEFAULTS and item == _RAW_FIELD_DEFAULTS[key]
        if key in value or not at_default:
            value[key] = item
    return _object(value, UNKNOWN_TIMELINE, place)


def _timeline(timeline: Timeline, place: str) -> dict[str, Any]:
    if isinstance(timeline.kind, UnknownKind) and timeline.raw is not None:
        return _raw_timeline(timeline, timeline.raw, place)
    kind = _spelling(timeline_kind_to_file, timeline.kind, place)
    fields = {
        "kind": kind,
        "name": timeline.name,
        "ordinal": timeline.ordinal,
        "metadata": timeline.metadata,
        "components": timeline.components,
    }
    value = _merged(
        place,
        ("the timeline's fields", fields),
        ("attrs", timeline.attrs),
        ("extra", timeline.extra),
    )
    shape = TIMELINE_SHAPES.get(timeline.kind, UNKNOWN_TIMELINE)
    marks = _mark_defaults(timeline) if timeline.kind == "beat" else {}

    def components(item: Any, parent: str, key: str | int) -> Any:
        if not isinstance(item, dict):
            return _value(item, parent, key)
        return _components(item, pointer_to(parent, key), marks)

    writers: dict[str, Writer] = {"components": components}
    if timeline.kind == "range":
        writers["rows"] = _rows
    return _object(value, shape, place, writers=writers)


def _timelines(timelines: Any, parent: str, key: str | int) -> Any:
    if not isinstance(timelines, dict):
        return _value(timelines, parent, key)
    place = pointer_to(parent, key)
    return {
        key: _timeline(timeline, pointer_to(place, key))
        for key, timeline in _entries(timelines, place)
    }


def _score(score: Score, place: str) -> dict[str, Any]:
    fields: dict[str, Any] = {"id": score.id, "format": score.format}
    if score.source is not None:
        fields["source"] = score.source
    if score.license is not None:
        fields["license"] = score.license
    fields["content"] = score.lines
    value = _merged(place, ("the score's fields", fields), ("extra", score.extra))
    shape = SCORE_SHAPES.get(score.format, UNKNOWN_SCORE)
    writers = {"source": _score_source, "content": _lines}
    return _object(value, shape, place, writers=writers)


def _scores(scores: Any, parent: str, key: str | int) -> Any:
    if not isinstance(scores, dict):
        return _value(scores, parent, key)
    place = pointer_to(parent, key)
    return [
        _score(score, pointer_to(place, index))
        for index, (_, score) in enumerate(_entries(scores, place))
    ]


def _document(doc: Document) -> dict[str, Any]:
    media = _merged(
        "/media",
        (
            "media_path and media_length",
            {"path": doc.media_path, "length": doc.media_length},
        ),
        ("media_extra", doc.media_extra),
    )
    fields = {
        "app_name": doc.app_name,
        "version": FORMAT_VERSION,
        "document_id": doc.document_id,
        "time_unit": doc.time_unit,
        "media": media,
        "metadata": doc.metadata,
        "timelines": doc.timelines,
        "scores": doc.scores,
    }
    value = _merged("", ("the document's fields", fields), ("extra", doc.extra))
    writers = {"media": _media, "timelines": _timelines, "scores": _scores}
    return _object(value, TOP_SHAPE, "", writers=writers)


# A surrogate: UTF-8 can't hold one on its own.
_SURROGATE = re.compile("[\ud800-\udfff]")


def _utf8(text: str) -> bytes:
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        # A pair of surrogates given as two characters becomes the character
        # they stand for, as JSON reads them back; a lone one, as in a label
        # cut inside an emoji, is written as its escape.
        text = text.encode("utf-16-le", "surrogatepass").decode(
            "utf-16-le", "surrogatepass"
        )
        escaped = _SURROGATE.sub(lambda match: f"\\u{ord(match[0]):04x}", text)
        return escaped.encode("utf-8")


def canonical_bytes(doc: Document) -> bytes:
    """The bytes `doc` is written as: the one way to write it, the same on every
    system (FR-016, FR-031, FR-032). For a document read from a file the core
    wrote, they are the file's bytes.

    Raises ValueError, naming the place as a JSON Pointer, for a value JSON
    can't hold: NaN, an infinity, an integer too long to read back, or a
    value of another type than JSON's.
    """
    content = _document(doc)
    text = json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False)
    return _utf8(text + "\n")


def new_document(*, time_unit: str = "seconds") -> Document:
    """An empty document in the current format, with a new document id (FR-035)."""
    if time_unit not in TIME_UNITS:
        units = ", ".join(TIME_UNITS)
        raise ValueError(f"time_unit must be one of {units}, not {time_unit!r}")
    return Document(
        document_id=new_id(), format_version=FORMAT_VERSION, time_unit=time_unit
    )
