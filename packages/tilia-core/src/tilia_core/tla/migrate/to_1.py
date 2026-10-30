"""The one migration from TiLiA 0.x's format to the current format.

It runs in memory on every read of an old file; nothing is written. First
TiLiA's own migrations, and the changes TiLiA 0.7 makes to an old file when
it opens it, bring the file to TiLiA 0.7.0's shape (`old`), then this module
takes it to the current format:

- timeline kinds, which an old file may write in any letter case, are
  written in the format's spelling;
- `file_path` and the stored hashes are dropped;
- `media_path` and the media length (from `media_metadata`) become `media`,
  and the rest of `media_metadata` becomes the file's `metadata`;
- hierarchies' `formal_type` and `formal_function` are dropped, each
  non-empty value with a warning, and AudioWave timelines' amplitude bars,
  which TiLiA computes from the media, with one warning per timeline;
- a beat timeline's `beat_pattern`, a list of bar lengths, becomes text:
  `[4, 4, 3]` becomes `"4 4 3"`;
- the prototype's `tag=` and `gen=` marks in components' comments move into
  their metadata's `tags` and `generated_by` (`marks`), and are counted;
- a `pre_start` or `post_end` equal to its `start` or `end` is left unset,
  and other attributes equal to their default are left out;
- the document id is derived from that content, and the timelines and
  components get ids derived from it and from their old ids; a range's
  `joined_right` follows the new ids, rows keep theirs.

Keys and kinds the core doesn't know are kept as they are; a timeline of a
kind it doesn't know keeps its content, its components' ids included, under
a new id, without the stored hashes, its own and its components'.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any

from tilia_core.tla.errors import UnreadableFile, printable
from tilia_core.tla.ids import derived_document_id, migrated_id
from tilia_core.tla.layout import (
    COMPONENT_SHAPES,
    RANGE_ROW_SHAPE,
    TIMELINE_SHAPES,
    Shape,
    pointer_to,
)
from tilia_core.tla.migrate import marks
from tilia_core.tla.migrate import old as old_migrations
from tilia_core.tla.model import (
    TIMELINE_COMPONENTS,
    ReadWarning,
    UnknownKind,
    component_kind_from_file,
    timeline_kind_from_file,
    timeline_kind_to_file,
)

# The keys of an old file's top level that the migration reads.
_OLD_TOP_LEVEL = frozenset(
    {
        "file_path",
        "media_path",
        "media_metadata",
        "timelines",
        "timelines_hash",
        "app_name",
        "version",
    }
)
# Keys of the current format that no old file has: one that does can't be
# migrated without losing its value.
_CURRENT_ONLY = ("document_id", "time_unit", "media", "metadata", "scores")
_STORED_HASHES = ("hash", "components_hash")
_MEDIA_LENGTH = "media length"
# A number written as text, in ASCII.
_NUMBER = re.compile(r"\s*[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\s*")


@dataclass
class Migrated:
    """An old file's content in the current format, as the reader reads it,
    with `version` the old file's version; what the migration dropped or
    changed, as warnings; and the counts for a migration report."""

    content: dict[str, Any]
    warnings: list[ReadWarning] = field(default_factory=list)
    changes: dict[str, int] = field(default_factory=dict)


def migrate(
    old: dict[str, Any], *, path: str | os.PathLike[str] | None = None
) -> Migrated:
    """Migrate an old file's parsed content, which is changed in place.

    Raises `UnreadableFile`, naming the place in the old file, for a shape
    the migration can't read.
    """
    version = old.get("version", "0.0.0")
    migration = _Migration(version, path)
    migration.check(old)
    old = old_migrations.migrate(old)
    content = migration.to_current(old)
    # With the old ids still in place, the beat timelines' measures
    # (TimeLineAnnotator/project-management#181), the legacy scores
    # (TimeLineAnnotator/project-management#182) are converted here, as the
    # comments' marks (TimeLineAnnotator/project-management#180) are in
    # `to_current`, so that the document id is derived from the content they
    # give.
    #
    # A file saved again by TiLiA 0.7 without an edit gets the same id, but
    # for three changes TiLiA 0.7 makes itself, which change it (accepted in
    # TimeLineAnnotator/project-management#312): it adds a slider timeline to
    # a file without one, moves timelines of kinds it doesn't know after the
    # others and renumbers them, and clears a media path it can't find when
    # the user doesn't show it where the media is.
    document_id = derived_document_id(content)
    content = _with_new_ids(content, document_id)
    # The media's and PDF timelines' paths are made relative here, from the
    # old file's `file_path` (TimeLineAnnotator/project-management#176).
    content["document_id"] = document_id
    return Migrated(content, migration.warnings, migration.changes)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _equal_numbers(value: Any, other: Any) -> bool:
    return _is_number(value) and _is_number(other) and value == other


def _same(value: Any, default: Any) -> bool:
    """Whether `value` is `default`, numbers by value: 1.0 is 1, true isn't."""
    if _is_number(value) and _is_number(default):
        return value == default
    return type(value) is type(default) and value == default


def _without_defaults(value: dict[str, Any], shape: Shape) -> dict[str, Any]:
    """An entry without the attributes that equal their default, as the
    writer leaves them out; numbers by value."""
    return {
        key: item
        for key, item in value.items()
        if not (key in shape.defaults and _same(item, shape.defaults[key]))
        and not (key in shape.left_out_empty and item == {})
    }


def _media_length(value: Any) -> int | float | None:
    """A number above zero, also one written as text; None for zero, empty
    or anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        if not _NUMBER.fullmatch(value):
            return None
        value = float(value)
    if not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if value > 0 else None


def _without_hash(component: Any) -> Any:
    """A component without the hash TiLiA stores in it; anything that isn't
    an object, as it is."""
    if not isinstance(component, dict):
        return component
    return {key: value for key, value in component.items() if key != "hash"}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _pattern(bars: list[Any]) -> str:
    """A beat pattern as text: its bar lengths separated by spaces, as
    desktop#621 joins a list, which it reads as the same pattern. An item
    that isn't text, which TiLiA never wrote, is written as `_text` writes
    it; the text then doesn't parse, and counts as "4" (FR-084)."""
    return " ".join(_text(bar) for bar in bars)


def _field(value: Any) -> str | list[str]:
    """A field's value as text: a list of plain values as a list of texts."""
    if isinstance(value, list) and not any(
        isinstance(item, (dict, list)) for item in value
    ):
        return [_text(item) for item in value]
    return _text(value)


class _Migration:
    def __init__(self, version: str, path: str | os.PathLike[str] | None) -> None:
        self.version = version
        self.path = path
        self.warnings: list[ReadWarning] = []
        self.changes: dict[str, int] = {}

    def _refuse(self, message: str, place: str) -> UnreadableFile:
        return UnreadableFile(message, path=self.path, place=place)

    def _object(self, value: Any, place: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise self._refuse(f"expected an object at {place}", place)
        return value

    def _require(self, value: dict[str, Any], key: str, place: str) -> Any:
        if key not in value:
            name = json.dumps(key, ensure_ascii=False)
            raise self._refuse(f"{name} is missing", pointer_to(place, key))
        return value[key]

    def _text(self, value: dict[str, Any], key: str, place: str) -> str:
        text = self._require(value, key, place)
        if not isinstance(text, str):
            at = pointer_to(place, key)
            raise self._refuse(f"expected text at {at}", at)
        return text

    def _warn(self, place: str, message: str, change: str, count: int = 1) -> None:
        self.warnings.append(ReadWarning(place=place, line=None, message=message))
        self._count(change, count)

    def _count(self, change: str, count: int) -> None:
        """Add `count` to a count of the report; a count stays out until it
        is above zero."""
        if count:
            self.changes[change] = self.changes.get(change, 0) + count

    def check(self, old: dict[str, Any]) -> None:
        """Check the shapes TiLiA's own migrations read, before they run."""
        for key in _CURRENT_ONLY:
            if key in old:
                name = json.dumps(key, ensure_ascii=False)
                raise self._refuse(
                    f"a file from TiLiA {printable(self.version)} can't hold"
                    f" {printable(name)}, a key of the current format",
                    pointer_to("", key),
                )
        if "media_path" in old and not isinstance(old["media_path"], str):
            raise self._refuse("expected text at /media_path", "/media_path")
        if "media_metadata" in old:
            self._object(old["media_metadata"], "/media_metadata")
        timelines = self._object(old["timelines"], "/timelines")
        renames = old_migrations.renames_display_position(self.version)
        for key, timeline in timelines.items():
            place = pointer_to("/timelines", key)
            self._object(timeline, place)
            self._text(timeline, "kind", place)
            position = timeline.get("display_position")
            if renames and "display_position" in timeline and type(position) is not int:
                at = pointer_to(place, "display_position")
                raise self._refuse(f"expected an integer at {at}", at)

    def to_current(self, old: dict[str, Any]) -> dict[str, Any]:
        """The content in the current format, with the old ids."""
        fields = dict(old.get("media_metadata", {}))
        length = _media_length(fields.pop(_MEDIA_LENGTH, None))
        content: dict[str, Any] = {
            "app_name": old.get("app_name", "TiLiA"),
            "version": self.version,
            "time_unit": "seconds",
            "media": {"path": old.get("media_path", ""), "length": length},
            "metadata": {name: _field(value) for name, value in fields.items()},
            "timelines": {
                key: self._timeline(key, timeline)
                for key, timeline in old["timelines"].items()
            },
            "scores": [],
        }
        for key, value in old.items():
            if key not in _OLD_TOP_LEVEL:
                content[key] = value  # a key the core doesn't know
        return content

    def _timeline(self, key: str, timeline: dict[str, Any]) -> dict[str, Any]:
        place = pointer_to("/timelines", key)
        kind = timeline_kind_from_file(timeline["kind"])
        if isinstance(kind, UnknownKind):
            # Kept as it is, without TiLiA's stored hashes: its own and its
            # components'.
            kept = {k: v for k, v in timeline.items() if k not in _STORED_HASHES}
            if isinstance(kept.get("components"), dict):
                kept["components"] = {
                    name: _without_hash(component)
                    for name, component in kept["components"].items()
                }
            return kept
        if self._require(timeline, "ordinal", place) is None:
            # Refused, not filled in as a height is: TiLiA 0.7 would give it
            # the next ordinal, but TiLiA has written one in every file since
            # 0.1.1, so only a file edited by hand has none.
            at = pointer_to(place, "ordinal")
            raise self._refuse('"ordinal" should be an integer, not null', at)
        components = self._object(
            self._require(timeline, "components", place),
            pointer_to(place, "components"),
        )
        converted = {
            name: value
            for name, value in timeline.items()
            if name not in _STORED_HASHES and name != "components"
        }
        # In the format's spelling, which the current format reads exactly:
        # an old file may have any letter case, and TiLiA's own migration
        # spells an old "AUDIOWAVE_TIMELINE" "Audiowave".
        converted["kind"] = timeline_kind_to_file(kind)
        if kind == "beat" and isinstance(converted.get("beat_pattern"), list):
            # Text, as the current format writes it (contracts/migration.md,
            # *Beat timelines*, step 6); "4", the default, is then left out.
            converted["beat_pattern"] = _pattern(converted["beat_pattern"])
        if isinstance(converted.get("rows"), list):
            converted["rows"] = [
                _without_defaults(row, RANGE_ROW_SHAPE)
                if isinstance(row, dict)
                else row
                for row in converted["rows"]
            ]
        converted = _without_defaults(converted, TIMELINE_SHAPES[kind])
        components_place = pointer_to(place, "components")
        if kind == "audiowave":
            # Computed from the media whenever it loads (layout.md, point 9).
            if components:
                count = len(components)
                bars = "amplitude bar" if count == 1 else "amplitude bars"
                self._warn(
                    components_place,
                    f"{count} {bars} dropped",
                    "amplitude_bars_dropped",
                    count,
                )
            converted["components"] = {}
        else:
            converted["components"] = {
                name: self._component(name, value, components_place, kind)
                for name, value in components.items()
            }
        return converted

    def _component(
        self, key: str, value: Any, parent: str, timeline_kind: str
    ) -> dict[str, Any]:
        place = pointer_to(parent, key)
        component = self._object(value, place)
        kind = component_kind_from_file(self._text(component, "kind", place))
        converted: dict[str, Any] = _without_hash(component)
        if kind == "hierarchy":
            for name in ("formal_type", "formal_function"):
                dropped = converted.pop(name, None)
                if dropped not in ("", None):
                    shown = printable(json.dumps(dropped, ensure_ascii=False))
                    self._warn(
                        pointer_to(place, name),
                        f"{name} {shown} dropped",
                        "formal_values_dropped",
                    )
        if kind in ("hierarchy", "range"):
            # Left unset where they equal what they default to (desktop#700).
            for derived, base in (("pre_start", "start"), ("post_end", "end")):
                if derived in converted and base in converted:
                    if _equal_numbers(converted[derived], converted[base]):
                        del converted[derived]
        if isinstance(kind, UnknownKind):
            return converted
        held = kind in TIMELINE_COMPONENTS[timeline_kind]
        if held and "comments" in COMPONENT_SHAPES[kind].known:
            # Not in a component of a kind its timeline doesn't hold, which is
            # kept as it is, as the check keeps it. Before the attributes at
            # their default go, so that a comment left empty goes with them,
            # where it has a default: a legacy score's note writes it empty.
            self._count("marks_moved", marks.move(converted))
        return _without_defaults(converted, COMPONENT_SHAPES[kind])


def _follow(reference: Any, new_ids: dict[str, str]) -> Any:
    """The new id of the component an old reference names, or the reference
    as it is when it names none."""
    if isinstance(reference, int) and not isinstance(reference, bool):
        reference = str(reference)
    if isinstance(reference, str) and reference in new_ids:
        return new_ids[reference]
    return reference


def _with_new_ids(content: dict[str, Any], document_id: str) -> dict[str, Any]:
    timelines: dict[str, Any] = {}
    for position, (old_id, timeline) in enumerate(content["timelines"].items()):
        new_id = migrated_id(document_id, "timeline", old_id, position=position)
        kind = timeline_kind_from_file(timeline["kind"])
        if not isinstance(kind, UnknownKind):
            components = timeline["components"]
            new_ids = {
                key: migrated_id(document_id, "component", old_id, key, position=index)
                for index, key in enumerate(components)
            }
            renamed = {}
            for key, component in components.items():
                if kind == "range" and "joined_right" in component:
                    component = {
                        **component,
                        "joined_right": _follow(component["joined_right"], new_ids),
                    }
                renamed[new_ids[key]] = component
            timeline = {**timeline, "components": renamed}
        timelines[new_id] = timeline
    return {**content, "timelines": timelines}
