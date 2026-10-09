"""Writing a `Document`: its canonical bytes, and atomic writes with expected fingerprints.

A document is written one way (T5): each object's keys in a fixed order, its
attributes at their default left out, timelines, components and scores in id
order, text in NFC except a score's lines, then `json.dumps` with two-space
indentation and a final newline, in UTF-8 without a byte-order mark. The
defaults are those of the format's JSON Schema, read from the copy in this
package, so that the core and readers without it agree on them.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from operator import itemgetter
from typing import Any

from tilia_core.labels import nfc
from tilia_core.tla.ids import new_id
from tilia_core.tla.model import (
    COMPONENT_KINDS,
    TIMELINE_KINDS,
    Component,
    Document,
    Kind,
    Score,
    Timeline,
    UnknownKind,
    component_kind_to_file,
    timeline_kind_to_file,
)

FORMAT_VERSION = "1.0.0-draft.1"


def _load_schema() -> dict[str, Any]:
    schema = files("tilia_core.tla").joinpath("schema")
    name = f"tla-{FORMAT_VERSION}.schema.json"
    return json.loads(schema.joinpath(name).read_bytes())


_SCHEMA = _load_schema()

# Each object's keys, in the order they are written (the format's layout).
# Keys that aren't listed come after these, in code-point order.
TOP_LEVEL = (
    "app_name",
    "version",
    "document_id",
    "time_unit",
    "media",
    "metadata",
    "timelines",
    "scores",
)
MEDIA = ("path", "length")
# A timeline's keys before and after its kind's own.
TIMELINE_BEFORE = ("kind", "name", "ordinal", "height", "is_visible")
TIMELINE_AFTER = ("measure_table", "metadata", "components")
TIMELINE_OWN: dict[str, tuple[str, ...]] = {
    "slider": (),
    "hierarchy": (),
    "marker": (),
    "beat": ("beat_pattern", "show_time_signatures", "measure_source"),
    "harmony": ("level_count", "level_height", "visible_level_count"),
    "range": ("rows", "default_row_height"),
    "score": ("score",),
    "pdf": ("path",),
    "audiowave": (),
}
# A component's attributes, between its kind and its metadata, in the order
# TiLiA 0.7 writes them.
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
    "beat": ("time", "measure", "beat_unit"),
    "pdf_marker": ("time", "page_number"),
    # A legacy score's components: every attribute is written, as TiLiA 0.7 did.
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
    "time_signature": ("staff_index", "time", "numerator", "denominator"),
    "bar_line": ("time",),
    "score_annotation": ("x", "y", "viewer_id", "text", "font_size"),
}
LEGACY_SCORE_COMPONENTS = frozenset(
    {
        "note",
        "staff",
        "clef",
        "key_signature",
        "time_signature",
        "bar_line",
        "score_annotation",
    }
)
MEASURE = (
    "number",
    "label",
    "force_display",
    "cadenza",
    "restart",
    "next",
    "source",
    "metadata",
)
BEAT_UNIT = ("denominator", "units", "assumed")
RANGE_ROW = ("id", "name", "color", "height")
SCORE = ("id", "format", "content")  # a score of a format the core doesn't know
SCORES = {
    "mei": ("id", "format", "source", "license", "content"),
    "svg-osmd-legacy": ("id", "format", "content", "beat_x"),
}
SCORE_SOURCE = ("file", "origin", "converter")

# The defaults the schema derives (`x-default-from`) from something other than
# a key of the same object, implemented here by name.
PREVIOUS_NUMBER_PLUS_ONE = "the previous measure's number + 1"
NUMBER_AS_TEXT = "number, as text"
TIMELINE_MEASURE_SOURCE = "the timeline's measure_source"


@dataclass(frozen=True)
class Shape:
    """How one kind of object is written: its known keys, in order; those always
    written; and the defaults of the others, at which they are left out. A
    default is a value, or, in `derived`, the `x-default-from` it comes from."""

    keys: tuple[str, ...]
    always: frozenset[str]
    defaults: Mapping[str, Any]
    derived: Mapping[str, str]
    known: frozenset[str]  # the keys, as a set


def _definition(ref: str) -> dict[str, Any]:
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        raise ValueError(f"the schema refers outside its definitions: {ref}")
    return _SCHEMA["$defs"][ref[len(prefix) :]]


def _branch(definition: dict[str, Any], key: str, value: str) -> dict[str, Any]:
    """The `then` of the `allOf` branch whose `if` holds when `key` is `value`."""
    for branch in definition["allOf"]:
        test = branch["if"]["properties"][key]
        if value in test.get("enum", [test.get("const")]):
            return branch["then"]
    raise ValueError(f"the schema has no branch for {key} {value!r}")


def _properties(node: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """An object schema's properties and required keys, with those of the
    definition it refers to."""
    properties: dict[str, Any] = {}
    required: set[str] = set()
    if "$ref" in node:
        properties, required = _properties(_definition(node["$ref"]))
    properties = {**properties, **node.get("properties", {})}
    return properties, required | set(node.get("required", ()))


def _shape(
    keys: tuple[str, ...],
    *nodes: dict[str, Any],
    always: Iterable[str] = (),
    left_out_empty: Iterable[str] = (),
) -> Shape:
    """The shape of objects with these keys, from their schema `nodes`. Keys in
    `always` are always written, as are the schema's required keys; those in
    `left_out_empty` are left out when empty."""
    properties: dict[str, Any] = {}
    required = set(always)
    for node in nodes:
        node_properties, node_required = _properties(node)
        properties.update(node_properties)
        required |= node_required
    defaults: dict[str, Any] = {key: {} for key in left_out_empty}
    derived: dict[str, str] = {}
    for key in keys:
        schema = properties.get(key, {})
        if key in required:
            continue
        if "default" in schema:
            defaults[key] = schema["default"]
        elif "x-default-from" in schema:
            derived[key] = schema["x-default-from"]
    return Shape(
        keys, frozenset(required & set(keys)), defaults, derived, frozenset(keys)
    )


_TIMELINE = _SCHEMA["$defs"]["timeline"]
_COMPONENT = _SCHEMA["$defs"]["component"]
_SCORE = _SCHEMA["$defs"]["score"]

TOP_SHAPE = _shape(TOP_LEVEL, _SCHEMA)
MEDIA_SHAPE = _shape(MEDIA, _SCHEMA["properties"]["media"])
TIMELINE_SHAPES: dict[str, Shape] = {
    kind: _shape(
        TIMELINE_BEFORE + TIMELINE_OWN[kind] + TIMELINE_AFTER,
        _branch(_TIMELINE, "kind", spelling),
        left_out_empty=("metadata",),
    )
    for kind, spelling in TIMELINE_KINDS.items()
}
# A timeline of a kind the core doesn't know is kept as it is: nothing is left
# out, and its own keys, which the core doesn't know, come after these.
UNKNOWN_TIMELINE = _shape(
    TIMELINE_BEFORE + TIMELINE_AFTER, always=TIMELINE_BEFORE + TIMELINE_AFTER
)
COMPONENT_SHAPES: dict[str, Shape] = {
    kind: _shape(
        ("kind", *COMPONENT_ATTRIBUTES[kind], "metadata"),
        _COMPONENT,
        _branch(_COMPONENT, "kind", spelling),
        always=COMPONENT_ATTRIBUTES[kind] if kind in LEGACY_SCORE_COMPONENTS else (),
        left_out_empty=("metadata",),
    )
    for kind, spelling in COMPONENT_KINDS.items()
}
UNKNOWN_COMPONENT = _shape(
    ("kind", "metadata"), _COMPONENT, left_out_empty=("metadata",)
)
MEASURE_SHAPE = _shape(
    MEASURE, _SCHEMA["$defs"]["measure"], left_out_empty=("metadata",)
)
BEAT_UNIT_SHAPE = _shape(BEAT_UNIT, _SCHEMA["$defs"]["beat_unit"])
RANGE_ROW_SHAPE = _shape(
    RANGE_ROW,
    _branch(_TIMELINE, "kind", "Range")["properties"]["rows"]["items"],
)
SCORE_SHAPES: dict[str, Shape] = {
    format: _shape(keys, _SCORE, _branch(_SCORE, "format", format))
    for format, keys in SCORES.items()
}
UNKNOWN_SCORE = _shape(SCORE, _SCORE)
SCORE_SOURCE_SHAPE = _shape(
    SCORE_SOURCE, _branch(_SCORE, "format", "mei")["properties"]["source"]
)
TIME_UNITS: tuple[str, ...] = tuple(_SCHEMA["properties"]["time_unit"]["enum"])
# Every key the layout names: an object whose keys are all among them has its
# keys in ASCII, and in NFC, without looking at each.
_LAYOUT_KEYS = frozenset(
    key
    for shape in (
        TOP_SHAPE,
        MEDIA_SHAPE,
        *TIMELINE_SHAPES.values(),
        *COMPONENT_SHAPES.values(),
        MEASURE_SHAPE,
        BEAT_UNIT_SHAPE,
        RANGE_ROW_SHAPE,
        *SCORE_SHAPES.values(),
        SCORE_SOURCE_SHAPE,
    )
    for key in shape.keys
)


# Text


def nfc_text(text: str) -> str:
    """`text` in NFC, without copying text that already is."""
    if text.isascii() or unicodedata.is_normalized("NFC", text):
        return text
    return nfc(text)


def nfc_keys(keys: list[str]) -> list[str]:
    """An object's keys in NFC, except those NFC would merge with another,
    which are kept as they are, so that no value is lost."""
    normal = [nfc_text(key) for key in keys]
    if len(set(normal)) == len(normal):
        return normal
    counts = Counter(normal)
    return [key if counts[n] > 1 else n for key, n in zip(keys, normal, strict=True)]


def _ascii_keys(value: Mapping[str, Any]) -> bool:
    """Whether `value`'s keys are all ASCII text; raises TypeError if a key isn't text."""
    return value.keys() <= _LAYOUT_KEYS or "".join(value).isascii()


def nfc_object(value: dict[str, Any]) -> dict[str, Any]:
    """`value` with its keys in NFC, and its values as they are."""
    if _ascii_keys(value):
        return value
    return dict(zip(nfc_keys(list(value)), value.values(), strict=True))


def nfc_value(value: Any) -> Any:
    """`value`, as JSON gives it, with all its text in NFC, keys included."""
    kind = type(value)
    if kind is str:
        return value if value.isascii() else nfc_text(value)
    if kind is dict:
        keys = nfc_keys(list(value))
        return dict(zip(keys, map(nfc_value, value.values()), strict=True))
    if kind is list:
        return [nfc_value(item) for item in value]
    return value


# Writing


def pointer_to(parent: str, key: str | int) -> str:
    """The JSON Pointer (RFC 6901) to `key` in the value `parent` points to."""
    return f"{parent}/{str(key).replace('~', '~0').replace('/', '~1')}"


# Python reads an integer of at most 4300 digits (since 3.10.7).
_TOO_LONG = 10**4300

Writer = Callable[[Any, str, "str | int"], Any]


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
        if -_TOO_LONG < value < _TOO_LONG:
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
        if _ascii_keys(value):
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
    """An object as written: its known keys in order, each left out when it
    equals its default, or, without one, when it is None, unless it is always
    written; then the others, in code-point order. `defaults` replaces the
    shape's own, for a measure's mark, whose defaults depend on the marks
    before it."""
    values = _text_keyed(value, place)
    if defaults is None:
        defaults = shape.defaults
    always, derived = shape.always, shape.derived
    written: dict[str, Any] = {}
    found = 0
    for key in shape.keys:
        if key not in values:
            continue
        found += 1
        item = values[key]
        kind = type(item)
        if key not in always:
            # Left out at its default, compared by type and value (0 isn't 0.0).
            if key in defaults:
                default = defaults[key]
                if kind is type(default) and item == default:
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


def _merged(place: str, *parts: Mapping[str, Any]) -> dict[str, Any]:
    """An entry's fields, attributes and unknown keys, as one object."""
    merged: dict[str, Any] = {}
    for part in parts:
        merged.update(part)
    if len(merged) < sum(map(len, parts)):
        seen: set[str] = set()
        for part in parts:
            if not seen.isdisjoint(part):
                key = next(key for key in part if key in seen)
                raise ValueError(
                    f"{pointer_to(place, key)}: set twice, in two of the"
                    " fields, `attrs` and `extra`"
                )
            seen.update(part)
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


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _time_order(beat: Component) -> tuple[Any, ...]:
    time = beat.attrs.get("time")
    if isinstance(time, (int, float)) and not isinstance(time, bool) and time == time:
        return (0, time, beat.id)
    return (1, 0, beat.id)  # no time, or NaN, which can't be written anyway


def _mark_defaults(timeline: Timeline) -> dict[str, Mapping[str, Any]]:
    """The defaults of the measure marks on a beat timeline's downbeats, by the
    downbeat's id. They depend on the marks before them, in time order: a
    mark's number is the previous one's plus one, its label its number as
    text, and its source the timeline's `measure_source`."""
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
        if _is_integer(number):
            derived[NUMBER_AS_TEXT] = str(number)
        previous = number if _is_integer(number) else None
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
    if not isinstance(value, list):
        return _value(value, parent, key)
    place = pointer_to(parent, key)
    return [_range_row(row, place, index) for index, row in enumerate(value)]


def _lines(value: Any, parent: str, key: str | int) -> Any:
    """A score's lines, as they are: never in NFC, since they are the score imported."""
    if not isinstance(value, list):
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
        {"kind": kind, "metadata": component.metadata},
        component.attrs,
        component.extra,
    )
    shape = COMPONENT_SHAPES.get(component.kind, UNKNOWN_COMPONENT)
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


def _timeline(timeline: Timeline, place: str) -> dict[str, Any]:
    if isinstance(timeline.kind, UnknownKind) and timeline.raw is not None:
        # Kept as it is, and written from `raw` alone.
        return _object(timeline.raw, UNKNOWN_TIMELINE, place)
    kind = _spelling(timeline_kind_to_file, timeline.kind, place)
    value = _merged(
        place,
        {
            "kind": kind,
            "name": timeline.name,
            "ordinal": timeline.ordinal,
            "metadata": timeline.metadata,
            "components": timeline.components,
        },
        timeline.attrs,
        timeline.extra,
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
    value = _merged(place, fields, score.extra)
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
        "/media", {"path": doc.media_path, "length": doc.media_length}, doc.media_extra
    )
    value = _merged(
        "",
        {
            "app_name": doc.app_name,
            "version": FORMAT_VERSION,
            "document_id": doc.document_id,
            "time_unit": doc.time_unit,
            "media": media,
            "metadata": doc.metadata,
            "timelines": doc.timelines,
            "scores": doc.scores,
        },
        doc.extra,
    )
    writers = {"media": _media, "timelines": _timelines, "scores": _scores}
    return _object(value, TOP_SHAPE, "", writers=writers)


# A lone surrogate, as in a label cut inside an emoji: UTF-8 can't hold one.
_SURROGATE = re.compile("[\ud800-\udfff]")


def _utf8(text: str) -> bytes:
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        # JSON writes it as an escape, which reads back as the same text.
        escaped = _SURROGATE.sub(lambda match: f"\\u{ord(match[0]):04x}", text)
        return escaped.encode("utf-8")


def canonical_bytes(doc: Document) -> bytes:
    """The bytes `doc` is written as: the one way to write it, the same on every
    system (FR-016, FR-031, FR-032). For a document read from a file the core
    wrote, they are the file's bytes.

    Raises ValueError, naming the place as a JSON Pointer, for a value JSON
    can't hold: NaN, an infinity, or a value of another type than JSON's.
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
