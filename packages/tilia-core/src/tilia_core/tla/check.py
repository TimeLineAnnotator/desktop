"""The reader's checks: what it refuses as a broken structure, and what it keeps with a warning.

A file in the current format is checked once it is parsed, before the reader
makes its document (FR-051a). The writer checks what it is about to write in
the same way, so that it never writes a file the reader refuses (FR-034).

Refused, with the place as a JSON Pointer and, when the text is at hand, the
line:

- what the format's JSON Schema checks: the keys each object requires, the
  type of each value, and ids that are UUIDs. They are read from the schema
  shipped in this package, so that the core and the schema agree (FR-090).
  The schema describes its other limits, such as a minimum, without checking
  them: the reader reads a value that breaks one;
- a score whose content has no lines;
- what JSON Schema can't check: an id used twice in the file, or a row's
  used twice in its timeline, and a reference that names nothing.

Kept, with a warning: a timeline's `vocabulary` that isn't a reference to a
vocabulary (FR-072); a component of a kind its timeline doesn't hold, kept as
one of a kind the core doesn't know, its structure checked as its kind's, as
the schema checks it, but not its references.

A null is a missing key: the schema allows one on every key it doesn't
require. A number written with a fraction of zero, such as 1.0, is an integer,
as JSON Schema counts it; the check turns it into one in the content, where
the schema says integer, so that the reader hands it out as one.

A timeline is checked as the kind its file spells exactly, as the writer
writes it; one of a kind the core doesn't know is kept as it is, and only its
kind, name, ordinal, metadata and vocabulary are looked at. So is a
component. Lines are found only when there is something to report.
"""

from __future__ import annotations

import copy
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from tilia_core.tla.errors import UnreadableFile, printable
from tilia_core.tla.layout import _SCHEMA, SCORES, _branch, nfc_text
from tilia_core.tla.model import (
    COMPONENT_KINDS,
    TIMELINE_COMPONENTS,
    TIMELINE_KINDS,
    Kind,
    ReadWarning,
    UnknownKind,
    component_kind_from_file,
    timeline_kind_from_current_file,
)
from tilia_core.tla.parse import lines_of, pointer

_BOM = b"\xef\xbb\xbf"


def check(
    content: Mapping[str, Any],
    source: str | bytes | None = None,
    *,
    path: str | os.PathLike[str] | None = None,
) -> list[ReadWarning]:
    """Check a file's content in the current format, as JSON gives it.

    Raises `UnreadableFile` for a broken structure, naming the first problem,
    its place and, when `source` is given, its line. Returns a warning for
    each rule broken that the reader keeps. Turns each integer written as
    1.0 into 1, in `content` itself. `source` is the text the content was
    read from, or the file's bytes, and is read only to find lines. `path` is
    the file's, for messages.
    """
    checker = _Checker()
    try:
        checker.document(content)
    except _Broken as broken:
        place = _pointer(broken.place)
        line = None
        if source is not None:
            line = lines_of(_text(source), [place])[place]
        raise UnreadableFile(
            broken.message, path=path, line=line, place=place
        ) from None
    if not checker.warnings:
        return []
    warnings = [(_pointer(place), message) for place, message in checker.warnings]
    lines: dict[str, int] = {}
    if source is not None:
        lines = lines_of(_text(source), [place for place, _ in warnings])
    return [
        ReadWarning(place=place, line=lines.get(place), message=message)
        for place, message in warnings
    ]


def _text(source: str | bytes) -> str:
    if isinstance(source, str):
        return source
    return source.removeprefix(_BOM).decode("utf-8")


def _quoted(value: Any) -> str:
    return printable(json.dumps(value, ensure_ascii=False))


# What the schema says about structure, compiled once: types, required keys,
# ids, and what each object and list holds.


_NONE = type(None)
# JSON's types, as Python reads them. JSON's 1.0 is read as a float: where an
# integer is expected, the check turns it into one.
_TYPES: dict[str, frozenset[type]] = {
    "null": frozenset({_NONE}),
    "boolean": frozenset({bool}),
    "integer": frozenset({int}),
    "number": frozenset({int, float}),
    "string": frozenset({str}),
    "array": frozenset({list}),
    "object": frozenset({dict}),
}
# Each type, as a message names what a value should be, in this order.
_EXPECTED = [
    (_TYPES["string"], "text"),
    (_TYPES["integer"], "an integer"),
    (_TYPES["number"], "a number"),
    (_TYPES["boolean"], "true or false"),
    (_TYPES["array"], "a list"),
    (_TYPES["object"], "an object"),
    (_TYPES["null"], "null"),
]
# And what it is. bool before int, which it is a kind of.
_ACTUAL = [
    (_NONE, "null"),
    (bool, "true or false"),
    (int, "a number"),
    (float, "a number"),
    (str, "text"),
    (list, "a list"),
    (dict, "an object"),
]
_DEFINITIONS = "#/$defs/"
# Objects checked by their kind, or a score by its format, against the
# schema's branch for it.
_ENTRIES = frozenset({"timeline", "component", "score"})


def _admits(types: frozenset[type], value: Any) -> bool:
    if type(value) in types:
        return True
    if _whole(value, types):
        return True
    for base, _ in _ACTUAL:  # a subclass, as the writer may be given
        if isinstance(value, base):
            return base in types
    return False


def _whole(value: Any, types: frozenset[type]) -> bool:
    """Whether `value` is a float that JSON Schema counts as an integer, where
    only an integer will do."""
    return (
        type(value) is float
        and int in types
        and float not in types
        and value.is_integer()
    )


def _actual(value: Any) -> str:
    for base, name in _ACTUAL:
        if isinstance(value, base):
            return name
    return type(value).__name__


def _describe(types: frozenset[type]) -> str:
    names = [name for each, name in _EXPECTED if each <= types]
    if "a number" in names:
        names.remove("an integer")
    return " or ".join(names)


@dataclass(frozen=True, eq=False)
class _Spec:
    """What a value must be, from a node of the schema: only its structure."""

    types: frozenset[type] | None = None  # None: any
    expected: str = ""  # the types, as a message names them
    pattern: re.Pattern[str] | None = None  # which the whole value must match
    required: tuple[str, ...] = ()
    properties: Mapping[str, _Spec] = field(default_factory=dict)
    additional: _Spec | None = None  # for the keys `properties` doesn't name
    keys: _Spec | None = None  # what an object's keys must be
    items: _Spec | None = None
    prefix: tuple[_Spec, ...] = ()  # the first items' own
    choices: tuple[_Spec, ...] = ()  # one of these
    entry: str | None = None  # a timeline, component or score
    # The types of the values that need nothing more checked than their type:
    # most values.
    quick: frozenset[type] = field(init=False, default=frozenset())

    def __post_init__(self) -> None:
        object.__setattr__(self, "quick", self._quick())

    def _quick(self) -> frozenset[type]:
        if self.choices:
            quick: set[type] = set()
            taken: set[type] = set()  # by a choice before
            for choice in self.choices:
                if choice.types is None:
                    break
                quick.update(choice.quick - taken)
                taken.update(choice.types)
            return frozenset(quick)
        if (
            self.types is None
            or self.pattern is not None
            or self.required
            or self.properties
            or self.additional is not None
            or self.keys is not None
            or self.items is not None
            or self.prefix
            or self.entry is not None
        ):
            return frozenset()
        return self.types


def _pattern(text: str) -> re.Pattern[str]:
    if not (text.startswith("^") and text.endswith("$")):
        raise ValueError(f"the schema has a pattern that isn't anchored: {text}")
    return re.compile(text[1:-1])


def _merge(first: _Spec, second: _Spec) -> _Spec:
    """What a value that must be both must be."""
    if first.types is None or second.types is None:
        types = first.types if second.types is None else second.types
        expected = first.expected if second.types is None else second.expected
    else:
        types = first.types & second.types
        expected = _describe(types)
    properties = dict(first.properties)
    for key, spec in second.properties.items():
        properties[key] = _merge(properties[key], spec) if key in properties else spec
    required = first.required + tuple(
        key for key in second.required if key not in first.required
    )
    return _Spec(
        types=types,
        expected=expected,
        pattern=second.pattern or first.pattern,
        required=required,
        properties=properties,
        additional=second.additional or first.additional,
        keys=second.keys or first.keys,
        items=second.items or first.items,
        prefix=second.prefix or first.prefix,
        choices=second.choices or first.choices,
        entry=second.entry or first.entry,
    )


_DEFINED: dict[str, _Spec] = {}


def _defined(name: str) -> _Spec:
    """One of the schema's definitions."""
    if name not in _DEFINED:
        spec = _compile(_SCHEMA["$defs"][name])
        if name == "id":
            spec = _Spec(types=spec.types, expected="a UUID", pattern=spec.pattern)
        _DEFINED[name] = spec
    return _DEFINED[name]


def _compile(node: Mapping[str, Any]) -> _Spec:
    """The structure a node of the schema states. An `allOf`, whose branches
    are by kind or format, is left to the entries' checks."""
    types = None
    if "type" in node:
        names = node["type"] if isinstance(node["type"], list) else [node["type"]]
        types = frozenset().union(*(_TYPES[name] for name in names))
    elif "const" in node or "enum" in node:
        # The value isn't structure; its type is.
        values = node["enum"] if "enum" in node else [node["const"]]
        types = frozenset(type(value) for value in values)
    choices = tuple(_compile(choice) for choice in node.get("oneOf", ()))
    if choices:
        expected = " or ".join(choice.expected for choice in choices)
    else:
        expected = "" if types is None else _describe(types)
    additional = node.get("additionalProperties")
    own = _Spec(
        types=types,
        expected=expected,
        pattern=_pattern(node["pattern"]) if "pattern" in node else None,
        required=tuple(node.get("required", ())),
        properties={k: _compile(v) for k, v in node.get("properties", {}).items()},
        additional=_compile(additional) if isinstance(additional, dict) else None,
        keys=_compile(node["propertyNames"]) if "propertyNames" in node else None,
        items=_compile(node["items"]) if "items" in node else None,
        prefix=tuple(_compile(item) for item in node.get("prefixItems", ())),
        choices=choices,
    )
    reference = node.get("$ref")
    if reference is None:
        return own
    if not reference.startswith(_DEFINITIONS):
        raise ValueError(f"the schema refers outside its definitions: {reference}")
    name = reference[len(_DEFINITIONS) :]
    if name in _ENTRIES:
        return _merge(own, _Spec(entry=name))
    return _merge(_defined(name), own)


def _without_branches(name: str) -> _Spec:
    definition = _SCHEMA["$defs"][name]
    return _compile({key: value for key, value in definition.items() if key != "allOf"})


def _branches(name: str, key: str, values: list[str]) -> dict[str, _Spec]:
    """Each branch of a definition, with what the definition says itself."""
    base = _without_branches(name)
    definition = _SCHEMA["$defs"][name]
    return {
        value: _merge(base, _compile(_branch(definition, key, value)))
        for value in values
    }


_DOCUMENT = _compile(_SCHEMA)
_TIMELINE = _without_branches("timeline")
_BY_SPELLING = _branches("timeline", "kind", list(TIMELINE_KINDS.values()))
# By the kind the reader reads, whatever the file's spelling.
_TIMELINES = {kind: _BY_SPELLING[spelling] for kind, spelling in TIMELINE_KINDS.items()}
_COMPONENT = _without_branches("component")
# By the kind as the file spells it: component kinds are read exactly.
_COMPONENTS = _branches("component", "kind", list(COMPONENT_KINDS.values()))
_SCORE = _without_branches("score")
_SCORES = _branches("score", "format", list(SCORES))
# What an object's entries are, for a message about an id.
_ENTRY_NAMES = {"timelines": "timeline", "components": "component"}

# A vocabulary reference: an id of lowercase letters, digits and hyphens ("/"
# is kept for a namespace), and an exact version, MAJOR.MINOR.PATCH; or a bare
# id, for a vocabulary defined in a corpus's manifest (FR-072).
_NUMBER = r"(?:0|[1-9][0-9]*)"
_VOCABULARY = re.compile(rf"[a-z0-9-]+(?:@{_NUMBER}\.{_NUMBER}\.{_NUMBER})?")


# A place in the file, built only when there is something to report: the
# place that holds it and its key there, or None for the whole file.
Place: TypeAlias = "tuple[Place, str | int] | None"


def _pointer(place: Place) -> str:
    steps: list[str] = []
    while place is not None:
        place, step = place
        steps.append(str(step))
    return pointer(steps[::-1])


def _key(place: Place) -> str | int | None:
    return None if place is None else place[1]


class _Broken(Exception):
    def __init__(self, message: str, place: Place) -> None:
        super().__init__(message)
        self.message, self.place = message, place


def _subject(place: Place, name: str | None) -> str:
    """What a message calls a value: its key, or an item of the nearest key's value."""
    key = _key(place)
    if key is None:
        return "the file"
    if isinstance(key, int):
        return f"an item of {_quoted(name)}"
    return _quoted(key)


def _wrong(value: Any, expected: str, place: Place, name: str | None) -> _Broken:
    message = f"{_subject(place, name)} should be {expected}, not {_actual(value)}"
    return _Broken(message, place)


class _Checker:
    """One file's checks: its structure first, in the file's order, then its
    ids and references, which need all of it."""

    def __init__(self) -> None:
        self.warnings: list[tuple[Place, str]] = []
        # Each timeline and score, with its place, in the file's order.
        self.timelines: list[tuple[Place, str, Kind, dict[str, Any]]] = []
        self.scores: list[tuple[Place, dict[str, Any]]] = []
        # The timeline whose components are being checked, and the kinds it
        # holds.
        self.holder: Mapping[str, Any] = {}
        self.holds: frozenset[str] = frozenset()

    def document(self, content: Mapping[str, Any]) -> None:
        self.value(content, _DOCUMENT, None, None)
        self.ids()
        self.references()

    # Structure

    def value(self, value: Any, spec: _Spec, place: Place, name: str | None) -> Any:
        """Check `value`, at `place`, and give it back, an integer written as
        1.0 as an integer. `name` is the nearest key, for a message about an
        item of a list."""
        if spec.choices:
            for choice in spec.choices:
                if choice.types is None or _admits(choice.types, value):
                    spec = choice
                    break
            else:
                raise _wrong(value, spec.expected, place, name)
        if spec.types is not None and not _admits(spec.types, value):
            raise _wrong(value, spec.expected, place, name)
        if spec.types is not None and _whole(value, spec.types):
            return int(value)
        if spec.pattern is not None and not spec.pattern.fullmatch(value):
            message = f"{_subject(place, name)} isn't {spec.expected}: {_quoted(value)}"
            raise _Broken(message, place)
        if spec.entry is not None:
            _ENTRY_CHECKS[spec.entry](self, value, place, name)
        elif isinstance(value, dict):
            self.object(value, spec, place)
        elif isinstance(value, list) and (spec.items is not None or spec.prefix):
            self.list(value, spec, place, name)
        return value

    def object(self, value: dict[str, Any], spec: _Spec, place: Place) -> None:
        for key in spec.required:
            if key not in value:
                raise _Broken(f"{_quoted(key)} is missing", (place, key))
        properties, additional, keys = spec.properties, spec.additional, spec.keys
        if not properties and additional is None and keys is None:
            return
        for key, item in value.items():
            if keys is not None:
                self.key(key, keys, place)
            sub = properties.get(key, additional)
            if sub is None or type(item) in sub.quick:
                continue  # most values: nothing more to check
            checked = self.value(item, sub, (place, key), key)
            if checked is not item:
                value[key] = checked

    def list(
        self, value: list[Any], spec: _Spec, place: Place, name: str | None
    ) -> None:
        for index, item in enumerate(value):
            sub = spec.prefix[index] if index < len(spec.prefix) else spec.items
            if sub is None or type(item) in sub.quick:
                continue
            checked = self.value(item, sub, (place, index), name)
            if checked is not item:
                value[index] = checked

    def key(self, key: str, spec: _Spec, place: Place) -> None:
        """An object's key, which must be an id."""
        if spec.pattern is None or spec.pattern.fullmatch(key):
            return
        what = _ENTRY_NAMES.get(str(_key(place)))
        if what is None:
            message = f"the key {_quoted(key)} isn't {spec.expected}"
        elif not key:
            message = f"a {what} has no id"
        else:
            message = f"a {what}'s id isn't {spec.expected}: {_quoted(key)}"
        raise _Broken(message, (place, key))

    # Entries, each checked against its kind's branch of the schema, or its
    # format's, which holds what the entry's own definition says too

    def timeline(self, value: Any, place: Place, name: str | None) -> None:
        kind: Kind | None = None
        if type(value) is dict and type(value.get("kind")) is str:
            kind = timeline_kind_from_current_file(value["kind"])
        if kind is None or isinstance(kind, UnknownKind):
            self.value(value, _TIMELINE, place, name)
            kind = timeline_kind_from_current_file(value["kind"])
        else:
            self.holder, self.holds = value, TIMELINE_COMPONENTS[kind]
            self.object(value, _TIMELINES[kind], place)
        # A timeline of a kind the core doesn't know is kept as it is: what
        # it holds isn't looked at, its components included, but for its
        # name, ordinal and metadata, which the core uses.
        self.timelines.append((place, str(_key(place)), kind, value))
        self.vocabulary(value, place)

    def component(self, value: Any, place: Place, name: str | None) -> None:
        spec = None
        if type(value) is dict and type(value.get("kind")) is str:
            spec = _COMPONENTS.get(value["kind"])
        if spec is None:
            self.value(value, _COMPONENT, place, name)
        elif component_kind_from_file(value["kind"]) in self.holds:
            self.object(value, spec, place)
        else:
            # Of a kind its timeline doesn't hold: kept as it is, as one of a
            # kind the core doesn't know, so it is checked on a copy (an
            # integer written as 1.0 stays so), and its references aren't.
            self.object(copy.deepcopy(value), spec, place)
            self.warnings.append(
                (
                    place,
                    f"{_which(self.holder)} holds a component of kind"
                    f" {_quoted(value['kind'])}, which a timeline of kind"
                    f" {_quoted(self.holder['kind'])} doesn't have: it is kept as"
                    " it is",
                )
            )

    def score(self, value: Any, place: Place, name: str | None) -> None:
        spec = None
        if type(value) is dict and type(value.get("format")) is str:
            spec = _SCORES.get(value["format"])
        if spec is None:
            self.value(value, _SCORE, place, name)
        else:
            self.object(value, spec, place)
        if not value["content"]:
            # Splitting any text gives a line: empty content is [""].
            raise _Broken("the score's content has no lines", (place, "content"))
        self.scores.append((place, value))

    # Ids and references

    def ids(self) -> None:
        """Refuse an id that two entries of the file share, whatever their kinds."""
        seen: dict[str, str] = {}

        def see(entry_id: str, what: str, place: Place) -> None:
            first = seen.get(entry_id)
            if first is not None:
                both = f"two {what}s" if first == what else f"a {first} and a {what}"
                raise _Broken(f"{both} have the id {_quoted(entry_id)}", place)
            seen[entry_id] = what

        for place, timeline_id, kind, value in self.timelines:
            see(timeline_id, "timeline", place)
            if isinstance(kind, UnknownKind):
                continue
            components = (place, "components")
            for component_id in value["components"]:
                see(component_id, "component", (components, component_id))
            if kind == "range":
                self.row_ids(value["rows"], (place, "rows"))
        for place, score in self.scores:
            see(score["id"], "score", (place, "id"))

    def row_ids(self, rows: list[dict[str, Any]], place: Place) -> None:
        """Refuse an id that two rows of one timeline share: a row's id is
        unique in its timeline only. Compared as the reader gives them: in NFC."""
        seen: set[str] = set()
        for index, row in enumerate(rows):
            row_id = nfc_text(row["id"])
            if row_id in seen:
                message = f"two rows have the id {_quoted(row['id'])}"
                raise _Broken(message, ((place, index), "id"))
            seen.add(row_id)

    def references(self) -> None:
        """Refuse a reference that names nothing."""
        beat_timelines = {
            timeline_id for _, timeline_id, kind, _ in self.timelines if kind == "beat"
        }
        scores = {score["id"] for _, score in self.scores}
        for place, _, kind, value in self.timelines:
            if isinstance(kind, UnknownKind):
                continue
            table = value.get("measure_table")
            if table is not None and table not in beat_timelines:
                raise _Broken(
                    f"a timeline names {_quoted(table)} as its measure table, which"
                    " isn't a beat timeline of the file",
                    (place, "measure_table"),
                )
            if kind == "range":
                self.range_references(value, place)
            elif kind == "score":
                score = value.get("score")
                if score is not None and score not in scores:
                    raise _Broken(
                        f"a score timeline names the score {_quoted(score)}, which"
                        " the file doesn't have",
                        (place, "score"),
                    )
            # A beat timeline's own, the measure mark on its first beat and the
            # downbeats a measure's `next` names, go with its measure table.

    def range_references(self, timeline: Mapping[str, Any], place: Place) -> None:
        # Compared as the reader gives them: in NFC.
        rows = {nfc_text(row["id"]) for row in timeline["rows"]}
        components = timeline["components"]
        for component_id, component in components.items():
            if component["kind"] != COMPONENT_KINDS["range"]:
                continue
            at = ((place, "components"), component_id)
            row = component["row_id"]
            if nfc_text(row) not in rows:
                raise _Broken(
                    f"a range names row {_quoted(row)}, which its timeline"
                    " doesn't have",
                    (at, "row_id"),
                )
            joined = component.get("joined_right")
            if joined is not None and joined not in components:
                raise _Broken(
                    f"a range is joined to {_quoted(joined)}, which its timeline"
                    " doesn't have",
                    (at, "joined_right"),
                )

    # Warnings

    def vocabulary(self, timeline: Mapping[str, Any], place: Place) -> None:
        """Warn about a vocabulary that isn't a reference to one (FR-072)."""
        metadata = timeline.get("metadata")
        if not isinstance(metadata, dict) or "vocabulary" not in metadata:
            return
        vocabulary = metadata["vocabulary"]
        if isinstance(vocabulary, str) and _VOCABULARY.fullmatch(vocabulary):
            return
        self.warnings.append(
            (
                ((place, "metadata"), "vocabulary"),
                f"the vocabulary {_quoted(vocabulary)} of {_which(timeline)} isn't"
                " a valid reference",
            )
        )


def _which(timeline: Mapping[str, Any]) -> str:
    """A timeline, as a warning names it."""
    name = timeline.get("name")
    return f"the timeline {_quoted(name)}" if name else "a timeline without a name"


Entry: TypeAlias = "Callable[[_Checker, Any, Place, str | None], None]"
_ENTRY_CHECKS: dict[str, Entry] = {
    "timeline": _Checker.timeline,
    "component": _Checker.component,
    "score": _Checker.score,
}
