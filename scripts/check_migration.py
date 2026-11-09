"""Check a migrated copy of a corpus against the original (SC-002).

    python scripts/check_migration.py SOURCE COPY

COPY has to be a copy of SOURCE: it is migrated in place. Never give an original
corpus as COPY. SOURCE is only read. tilia-core has to be installed, for example
with `uv run --package tilia-core python scripts/check_migration.py SOURCE COPY`.

The script migrates COPY with `migrate_folder(apply=True)`, which does nothing to
a file already migrated, then checks each file:

- it reads back, without an error;
- it holds what SOURCE's file holds when read through the migration;
- an old file's copy is byte for byte what the migration gives, and a second read
  and write leaves it byte-identical. A file already in the current format is left
  alone by the migration, whatever its layout, so its bytes aren't checked, and
  the second read and write goes to a file beside it, so that it stays as it was;
- an old file's copy is compared with the original's own JSON, per timeline and
  per component. Reading both through the migration couldn't show what the
  migration itself gets wrong: both sides would have it. The new ids hold what
  they come from, so that each component is compared with its own original, and
  everything it holds, but for what the migration changes on purpose, which is
  named below with what says so. A media or PDF path is compared with what the
  migration should make of it, relative to the file's folder.

It prints a report, whose first lines say whether chords and keys were checked and
which files were left out, and exits with 0 when there is no difference, 1 when
there is any, and 2 when it was given something it won't check, having written
nothing. What opens with a warning isn't a difference: the report prints it. Nor
is a beat or a beat unit the migration drops, as TiLiA drops it when it opens the
file, with its warning: the report lists it, and without its warning it is one.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import ntpath
import os
import posixpath
import re
import secrets
import sys
import uuid
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from tilia_core import tla
from tilia_core.importers import harmony_available
from tilia_core.timemap import units as beat_units
from tilia_core.tla.folder import corpus_files
from tilia_core.tla.ids import migrated_id
from tilia_core.tla.layout import (
    COMPONENT_SHAPES,
    RANGE_ROW_SHAPE,
    TIMELINE_SHAPES,
    UNKNOWN_COMPONENT,
    Shape,
    nfc_value,
)
from tilia_core.tla.media_files import YOUTUBE_URL
from tilia_core.tla.migrate.old import TILIA_0_7_HEIGHTS, renames_display_position
from tilia_core.tla.model import (
    TIMELINE_COMPONENTS,
    component_kind_from_file,
    timeline_kind_from_file,
)

# What reading an old file and reading its migrated copy differ in on purpose: the
# version it was read from, the warnings of a migration done since, and where it
# was read from.
NOT_CONTENT = frozenset({"format_version", "warnings", "origin"})
LEGACY_SCORE = "svg-osmd-legacy"
SHOWN_PER_FILE = 20
SHORT = 100
SECOND_WRITE_CHANGED = "a second read and write changed its bytes"

# What the migration changes on purpose, and so what the comparison with an old
# file's own JSON leaves out or expects changed; everything else carries over
# (FR-025). The contract is WP3's contracts/migration.md.
#
# An old file's top level: `file_path` and `timelines_hash` are dropped (FR-021) and
# `version` replaced (FR-002). The others here are compared one by one, and any other
# is a key the core doesn't know, kept as it is (FR-015).
NOT_UNKNOWN_AT_THE_TOP = frozenset(
    {
        "file_path",
        "timelines_hash",
        "version",
        "app_name",
        "media_path",
        "media_metadata",
        "timelines",
    }
)
STORED_HASHES = ("hash", "components_hash")  # dropped everywhere (FR-021)
# A hierarchy's formal type and function are dropped (FR-021), and its parent and
# children, which TiLiA computes from levels and times, as TiLiA 0.7 drops them
# when it opens a file (contract, step 1). So a migrated hierarchy has no link to
# another: those times and levels are compared, and `joined_right` is what follows
# the new ids.
NOT_KEPT_IN_HIERARCHIES = ("parent", "children", "formal_type", "formal_function")
# A beat timeline's lists by measure become marks on its beats (FR-082): compared
# through the measure table the reader builds from those marks.
LISTS_BY_MEASURE = ("beats_in_measure", "measure_numbers", "measures_to_force_display")
BEAT_UNIT = "BEAT_UNIT"  # desktop#621's: moves onto the beat it names (FR-082, FR-083)
# A comment's words, as the migration tells them. A word that starts with one of
# the marks and has a value moves to the component's metadata (FR-021).
SEPARATORS = re.compile(r"[\s|]+")
TAG = "tag="
GEN = "gen="
# The media length as text, which the migration reads (contract, step 2): in ASCII,
# with around it the spaces float() strips, which \s is but for U+001C to U+001F.
NUMBER = re.compile(
    r"[^\S\x1c-\x1f]*[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
    r"[^\S\x1c-\x1f]*"
)
PATH_SEPARATORS = re.compile(r"[\\/]")
# An absolute path of Windows' form, whichever system reads it: a drive and its
# root, or a share's two slashes of one kind (contract, *Media paths*).
WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/]|//|\\\\")
URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]+://")  # a scheme of two characters or more
HERE = "windows" if os.name == "nt" else "posix"
PATHS = {"windows": ntpath, "posix": posixpath}
# How far past the end of the media TiLiA keeps a beat when it opens a file.
BEAT_TOLERANCE = 2


def plain(value: Any) -> Any:
    """`value`, a document or a part of one, as dicts, lists and values."""
    if dataclasses.is_dataclass(value):
        return {
            field.name: plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if field.compare and field.name not in NOT_CONTENT
        }
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= SHORT else f"{text[:SHORT]}... ({len(text)} characters)"


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def identical(one: Any, other: Any) -> bool:
    """A number of another type isn't identical, as it isn't in a file: 1 and 1.0."""
    return type(one) is type(other) and one == other


def by_value(one: Any, other: Any) -> bool:
    """Numbers by value: 1 and 1.0 are alike, and true and 1 aren't. The migration
    leaves out a number equal to its default, by value, and the check makes an
    integer of a 1.0 where the format says integer."""
    return (
        one == other if is_number(one) and is_number(other) else identical(one, other)
    )


def differences(
    before: Any,
    after: Any,
    place: str = "",
    same: Callable[[Any, Any], bool] = identical,
) -> Iterator[str]:
    """How `after` differs from `before`, both plain, each with its place."""
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys(), key=str):
            at = f"{place}/{key}"
            if key not in after:
                yield f"{at}: missing from the copy, was {short(before[key])}"
            elif key not in before:
                yield f"{at}: only in the copy, is {short(after[key])}"
            else:
                yield from differences(before[key], after[key], at, same)
    elif isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            yield f"{place}: {len(before)} items in the original, {len(after)} here"
        for index, (one, other) in enumerate(zip(before, after, strict=False)):
            yield from differences(one, other, f"{place}/{index}", same)
    elif not same(before, after):
        yield f"{place}: {short(before)} in the original, {short(after)} in the copy"


def kind_of(kind: Any) -> str:
    """A timeline's or a component's kind, however a file spells it."""
    return str(getattr(kind, "spelling", kind)).lower().removesuffix("_timeline")


def as_read(value: Mapping[str, Any], shape: Shape) -> dict[str, Any]:
    """An object of an old file as the reader holds it once migrated, its text in
    NFC: a null a missing key, what is missing its default."""
    kept = {
        key: item
        for key, item in nfc_value(dict(value)).items()
        if item is not None or key not in shape.known or key in shape.always
    }
    empty = {key: {} for key in shape.left_out_empty}
    return {**shape.defaults, **empty, **kept}


def stable(new_id: str) -> int:
    """A migrated id without its time field. That holds the old id when it is an
    integer, else a position among what the migration keeps, which a dropped beat
    moves. The other bits are a hash of the document id and the old ids (FR-012), so
    they tell which old entry the id comes from, whatever its old id was."""
    return uuid.UUID(new_id).int & ((1 << 80) - 1)


def old_entry(document: tla.Document, kind: str, *old_ids: str) -> int:
    """What `stable` gives for the id migrating that old entry gives."""
    return stable(migrated_id(document.document_id, kind, *old_ids, position=0))


def pointer(*parts: str) -> str:
    """A JSON Pointer, as a warning names a place in the old file."""
    return "".join("/" + part.replace("~", "~0").replace("/", "~1") for part in parts)


class Dropped:
    """What the migration drops on purpose, as TiLiA drops it when it opens the
    file, with a warning at its place in the old file: a beat without a time,
    outside the media or at the time of another, and a beat unit on no beat kept,
    on a beat that has one, or that desktop#621 can't read (contract, *Beat
    timelines*, steps 1 and 4). The places warned about; the old media length,
    as the migration reads it; the old file's version; and what was found dropped
    so, for the report."""

    def __init__(self, warned: set[str], media_length: Any, version: str) -> None:
        self.warned = warned
        self.media_length = media_length
        self.version = version
        self.found: list[str] = []

    def check(self, place: str, at: str, why: str) -> Iterator[str]:
        """Whether a drop at `place`, `at` in the old file, has its warning: listed
        if so, else a difference."""
        if at in self.warned:
            self.found.append(f"dropped, with its warning: {place}, {why}")
        else:
            yield f"{place}: missing from the copy, {why}, without its warning"

    def beats(self, old_components: Mapping[str, Any]) -> dict[str, str]:
        """The beats of a beat timeline to drop, each with why, by old id."""
        dropped: dict[str, str] = {}
        times: set[Any] = set()
        length = self.media_length
        for key, beat in old_components.items():
            if beat.get("kind") != "BEAT":
                continue
            time = beat.get("time")
            if time is None:
                dropped[key] = "a beat without a time"
            elif is_number(time) and (
                time < 0 or (length is not None and time > length + BEAT_TOLERANCE)
            ):
                dropped[key] = f"a beat at {time!r}, outside the media"
            elif is_number(time) and time in times:
                dropped[key] = f"a beat at the time of another, {time!r}"
            elif is_number(time):
                times.add(time)
        return dropped


def comment_parts(comment: str) -> tuple[list[str], list[str], list[str]]:
    """A comment's words, its tags and its generators."""
    words: list[str] = []
    tags: list[str] = []
    generators: list[str] = []
    for word in SEPARATORS.split(comment):
        if word.startswith(TAG) and word != TAG:
            tags.append(word[len(TAG) :])
        elif word.startswith(GEN) and word != GEN:
            generators.append(word[len(GEN) :])
        elif word:
            words.append(word)
    return words, tags, generators


def as_list(value: Any) -> list[Any]:
    """A field's value as a list: no text is none."""
    if isinstance(value, list):
        return value
    return [value] if value else []


def compare_marks(expected: dict[str, Any], held: dict[str, Any]) -> None:
    """Make what is compared of a comment with marks what they leave unchanged: the
    marks move into the metadata, and the separators around them may go, so the
    comment's other words are compared, in their order, and the fields as lists:
    each `tag=` in `tags`, without repeats, and each `gen=` in `generated_by`, after
    what a hand edit put there (FR-021, contract, *Comment marks*)."""
    comment = expected.get("comments")
    if not isinstance(comment, str):
        return
    words, tags, generators = comment_parts(comment)
    if not tags and not generators:
        return
    expected["comments"] = words
    found = held.get("comments")
    if isinstance(found, str):
        held["comments"] = [word for word in SEPARATORS.split(found) if word]
    metadata = expected["metadata"]
    if tags:
        had = as_list(metadata.get("tags"))
        metadata["tags"] = had + [tag for tag in dict.fromkeys(tags) if tag not in had]
        held["metadata"]["tags"] = as_list(held["metadata"].get("tags"))
    if generators:
        metadata["generated_by"] = as_list(metadata.get("generated_by")) + generators
        held["metadata"]["generated_by"] = as_list(held["metadata"].get("generated_by"))


def equals_its_base(attrs: Mapping[str, Any], derived: str, base: str) -> bool:
    one, other = attrs.get(derived), attrs.get(base)
    return is_number(one) and is_number(other) and one == other


def expected_attrs(
    kind: str, old: Mapping[str, Any], new_ids: Mapping[str, str]
) -> dict[str, Any]:
    """What a component of a kind its timeline holds should hold once migrated."""
    attrs = {key: value for key, value in old.items() if key not in ("hash", "kind")}
    if kind == "hierarchy":
        for name in NOT_KEPT_IN_HIERARCHIES:
            attrs.pop(name, None)
    if kind in ("hierarchy", "range"):
        # Left unset where they equal what they default to (contract, step 2).
        for derived, base in (("pre_start", "start"), ("post_end", "end")):
            if equals_its_base(attrs, derived, base):
                del attrs[derived]
    if kind == "harmony" and attrs.get("display_mode") == "chord":
        attrs["display_mode"] = "letter"  # TiLiA 0.5's name for it (contract, step 2)
    if kind == "clef" and isinstance(attrs.get("icon"), str):
        # As TiLiA 0.7 reads it (contract, step 1).
        attrs["icon"] = attrs["icon"].removesuffix(".svg")
    joined = attrs.get("joined_right")
    if kind == "range" and joined is not None:
        attrs["joined_right"] = new_ids.get(str(joined), joined)  # FR-021
    return as_read(attrs, COMPONENT_SHAPES[kind])


def component_differences(
    timeline_kind: str,
    old_components: Mapping[str, Any],
    components: Mapping[str, tla.Component],
    place: str,
) -> Iterator[str]:
    """How the components matched with `old_components` differ from them, each from
    its own original, a beat's measure and beat unit but for those compared with its
    timeline's lists and units."""
    new_ids = {key: component.id for key, component in components.items()}
    for key, component in components.items():
        old = old_components[key]
        at = f"{place}/{key}"
        kind = component_kind_from_file(old["kind"])
        if kind_of(component.kind) != kind_of(old["kind"]):
            yield (
                f"{at}/kind: {short(kind_of(old['kind']))} in the original,"
                f" {short(kind_of(component.kind))} in the copy"
            )
        held = {
            "metadata": dict(component.metadata),
            **component.attrs,
            **component.extra,
        }
        if kind in TIMELINE_COMPONENTS[timeline_kind]:
            expected = expected_attrs(kind, old, new_ids)
            if "comments" in COMPONENT_SHAPES[kind].known:
                compare_marks(expected, held)
            if kind == "beat":
                held.pop("measure", None)
                held.pop("beat_unit", None)
        else:
            # Kept as it is, but for its stored hash (FR-015).
            kept = {k: v for k, v in old.items() if k not in ("hash", "kind")}
            expected = as_read(kept, UNKNOWN_COMPONENT)
        yield from differences(expected, held, at, by_value)


def whole_numbers(value: Any, minimum: int | None = None) -> list[int]:
    """A list by measure as far as TiLiA can read it."""
    numbers: list[int] = []
    for item in value if isinstance(value, list) else []:
        whole = int(item) if is_number(item) and item == int(item) else None
        if whole is None or (minimum is not None and whole < minimum):
            break
        numbers.append(whole)
    return numbers


def measure_differences(
    old: Mapping[str, Any], timeline: tla.Timeline, place: str
) -> Iterator[str]:
    """How a beat timeline's measure table differs from its old lists by measure:
    each measure they list with its number, its beats and whether its number is
    always shown. TiLiA fits the lists to the beats, adding measures after them and
    taking measures off the end (FR-082), so a last measure may hold more or fewer
    beats than listed; what it makes of the rest isn't in the old file to compare."""
    rows = timeline.measures.rows
    beats = sum(1 for one in timeline.components.values() if one.kind == "beat")
    counts = whole_numbers(old.get("beats_in_measure"), minimum=1)
    numbers = whole_numbers(old.get("measure_numbers"))
    listed = min(len(counts), len(numbers))
    fits = sum(counts) == beats and listed == len(counts)
    start = 0
    for index in range(listed):
        start += counts[index]
        if start > beats:
            break
        at = f"{place}/measures/{index}"
        if index >= len(rows):
            yield f"{at}: missing from the copy, was measure {numbers[index]}"
            continue
        row = rows[index]
        if row.number != numbers[index]:
            yield (
                f"{at}/number: {numbers[index]} in the original,"
                f" {row.number} in the copy"
            )
        if (index < listed - 1 or fits) and len(row.beats) != counts[index]:
            yield (
                f"{at}/beats: {counts[index]} in the original,"
                f" {len(row.beats)} in the copy"
            )
    forced = whole_numbers(old.get("measures_to_force_display"))
    expected = {index for index in forced if 0 <= index < len(rows)}
    shown = {index for index, row in enumerate(rows) if row.force_display}
    for index in sorted(expected ^ shown):
        was = index in expected
        yield (
            f"{place}/measures/{index}/force_display: {was} in the original,"
            f" {not was} in the copy"
        )


def beat_unit_differences(
    key_of_timeline: str,
    old_components: Mapping[str, Any],
    components: Mapping[str, tla.Component],
    place: str,
    dropped: Dropped,
) -> Iterator[str]:
    """How the beat units on a timeline's beats differ from its old ones, each of
    them on the beat it names, or T12's default on the first beat, assumed, when it
    has none (FR-083). One the migration drops, as TiLiA drops it when it opens the
    file, is listed with its warning, and is a difference without one."""
    units: dict[str, dict[str, Any]] = {}
    for key, old in old_components.items():
        if old.get("kind") != BEAT_UNIT:
            continue
        named = old.get("beat_id")
        named = str(named) if is_number(named) else named
        text = old.get("units", beat_units.DEFAULT_UNITS)
        parsed = beat_units.parse_units(text) if isinstance(text, str) else None
        denominator = old.get("denominator", beat_units.DEFAULT_DENOMINATOR)
        why = None
        if named not in components:
            why = f"a beat unit naming {named!r}, which isn't a beat kept"
        elif named in units:
            why = f"a second beat unit on the beat {named!r}"
        elif parsed is None or not parsed.is_valid:
            why = f"a beat unit with the units {text!r}"
        elif not beat_units.validate_denominator(denominator):
            why = f"a beat unit with the denominator {denominator!r}"
        if why is not None:
            at = pointer("timelines", key_of_timeline, "components", key)
            yield from dropped.check(f"{place}/{key}", at, why)
            continue
        units[named] = {
            "denominator": denominator,
            "units": beat_units.format_units(parsed.units),
            "assumed": bool(old.get("assumed")),
        }
    beats = {k: c for k, c in components.items() if c.kind == "beat"}
    if beats and not units:
        first = min(beats, key=lambda key: beats[key].attrs["time"])
        units[first] = {
            "denominator": beat_units.DEFAULT_DENOMINATOR,
            "units": beat_units.DEFAULT_UNITS,
            "assumed": True,
        }
    for key, beat in beats.items():
        yield from differences(
            {"beat_unit": units.get(key)},
            {"beat_unit": beat.attrs.get("beat_unit")},
            f"{place}/{key}",
            by_value,
        )


def legacy_score_differences(
    key: str,
    old: Mapping[str, Any],
    timeline: tla.Timeline,
    document: tla.Document,
    scores: dict[int, tla.Score],
    place: str,
) -> Iterator[str]:
    """How a score timeline's legacy score differs from its SVG and beat positions,
    which have moved there (FR-022). One without an SVG has no score. What it finds
    leaves `scores`."""
    named = timeline.attrs.get("score")
    if not old.get("svg_data"):
        if named is not None:
            yield f"{place}/score: only in the copy, is {short(named)}"
        return
    score = scores.pop(old_entry(document, "score", key), None)
    if score is None or score.id != named:
        yield f"{place}/score: missing from the copy, was its SVG"
        return
    svg = tla.Score(id="", format=LEGACY_SCORE)
    svg.text = old["svg_data"]
    # Of two keys of one value, the last counts, as TiLiA reads them.
    positions = {float(k): x for k, x in (old.get("viewer_beat_x") or {}).items()}
    expected = {
        "format": LEGACY_SCORE,
        "lines": svg.lines,
        "beat_x": [[position, positions[position]] for position in sorted(positions)],
    }
    held = {
        "format": score.format,
        "lines": score.lines,
        "beat_x": score.extra.get("beat_x"),
    }
    yield from differences(expected, held, f"{place}/score", by_value)


def file_name(path: Any) -> Any:
    """The last name of a stored path, which making it relative doesn't change."""
    return PATH_SEPARATORS.split(nfc_value(path))[-1] if isinstance(path, str) else path


def path_form(path: str) -> str | None:
    """`windows` or `posix` for an absolute path of that system's form, whichever
    system reads it; None for anything else."""
    if WINDOWS_PATH.match(path):
        return "windows"
    return "posix" if path.startswith("/") else None


def as_migrated(stored: Any, file_path: Any, folder: str, media: bool) -> Any:
    """What the migration should store for an old file's media path (`media`) or a
    PDF timeline's path, for a file in `folder` last saved at `file_path` (FR-021,
    Q4, contract, *Media paths*): relative to `folder`, starting from where TiLiA
    would find it now: where it is, if it is on this computer; else beside
    `file_path`, by that path's own system; else beside the file. Absolute where no
    relative path exists; a URL, or a path written relative by hand, as it is; a
    YouTube link without a scheme with one. None for a path of this system's form
    and a `file_path` of the other's, which reading keeps absolute and the writer
    writes relative: that waits on TimeLineAnnotator/project-management#530 (a
    media path that reading keeps absolute), and only its file's name is
    compared."""
    if not isinstance(stored, str) or not stored or URL.match(stored):
        return stored
    if media and YOUTUBE_URL.match(stored):
        return f"https:{stored}" if stored.startswith("//") else f"https://{stored}"
    form = path_form(stored)
    if form is None:
        return stored
    paths = PATHS[form]
    saved = file_path if isinstance(file_path, str) and not URL.match(file_path) else ""
    saved_form = path_form(saved) if saved else None
    if form == HERE and os.path.isfile(stored):
        base: str | None = folder
    elif saved_form is None:
        base = folder if form == HERE else None
    elif saved_form == form:
        base = paths.dirname(saved)
    elif form == HERE:
        return None
    else:
        base = None
    relative = stored
    if base is not None:
        try:
            relative = paths.relpath(stored, base)
        except ValueError:  # on another drive or share
            pass
    return relative.replace("\\", "/") if form == "windows" else relative


def path_differences(
    stored: Any, file_path: Any, held: Any, folder: str, place: str, media: bool
) -> Iterator[str]:
    """How a migrated media or PDF path differs from what the old one should be."""
    expected = as_migrated(stored, file_path, folder, media)
    if expected is None:
        stored, held = file_name(stored), file_name(held)
    else:
        stored = nfc_value(expected)
    yield from differences(stored, held, place, by_value)


def as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return "" if value is None else json.dumps(value, ensure_ascii=False)


def expected_settings(kind: str, old: Mapping[str, Any]) -> dict[str, Any]:
    """A timeline's settings, its kind's own included, as it should hold them once
    migrated."""
    settings = {
        key: value
        for key, value in old.items()
        if key not in (*STORED_HASHES, "kind", "components")
    }
    height = settings.get("height")
    if kind in TILIA_0_7_HEIGHTS and (
        height is None or (is_number(height) and height == 0)
    ):
        settings["height"] = TILIA_0_7_HEIGHTS[kind]  # contract, step 1
    if kind == "beat":
        for name in LISTS_BY_MEASURE:
            settings.pop(name, None)
        pattern = settings.get("beat_pattern")
        if isinstance(pattern, list):  # FR-084
            settings["beat_pattern"] = " ".join(as_text(bar) for bar in pattern)
        if settings.get("show_time_signatures") is None:  # FR-084
            settings["show_time_signatures"] = False
        settings["measure_source"] = "unknown"  # FR-082
    if kind == "score":
        # Moved to its legacy score (FR-022), which is compared by itself. With no
        # SVG, beat positions stay: only a hand edit gives them.
        svg = settings.pop("svg_data", None)
        if svg or settings.get("viewer_beat_x") in (None, {}):
            settings.pop("viewer_beat_x", None)
    expected = as_read(settings, TIMELINE_SHAPES[kind])
    if kind == "score":
        expected.pop("score", None)
    if kind == "pdf":
        expected.pop("path", None)  # relative, as the media's (FR-021): compared apart
    if kind == "range" and isinstance(expected.get("rows"), list):
        # Rows keep their ids (contract, step 2), and the reader fills them in.
        expected["rows"] = [
            as_read(row, RANGE_ROW_SHAPE) if isinstance(row, dict) else row
            for row in expected["rows"]
        ]
    return expected


def timeline_differences(
    key: str,
    old: Mapping[str, Any],
    timeline: tla.Timeline,
    document: tla.Document,
    scores: dict[int, tla.Score],
    file_path: Any,
    dropped: Dropped,
) -> Iterator[str]:
    """How a migrated timeline differs from its old one: its kind, its settings and
    each of its components."""
    place = f"/timelines/{key}"
    if kind_of(timeline.kind) != kind_of(old["kind"]):
        yield (
            f"{place}/kind: {short(kind_of(old['kind']))} in the original,"
            f" {short(kind_of(timeline.kind))} in the copy"
        )
    if renames_display_position(dropped.version) and "display_position" in old:
        # From 0-based to 1-based (contract, step 1).
        old = {**old, "ordinal": old["display_position"] + 1}
        old = {k: v for k, v in old.items() if k != "display_position"}
    kind = timeline_kind_from_file(old["kind"])
    if isinstance(kind, tla.UnknownKind):
        # Kept as it is, but for its stored hashes, its components' too (FR-015).
        kept = {k: v for k, v in old.items() if k not in (*STORED_HASHES, "kind")}
        if isinstance(kept.get("components"), dict):
            kept["components"] = {
                name: {k: v for k, v in one.items() if k != "hash"}
                if isinstance(one, dict)
                else one
                for name, one in kept["components"].items()
            }
        raw = {k: v for k, v in (timeline.raw or {}).items() if k != "kind"}
        yield from differences(nfc_value(kept), raw, place, by_value)
        return
    held = {
        "name": timeline.name,
        "ordinal": timeline.ordinal,
        "metadata": timeline.metadata,
        **timeline.attrs,
        **timeline.extra,
    }
    if kind == "score":
        held.pop("score", None)
    if kind == "pdf":
        path = held.pop("path", None)
        folder = str(document.origin.parent) if document.origin else ""
        yield from path_differences(
            old.get("path"), file_path, path, folder, f"{place}/path", media=False
        )
    yield from differences(expected_settings(kind, old), held, place, by_value)

    # AudioWave's amplitude bars are computed from the media, and aren't stored
    # (contract, step 2): one of its components is only in the copy.
    old_components = {} if kind == "audiowave" else old["components"]
    remaining = {stable(new): one for new, one in timeline.components.items()}
    components: dict[str, tla.Component] = {}
    place = f"{place}/components"
    to_drop = dropped.beats(old_components) if kind == "beat" else {}
    for name, component in old_components.items():
        if kind == "beat" and component.get("kind") == BEAT_UNIT:
            continue
        found = remaining.pop(old_entry(document, "component", key, name), None)
        if found is not None:
            components[name] = found
        elif name in to_drop:
            at = pointer("timelines", key, "components", name)
            yield from dropped.check(f"{place}/{name}", at, to_drop[name])
        else:
            yield f"{place}/{name}: missing from the copy, was {short(component)}"
    for one in remaining.values():
        yield f"{place}/{one.id}: only in the copy, is a {kind_of(one.kind)}"
    yield from component_differences(kind, old_components, components, place)
    if kind == "beat":
        yield from measure_differences(old, timeline, f"/timelines/{key}")
        yield from beat_unit_differences(
            key, old_components, components, place, dropped
        )
    if kind == "score":
        yield from legacy_score_differences(
            key, old, timeline, document, scores, f"/timelines/{key}"
        )


def as_field(value: Any) -> str | list[str]:
    """A metadata value as the migration writes it: text, or a list of texts, or
    JSON's text of what holds an object or a list (contract, step 2)."""
    if isinstance(value, list) and not any(
        isinstance(item, (dict, list)) for item in value
    ):
        return [as_text(item) for item in value]
    return as_text(value)


def as_media_length(value: Any) -> Any:
    """A number above zero, also one written as text; none otherwise (FR-021)."""
    if isinstance(value, str) and NUMBER.fullmatch(value):
        value = float(value)
    if not is_number(value) or (isinstance(value, float) and not math.isfinite(value)):
        return None
    return value if value > 0 else None


def against_old_file(
    content: Mapping[str, Any], document: tla.Document, dropped: Dropped
) -> Iterator[str]:
    """How `document`, a migrated file, differs from the old file's own JSON: what
    its top level holds, then each timeline and each component against its own
    original. Each is found through its id, so that what is on another timeline, or
    on another component of its timeline, is a difference. What the migration drops
    on purpose, with its warning, goes in `dropped`."""
    metadata = dict(content.get("media_metadata", {}))
    length = metadata.pop("media length", None)
    expected_metadata = nfc_value({k: as_field(v) for k, v in metadata.items()})
    expected = {
        "app_name": content.get("app_name", "TiLiA"),
        "time_unit": "seconds",  # FR-021
        "media/length": as_media_length(length),
        "metadata": expected_metadata,
        **{k: v for k, v in content.items() if k not in NOT_UNKNOWN_AT_THE_TOP},
    }
    held = {
        "app_name": document.app_name,
        "time_unit": document.time_unit,
        "media/length": document.media_length,
        "metadata": document.metadata,
        **document.extra,
    }
    yield from differences(nfc_value(expected), held, "", by_value)
    if list(expected_metadata) != list(document.metadata):
        yield (
            f"/metadata: in the order {short(list(expected_metadata))} in the"
            f" original, {short(list(document.metadata))} in the copy"
        )
    file_path = content.get("file_path")
    folder = str(document.origin.parent) if document.origin else ""
    yield from path_differences(
        content.get("media_path", ""),
        file_path,
        document.media_path,
        folder,
        "/media/path",
        media=True,
    )
    timelines = {stable(new): one for new, one in document.timelines.items()}
    scores = {stable(new): one for new, one in document.scores.items()}
    for key, old in content["timelines"].items():
        timeline = timelines.pop(old_entry(document, "timeline", key), None)
        if timeline is None:
            yield (
                f"/timelines/{key}: missing from the copy,"
                f" was a {kind_of(old['kind'])} timeline"
            )
        else:
            yield from timeline_differences(
                key, old, timeline, document, scores, file_path, dropped
            )
    for timeline in timelines.values():
        yield (
            f"/timelines/{timeline.id}: only in the copy,"
            f" is a {kind_of(timeline.kind)} timeline"
        )
    for score in scores.values():
        yield f"/scores/{score.id}: only in the copy, is a {score.format} score"


def held_in(document: tla.Document) -> Counter[str]:
    """How many of each thing `document` holds, as a report counts them."""
    held: Counter[str] = Counter()
    for value in document.metadata.values():
        held["metadata"] += len(value) if isinstance(value, list) else 1
    held["score"] = sum(one.format == LEGACY_SCORE for one in document.scores.values())
    for timeline in document.timelines.values():
        held["timeline"] += 1
        for component in timeline.components.values():
            attrs = component.attrs
            held["component"] += 1
            held["label"] += bool(attrs.get("label"))
            held["time"] += sum(
                is_number(attrs.get(key)) for key in ("time", "start", "end")
            )
            held["colour"] += bool(attrs.get("color"))
            comment = attrs.get("comments")
            if isinstance(comment, str):
                held["comment"] += len(comment_parts(comment)[0])
            for field in ("tags", "generated_by"):
                held["mark"] += len(as_list(component.metadata.get(field)))
    return held


def tally(held: Counter[str]) -> str:
    """How many things of each category `held` has."""
    return (
        f"timelines {held['timeline']}, components {held['component']},"
        f" labels {held['label']}, times {held['time']},"
        f" colours {held['colour']}, words of comments {held['comment']},"
        f" marks {held['mark']}, metadata items {held['metadata']},"
        f" legacy scores {held['score']}"
    )


def second_write_changes(copy: Path) -> bool:
    """Whether a second read and write of `copy`, a file in the current format,
    changes what the first wrote. Both go to a hidden file beside it, since writing
    it there keeps its relative paths, and the file itself isn't written."""
    beside = copy.with_name(f".{copy.name}.{secrets.token_hex(4)}.check")
    try:
        tla.write(beside, tla.read(copy), expect=tla.ABSENT)
        first = beside.read_bytes()
        tla.write(beside, tla.read(beside), expect=tla.fingerprint(beside))
        return beside.read_bytes() != first
    finally:
        beside.unlink(missing_ok=True)


def check_file(source: Path, copy: Path) -> tuple[list[str], list[str], Counter[str]]:
    """The differences between a file of SOURCE and its migrated copy; what is worth
    saying about it and isn't one; and what the copy holds."""
    after = tla.read(copy)
    written = copy.read_bytes()
    original = source.read_bytes()
    # As if it were at the copy's place, where the copy was migrated: the media's
    # path is relative to the file's folder (FR-021).
    before = tla.loads(original, path=copy)
    found = list(differences(plain(before), plain(after)))
    notes = [f"warning: {warning}" for warning in before.warnings]
    if before.format_version == tla.FORMAT_VERSION:
        # The migration left it alone: its bytes aren't the migration's.
        if tla.canonical_bytes(after) != written:
            notes.append("not in the writer's layout: a save would change its bytes")
        if second_write_changes(copy):
            found.append(SECOND_WRITE_CHANGED)
    else:
        if not found and tla.canonical_bytes(before) != written:
            found.append("the copy isn't what the original migrates to")
        content = json.loads(original)
        dropped = Dropped(
            warned={w.place for w in before.warnings if "dropped" in w.message},
            media_length=as_media_length(
                content.get("media_metadata", {}).get("media length")
            ),
            version=content.get("version", "0.0.0"),
        )
        found.extend(against_old_file(content, after, dropped))
        notes.extend(dropped.found)
        tla.write(copy, after, expect=tla.fingerprint(copy))
        if copy.read_bytes() != written:
            found.append(SECOND_WRITE_CHANGED)
    return found, notes, held_in(after)


def is_within(inner: Path, outer: Path) -> bool:
    """Whether `inner`, a file or a folder, is `outer`, or inside it, links followed."""
    inner_path = os.path.normcase(os.path.realpath(inner))
    outer_path = os.path.normcase(os.path.realpath(outer))
    try:
        return os.path.commonpath([inner_path, outer_path]) == outer_path
    except ValueError:  # on another drive
        return False


def is_current(data: bytes) -> bool:
    try:
        return tla.loads(data).format_version == tla.FORMAT_VERSION
    except ValueError:  # UnreadableFile is a ValueError
        return False


def looks_swapped(files: dict[str, tuple[Path, Path]]) -> str | None:
    """A file already migrated in SOURCE and not in COPY, which may be the original:
    a copy migrated with `tilia migrate` is the other way round."""
    for relative, (source, copy) in files.items():
        original, copied = source.read_bytes(), copy.read_bytes()
        if original != copied and is_current(original) and not is_current(copied):
            return relative
    return None


def link_into(folder: Path, files: dict[str, tuple[Path, Path]]) -> str | None:
    """A file of COPY that is a link into `folder`. The writer keeps a link, and
    writes the file it names, so migrating it would overwrite that file. A hard link
    isn't one: the writer replaces it, and the file it shared is left as it was."""
    for relative, (_, copy) in files.items():
        if is_within(copy, folder):
            return relative
    return None


def skipped(folder: Path) -> tuple[int, int]:
    """How many files below `folder` no corpus takes: those hidden, in a hidden
    folder among them, and the others that aren't `.tla` files. As `corpus_files`,
    it doesn't follow links to folders."""
    hidden = others = 0
    for current, _, names in os.walk(folder):
        in_hidden = any(
            part.startswith(".") for part in Path(current).relative_to(folder).parts
        )
        for name in names:
            if in_hidden or name.startswith("."):
                hidden += 1
            elif not name.lower().endswith(".tla"):
                others += 1
    return hidden, others


def corpus_line(name: str, folder: Path, files: Mapping[str, Path]) -> str:
    hidden, others = skipped(folder)
    return (
        f"{name}: {len(files)} .tla files, skipped: {hidden} hidden, {others} not .tla"
    )


def chords_and_keys() -> str:
    """Whether chords and keys are checked here. A harmony's quality and inversion
    and a mode's type are checked against music21, which the `harmony` extra
    installs, and only by a core whose reader and writer check the rules, which
    is the one that has `BrokenRules`."""
    music21 = (
        "music21 is installed"
        if harmony_available()
        else "music21 isn't installed (the `harmony` extra)"
    )
    if not hasattr(tla, "BrokenRules"):
        return (
            f"{music21}, and this core doesn't check the rules when it reads and"
            " writes: chords and keys weren't checked, so a file can pass here and be"
            " refused by a core that does."
        )
    if harmony_available():
        return f"{music21}: chords and keys were checked."
    return (
        f"{music21}: chords and keys weren't checked, and this core won't write a"
        " file that holds them, so such a file is a difference here."
    )


def check(source: Path, copy: Path) -> int:
    """Check `copy` against `source`, print the report and give the exit status."""
    for folder in (source, copy):
        if not folder.is_dir():
            print(f"not a folder: {folder}", file=sys.stderr)
            return 2
    if is_within(source, copy) or is_within(copy, source):
        print(f"SOURCE and COPY overlap: {source}, {copy}", file=sys.stderr)
        return 2
    try:
        in_source = dict(corpus_files(source))
        if not in_source:
            hidden, others = skipped(source)
            print(
                f"no .tla file in SOURCE: {source}, skipped: {hidden} hidden,"
                f" {others} not .tla. Nothing was written.",
                file=sys.stderr,
            )
            return 2
        in_copy = dict(corpus_files(copy))
        print(chords_and_keys())
        print(corpus_line("SOURCE", source, in_source))
        print(corpus_line("COPY", copy, in_copy))
        only = sorted(in_source.keys() ^ in_copy.keys())
        for relative in only:
            print(
                f"{relative}: only in {'SOURCE' if relative in in_source else 'COPY'}"
            )
        if only:
            print(f"{len(only)} files aren't in both: nothing was written.")
            return 1
        files = {path: (in_source[path], in_copy[path]) for path in in_source}
        linked = link_into(source, files)
        swapped = None if linked is not None else looks_swapped(files)
    except OSError as error:
        print(error, file=sys.stderr)
        return 2
    if linked is not None:
        print(
            f"{linked} in COPY is a link into SOURCE: migrating it would overwrite"
            " the file it names. Nothing was written.",
            file=sys.stderr,
        )
        return 2
    if swapped is not None:
        print(
            f"{swapped} is migrated in SOURCE and not in COPY: are they the wrong way"
            " round? Nothing was written.",
            file=sys.stderr,
        )
        return 2
    return migrate_and_compare(copy, files)


def print_lines(lines: list[str]) -> None:
    for line in lines[:SHOWN_PER_FILE]:
        print(f"  {line}")
    if len(lines) > SHOWN_PER_FILE:
        print(f"  and {len(lines) - SHOWN_PER_FILE} more")


def migrate_and_compare(copy: Path, files: dict[str, tuple[Path, Path]]) -> int:
    """Migrate `copy`, compare each of `files`, print what was found and give the
    exit status."""
    migrated = tla.migrate_folder(copy, apply=True)
    different = len(migrated.folders_not_listed)
    total: Counter[str] = Counter()
    warnings = drops = 0
    for unlisted in migrated.folders_not_listed:
        print(f"{unlisted.path}: {unlisted.reason}")
    for result in migrated.files:
        found: list[str] = []
        notes: list[str] = []
        held: Counter[str] = Counter()
        if result.outcome not in (tla.Outcome.MIGRATED, tla.Outcome.CURRENT):
            found.append(f"{result.outcome.value}: {result.reason}")
        else:
            try:
                found, notes, held = check_file(*files[result.path])
            except Exception as error:  # an error in the core too: go on (FR-052)
                found.append(f"{type(error).__name__}: {error}")
        total.update(held)
        warnings += sum(note.startswith("warning: ") for note in notes)
        drops += sum(note.startswith("dropped, ") for note in notes)
        origin = f" (from {result.from_version})" if result.from_version else ""
        if not found:
            print(f"{result.path}{origin}: no difference: {tally(held)}")
        else:
            different += 1
            print(f"{result.path}{origin}: differences: {len(found)}")
            print_lines(found)
        print_lines(notes)
    for paths in migrated.shared_ids:
        print(f"These files share a document id: {', '.join(paths)}")
    print(f"{len(migrated.files)} files, {different} with a difference.")
    print(f"In all: {tally(total)}.")
    print(f"Warnings, which aren't differences: {warnings}.")
    print(
        f"Dropped on purpose, each with its warning, which isn't a difference: {drops}."
    )
    return 1 if different else 0


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.partition("\n")[0])
    parser.add_argument("source", type=Path, metavar="SOURCE", help="only read")
    parser.add_argument("copy", type=Path, metavar="COPY", help="migrated in place")
    args = parser.parse_args(arguments)
    # A console may not have every character of a label or a file's name.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")
    return check(args.source, args.copy)


if __name__ == "__main__":
    sys.exit(main())
