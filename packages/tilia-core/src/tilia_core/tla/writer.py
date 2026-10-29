"""Writing a `Document`: its canonical bytes, and atomic writes with expected fingerprints.

A document is written one way (T5): each object's keys in a fixed order, its
attributes at their default left out, timelines, components and scores in id
order, text in NFC except a score's lines, then `json.dumps` with two-space
indentation and a final newline, in UTF-8 without a byte-order mark. The
order and the defaults are the layout's (`tla.layout`).

A file is written atomically, through the core's one atomic write
(`state.atomic_write`), and a write may state the fingerprint of the version
it expects to replace, or that it expects no file.
"""

from __future__ import annotations

import dataclasses
import enum
import errno
import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Mapping
from operator import itemgetter
from pathlib import Path
from typing import Any

from tilia_core.state import atomic_write
from tilia_core.tla.check import check
from tilia_core.tla.errors import FileChanged, FileInUse, UnreadableFile
from tilia_core.tla.ids import new_id
from tilia_core.tla.layout import (
    BEAT_UNIT_SHAPE,
    COMPONENT_SHAPES,
    FORMAT_VERSION,
    MEASURE_SHAPE,
    MEDIA_SHAPE,
    RANGE_ROW_SHAPE,
    SCORE_SHAPES,
    SCORE_SOURCE_SHAPE,
    TIME_UNITS,
    TIMELINE_SHAPES,
    TOP_SHAPE,
    UNKNOWN_COMPONENT,
    UNKNOWN_COMPONENT_WITH_METADATA,
    UNKNOWN_SCORE,
    UNKNOWN_TIMELINE,
    Shape,
    nfc_object,
    nfc_text,
    pointer_to,
)
from tilia_core.tla.media import (
    SYSTEM,
    absolute_form,
    is_relative,
    relative_path,
    with_slashes,
)
from tilia_core.tla.model import (
    TIMELINE_COMPONENTS,
    Component,
    Document,
    Kind,
    Score,
    Timeline,
    UnknownKind,
    component_kind_from_file,
    component_kind_to_file,
    timeline_kind_to_file,
)
from tilia_core.tla.parse import MAX_DEPTH
from tilia_core.tla.reader import loads, read

Writer = Callable[[Any, str, "str | int"], Any]

# Every Python writes and reads an integer of fewer than 640 digits, whatever
# its limit (sys.set_int_max_str_digits); 2000 bits are fewer than 610 digits.
_SHORT_INTEGER_BITS = 2000
# Python reads at most 4300 digits by default (since 3.10.7), the sign aside.
# The bound is that, whatever the running Python's limit, so that the same
# document gives the same bytes, or the same refusal, everywhere.
_TOO_LONG = 10**4300


def _readable(value: int) -> bool:
    """Whether this integer, written, reads back on any Python: it has at
    most 4300 digits, and the running Python can write it."""
    if value.bit_length() <= _SHORT_INTEGER_BITS:
        return True
    if not -_TOO_LONG < value < _TOO_LONG:
        return False
    try:
        str(value)
    except ValueError:  # longer than the running Python's limit, set lower
        return False
    return True


def _value(value: Any, parent: str, key: str | int) -> Any:
    """`value` as written: text in NFC, objects in their own order. Raises
    ValueError, naming the place, for a value JSON can't hold, or one nested
    deeper than the reader reads."""
    if isinstance(value, str):
        return nfc_text(value)
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        raise ValueError(
            f"{pointer_to(parent, key)}: {value!r} can't be written: JSON has no"
            " NaN or infinity"
        )
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if _readable(value):
            return value
        raise ValueError(f"{pointer_to(parent, key)}: an integer too long to read back")
    place = pointer_to(parent, key)
    if isinstance(value, (dict, list, tuple)) and place.count("/") >= MAX_DEPTH:
        # As the reader counts: the top level is the first level, and an
        # object or a list n keys below it the (n + 1)th. This also stops a
        # value that holds itself.
        raise ValueError(f"{place}: nested more than {MAX_DEPTH} levels deep")
    if isinstance(value, dict):
        return {k: _value(v, place, k) for k, v in nfc_object(value, place).items()}
    if isinstance(value, (list, tuple)):
        return [_value(item, place, index) for index, item in enumerate(value)]
    raise ValueError(f"{place}: a {type(value).__name__} can't be written in JSON")


def _object(
    value: dict[str, Any],
    shape: Shape,
    place: str,
    writers: Mapping[str, Writer] | None = None,
) -> dict[str, Any]:
    """An object as written: its known keys in order, then the others, in
    code-point order. A known key that isn't always written is left out when
    it equals its default, by type and value (0 isn't 0.0), or, without one,
    when it is None. A default derived from another value, such as
    `pre_start`'s from `start`, isn't one: such a key is written whenever it
    is set, whatever value it would derive."""
    values = nfc_object(value, place)
    always, defaults, empty = shape.always, shape.defaults, shape.left_out_empty
    written: dict[str, Any] = {}
    found = 0
    for key in shape.keys:
        if key not in values:
            continue
        found += 1
        item = values[key]
        kind = type(item)
        if key not in always:
            if item is None:
                continue  # None is a missing key, as a null in a file is
            if key in defaults:
                default = defaults[key]
                if kind is type(default) and item == default:
                    continue
            elif key in empty:
                if kind is dict and not item:
                    continue
        writer = writers.get(key) if writers else None
        if writer is not None:
            written[key] = writer(item, place, key)
        else:
            written[key] = _value(item, place, key)
    if found < len(values):
        known = shape.known
        for key in sorted(key for key in values if key not in known):
            written[key] = _value(values[key], place, key)
    return written


def _merged(
    place: str,
    fields: tuple[str, dict[str, Any]],
    *parts: tuple[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """An entry's keys, from the places the API holds them: its fields, then
    `attrs` and `extra`, each named, which may not share a key. The fields
    are a new dict, which the others are added to rather than copied."""
    fields_name, merged = fields
    for index, (name, part) in enumerate(parts):
        if not merged.keys().isdisjoint(part):
            key = next(key for key in part if key in merged)
            earlier = next((n for n, p in parts[:index] if key in p), fields_name)
            raise ValueError(
                f"{pointer_to(place, key)}: set both in {earlier} and in {name}"
            )
        merged.update(part)
    return merged


def _entries(entries: dict[str, Any], place: str) -> list[tuple[str, Any]]:
    """Timelines, components or scores in id order, each checked to be under its own id."""
    for given, entry in entries.items():
        if getattr(entry, "id", given) != given:
            raise ValueError(f"{pointer_to(place, given)}: holds the id {entry.id!r}")
    return sorted(nfc_object(entries, place).items(), key=itemgetter(0))


def _spelling(to_file: Callable[[Kind], str], kind: Kind, place: str) -> str:
    try:
        return to_file(kind)
    except ValueError as error:
        raise ValueError(f"{place}/kind: {error}") from None


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
# A beat's measure mark is always written, even empty: it is what makes a
# downbeat. Its number, label and source are written whenever they are set,
# like any key without a default, whatever the marks before it would give.
_BEAT_WRITERS: dict[str, Writer] = {
    "measure": _shaped(MEASURE_SHAPE),
    "beat_unit": _beat_unit,
}


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
    component: Component, place: str, holds: frozenset[str]
) -> dict[str, Any]:
    """A component of a timeline that holds the kinds `holds`."""
    if isinstance(component.kind, UnknownKind) and (
        component_kind_from_file(component.kind.spelling) not in holds
    ):
        # Read back as it is spelled, as an UnknownKind: of a kind the core
        # doesn't know, or of one its timeline doesn't hold.
        kind = component.kind.spelling
    else:
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
    writers = _BEAT_WRITERS if component.kind == "beat" else None
    return _object(value, shape, place, writers=writers)


def _components(
    components: dict[str, Component], place: str, holds: frozenset[str]
) -> dict[str, Any]:
    """A timeline's components, in id order."""
    return {
        key: _component(component, pointer_to(place, key), holds)
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
        if value.get(key) is not None or not at_default:
            value[key] = item
        elif key in value:
            del value[key]  # a null in the file was a missing key
    return _object(value, UNKNOWN_TIMELINE, place)


def _components_writer(holds: frozenset[str]) -> Writer:
    def write(item: Any, parent: str, key: str | int) -> Any:
        if not isinstance(item, dict):
            return _value(item, parent, key)
        return _components(item, pointer_to(parent, key), holds)

    return write


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
    holds = TIMELINE_COMPONENTS.get(timeline.kind, frozenset())
    writers: dict[str, Writer] = {"components": _components_writer(holds)}
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
    wrote, they are the file's bytes. A float that is an integer, where the
    format has an integer, is written as that integer, as the reader reads
    it (FR-051a); a document the reader would refuse is written as it is.

    Raises ValueError, naming the place as a JSON Pointer, for a value JSON
    can't hold: NaN, an infinity, an integer too long to read back, or a
    value of another type than JSON's; and for one nested deeper than the
    reader reads, as a value that holds itself is (FR-034).
    """
    return _utf8(_canonical(doc, refuse=False))


def checked_bytes(
    doc: Document, *, path: str | os.PathLike[str] | None = None
) -> bytes:
    """The bytes `write` writes: `canonical_bytes(doc)`, once checked as the
    reader checks a file. Raises `UnreadableFile`, with its place and line,
    for a document the reader would refuse; one the reader only warns about
    gives its bytes (FR-034). `path`, where they are to be written, is for
    messages."""
    return _utf8(_canonical(doc, path=path, refuse=True))


def _canonical(
    doc: Document,
    *,
    path: str | os.PathLike[str] | None = None,
    refuse: bool,
) -> str:
    """`doc`'s text, checked as the reader checks a file. The check turns
    each float that is an integer, where the format has an integer, into
    that integer. When it turned any, the text is that of the document
    reading the checked text gives: a value at its default, such as a step
    of 0 given as 0.0, is then left out, as the reader fills it in. A
    document the reader would refuse raises `UnreadableFile` with `refuse`,
    and is written as it is without."""
    content = _document(doc)
    text = _text(content)
    try:
        check(content, text, path=path)
    except UnreadableFile:
        if refuse:
            raise
        return text
    checked = _text(content)
    if checked == text:
        return text
    return _text(_document(loads(_utf8(checked))))


def _text(content: dict[str, Any]) -> str:
    return json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def new_document(*, time_unit: str = "seconds") -> Document:
    """An empty document in the current format, with a new document id (FR-035)."""
    if time_unit not in TIME_UNITS:
        units = ", ".join(TIME_UNITS)
        raise ValueError(f"time_unit must be one of {units}, not {time_unit!r}")
    return Document(
        document_id=new_id(), format_version=FORMAT_VERSION, time_unit=time_unit
    )


# The temporary files of `state.atomic_write`, `.<name>.<8 hex digits>.tmp`
# beside the file they replace: hidden on macOS and Linux, and never ending in
# `.tla`, so that they are never taken for a TiLiA file (FR-017, FR-041). A
# crash during a write may leave one behind.
TEMPORARY_PATTERN = r"^\..+\.[0-9a-f]{8}\.tmp$"
_TEMPORARY = re.compile(TEMPORARY_PATTERN)


def is_temporary(name: str) -> bool:
    """Whether a file name is one of the writer's temporary files."""
    return _TEMPORARY.fullmatch(name) is not None


class _Absent(enum.Enum):
    ABSENT = "ABSENT"

    def __repr__(self) -> str:
        return "ABSENT"


ABSENT = _Absent.ABSENT
"""`write`'s `expect` for a write that expects no file at its path."""


def fingerprint_of(doc: Document) -> str:
    """The SHA-256 of `doc`'s canonical bytes, in lower-case hexadecimal (FR-043)."""
    return hashlib.sha256(canonical_bytes(doc)).hexdigest()


def fingerprint(path: str | os.PathLike[str]) -> str:
    """The fingerprint of the file at `path`: that of its canonical bytes, so
    that its line endings, a byte-order mark or its key order don't change
    it (FR-043). Raises as `read` does."""
    return fingerprint_of(read(path))


def _found(path: str, expect: str | None = None) -> str | None:
    """The fingerprint of the file at `path`, or None when it is missing or
    can't be read. A file the core wrote holds its canonical bytes: when the
    SHA-256 of its bytes is `expect`, that is its fingerprint, and it isn't
    read as a document. Any other file is, so that a file in another form,
    such as with CRLF line endings, is still the one expected."""
    try:
        with open(path, "rb") as file:
            data = file.read()
        if expect is not None and hashlib.sha256(data).hexdigest() == expect:
            return expect
        return fingerprint_of(loads(data, path=path))
    except (OSError, ValueError):  # UnreadableFile is a ValueError
        return None


def rebase_paths(doc: Document, folder: str | os.PathLike[str]) -> Document:
    """`doc` with its media's path and its PDF timelines' paths as a file in
    `folder` stores them (FR-003, FR-033), with "/".

    An absolute path becomes relative to `folder` wherever a relative path
    exists, so not on another drive on Windows. When `folder` isn't the one
    `doc` was read from, a relative path is resolved against that one and
    made relative to `folder`, or absolute where no relative path exists. An
    empty path, a URL, a path of the other system's form, and a relative
    path in a document read from nowhere, whose base is unknown, are kept as
    they are. `doc` isn't changed: when a path changes, a copy is returned,
    sharing with `doc` what didn't change."""
    folder = os.path.abspath(folder)
    origin = (
        None if doc.origin is None else os.path.dirname(os.path.abspath(doc.origin))
    )
    if origin is not None and os.path.normcase(origin) == os.path.normcase(folder):
        origin = None  # its relative paths are already relative to `folder`
    media_path = _rebased(doc.media_path, origin, folder)
    changed: dict[str, Timeline] = {}
    if isinstance(doc.timelines, dict):
        for key, timeline in doc.timelines.items():
            if not (
                isinstance(timeline, Timeline)
                and timeline.kind == "pdf"
                and isinstance(timeline.attrs, dict)
            ):
                continue
            path = timeline.attrs.get("path")
            rebased = _rebased(path, origin, folder)
            if rebased != path:
                attrs = {**timeline.attrs, "path": rebased}
                changed[key] = dataclasses.replace(timeline, attrs=attrs)
    if media_path == doc.media_path and not changed:
        return doc
    timelines = {**doc.timelines, **changed} if changed else doc.timelines
    return dataclasses.replace(doc, media_path=media_path, timelines=timelines)


def _rebased(stored: Any, origin: str | None, folder: str) -> Any:
    """`stored` as a file in `folder` stores it; `origin` is the folder its
    relative paths are relative to when that isn't `folder`, or None."""
    if not isinstance(stored, str):
        return stored  # for the check to refuse
    if absolute_form(stored) == SYSTEM:
        relative = relative_path(stored, folder, SYSTEM)
        return stored if relative is None else relative
    if origin is not None and is_relative(stored):
        found = os.path.normpath(os.path.join(origin, stored))
        relative = relative_path(found, folder, SYSTEM)
        return with_slashes(found, SYSTEM) if relative is None else relative
    return stored


def write(
    path: str | os.PathLike[str],
    doc: Document,
    *,
    expect: str | _Absent | None = None,
) -> str:
    """Write `doc` to `path` atomically, and return the fingerprint of the
    bytes written (FR-040–FR-044).

    `expect` is the fingerprint of the version the caller read, `ABSENT` when
    no file may be at `path`, or None for no check. When the file on disk is
    something else, or is missing, or can't be read, `FileChanged` is raised
    and nothing is written (FR-042). The check and the rename are two steps:
    a change between them isn't caught.

    The media's path and PDF timelines' paths are written relative to the
    folder of `path` wherever a relative path exists, recomputed when it
    isn't the folder `doc` was read from (`rebase_paths`, FR-033); `doc`
    itself isn't changed. Its other bytes are `canonical_bytes(doc)`'s.

    A link stays a link, and the file it names is written; the file keeps its
    permission bits. A folder is refused with `IsADirectoryError`, and a
    read-only file with `PermissionError`, as the system refuses to open
    either for writing. On Windows, a file another program holds open, or
    whose new temporary file it holds open, is retried for about a second,
    then refused with `FileInUse`. A document the reader would refuse raises
    `UnreadableFile`, with its place and line, and one `canonical_bytes`
    refuses raises its `ValueError`, both before anything is read or written
    (FR-034). Any other failure raises the system's `OSError`. Whenever a
    write fails, the file is as it was.
    """
    target = os.path.realpath(path)
    # Relative to the folder of `path` as given, links not followed, which is
    # the folder the reader resolves the file's paths against.
    doc = rebase_paths(doc, os.path.dirname(os.path.abspath(path)))
    data = checked_bytes(doc, path=path)
    if expect is ABSENT:
        if os.path.lexists(target):
            raise FileChanged(path, None, _found(target))
    elif expect is not None:
        found = _found(target, expect)
        if found != expect:
            raise FileChanged(path, expect, found)
    if os.path.isdir(target):
        # On Windows, the rename would be refused as if the file were held open.
        raise IsADirectoryError(
            errno.EISDIR, os.strerror(errno.EISDIR), os.fspath(path)
        )
    if os.path.exists(target) and not os.access(target, os.W_OK):
        # The rename would replace it on macOS and Linux.
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), os.fspath(path))
    try:
        atomic_write(Path(target), data)
    except PermissionError as error:
        if _held_open(error):
            raise FileInUse(path) from error
        raise
    return hashlib.sha256(data).hexdigest()


# Windows' errors for a rename refused because another program holds a file
# open: ERROR_ACCESS_DENIED when it is the file replaced,
# ERROR_SHARING_VIOLATION when it is the new temporary file, which a virus
# scanner or an indexer may open as soon as it is written.
_HELD_OPEN = frozenset({5, 32})


def _held_open(error: PermissionError) -> bool:
    """Whether `atomic_write`'s rename failed, after its retry, because
    another program holds the file or the temporary file open. A read-only
    file and a folder are refused before the rename."""
    renamed = error.filename2 is not None  # os.replace names both files
    return renamed and getattr(error, "winerror", None) in _HELD_OPEN
