"""The layout of a `.tla` file in the current format: each object's keys in the
order they are written, and their defaults, read from the format's JSON Schema.

The reader and the writer share it, with the rules for text (NFC) and for
naming a place in a file (a JSON Pointer). The schema shipped in this package
is the one place the defaults are kept, so that the core and readers without
it leave out and fill in the same values.
"""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from tilia_core.labels import nfc
from tilia_core.tla.model import COMPONENT_KINDS, TIMELINE_KINDS
from tilia_core.tla.parse import pointer

FORMAT_VERSION = "1.0.0-draft.1"


def _load_schema() -> dict[str, Any]:
    schema = files("tilia_core.tla").joinpath("schema")
    name = f"tla-{FORMAT_VERSION}.schema.json"
    return json.loads(schema.joinpath(name).read_bytes())


_SCHEMA = _load_schema()

# Each object's keys, in the order they are written. Keys that aren't listed
# come after these, in code-point order.
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
# a key of the same object: a measure's, from the measures before it and from
# its timeline. The writer implements each by name.
PREVIOUS_NUMBER_PLUS_ONE = "the previous measure's number + 1"
NUMBER_AS_TEXT = "number, as text"
TIMELINE_MEASURE_SOURCE = "the timeline's measure_source"


@dataclass(frozen=True)
class Shape:
    """How one kind of object is written.

    `keys` are its known keys, in order, and `known` the same as a set. Those
    in `always` are always written. The others are left out at their
    default: a value in `defaults`, the `x-default-from` in `derived` that
    names where it comes from, or, for those in `left_out_empty`, an empty
    object.
    """

    keys: tuple[str, ...]
    known: frozenset[str]
    always: frozenset[str]
    defaults: Mapping[str, Any]
    derived: Mapping[str, str]
    left_out_empty: frozenset[str]


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
    defaults: dict[str, Any] = {}
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
        keys=keys,
        known=frozenset(keys),
        always=frozenset(required & set(keys)),
        defaults=defaults,
        derived=derived,
        left_out_empty=frozenset(left_out_empty),
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
# A component of a kind the core doesn't know is kept as it is: if its file
# had "metadata", the key is written even empty.
UNKNOWN_COMPONENT_WITH_METADATA = _shape(
    ("kind", "metadata"), _COMPONENT, always=("metadata",)
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
# keys in ASCII, and so in NFC, without looking at each.
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


def ascii_keys(value: Mapping[str, Any]) -> bool:
    """Whether `value`'s keys are all ASCII text; raises TypeError if a key isn't text."""
    return value.keys() <= _LAYOUT_KEYS or "".join(value).isascii()


def nfc_object(value: dict[str, Any]) -> dict[str, Any]:
    """`value` with its keys in NFC, and its values as they are."""
    if ascii_keys(value):
        return value
    return dict(zip(nfc_keys(list(value)), value.values(), strict=True))


def nfc_value(value: Any) -> Any:
    """`value`, as JSON gives it, with all its text in NFC, keys included. Its
    objects and lists are new ones."""
    kind = type(value)
    if kind is str:
        return value if value.isascii() else nfc_text(value)
    if kind is dict:
        keys = nfc_keys(list(value))
        return dict(zip(keys, map(nfc_value, value.values()), strict=True))
    if kind is list:
        return [nfc_value(item) for item in value]
    return value


# Places and values


def pointer_to(parent: str, key: str | int) -> str:
    """The JSON Pointer to `key` in the value `parent` points to."""
    return parent + pointer([str(key)])


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
