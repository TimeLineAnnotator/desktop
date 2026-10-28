"""TiLiA's own migrations between its 0.x versions, ported from the app.

The app's `tilia/file/migration.py`, as TiLiA 0.7 runs it when it opens a
file: each function makes one change, and applies to the files below its
target version. Then the changes TiLiA 0.7 makes to any old file when it
opens it, and so writes when it saves the file again without an edit:
hierarchies lose `parent` and `children`, which TiLiA before 0.5.6 wrote and
TiLiA now computes from levels and times, and clef icons lose `.svg`. After
them, every old file has TiLiA 0.7.0's shape, so that a file saved again by
TiLiA 0.7 without an edit is migrated to the same content. The core doesn't
import the app, so all of this is copied here.

One difference: TiLiA 0.1.1, as released, still wrote `display_position`,
and TiLiA's migration, which applies below 0.1.1, leaves its files without
an `ordinal`. Here it applies to them too; it changes nothing in a file
without `display_position`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tilia_core.tla.model import timeline_kind_from_file

Migration = Callable[[dict[str, Any]], dict[str, Any]]
# A version as TiLiA compares versions; see version_key.
VersionKey = tuple[tuple[int, str], ...]


def version_key(version: str) -> VersionKey:
    """A key that orders versions as TiLiA's `_parse_version` does: by the
    leading integer of each dot-separated part, up to the first part without
    one, so that suffixes are ignored ("0.7.0rc1" as 0.7.0, "0.5.15.0" as
    0.5.15.0). Text without one is 0. Integers are compared by their digits
    rather than with int(), which refuses very long digit strings, and only
    ASCII digits count."""
    parts: list[tuple[int, str]] = []
    for segment in version.split("."):
        digits = ""
        for char in segment:
            if not "0" <= char <= "9":
                break
            digits += char
        if not digits:
            break
        digits = digits.lstrip("0")
        parts.append((len(digits), digits))
    return tuple(parts) or ((0, ""),)


def _display_position_to_ordinal(data: dict[str, Any]) -> dict[str, Any]:
    """Rename each timeline's `display_position` to `ordinal`, which is
    1-based where `display_position` was 0-based."""
    for timeline in data.get("timelines", {}).values():
        if "display_position" in timeline:
            timeline["ordinal"] = timeline.pop("display_position") + 1
    return data


def normalize_kind_string(kind: str) -> str:
    """A timeline kind as TiLiA 0.7 writes it: TiLiA before 0.7 wrote
    "MARKER_TIMELINE", which becomes "Marker"."""
    if kind.endswith("_TIMELINE"):
        return kind.replace("_TIMELINE", "").capitalize()
    return kind


def _timeline_kind(data: dict[str, Any]) -> dict[str, Any]:
    for timeline in data.get("timelines", {}).values():
        timeline["kind"] = normalize_kind_string(timeline.get("kind", ""))
    return data


def _as_tilia_0_7_opens_it(data: dict[str, Any]) -> dict[str, Any]:
    """Make the changes TiLiA 0.7 makes to an old file when it opens it:
    hierarchies' `parent` and `children` dropped, clef icons without `.svg`.
    Components that aren't objects are left for the migration to refuse."""
    for timeline in data.get("timelines", {}).values():
        kind = timeline_kind_from_file(timeline.get("kind", ""))
        components = timeline.get("components")
        if kind not in ("hierarchy", "score") or not isinstance(components, dict):
            continue
        for component in components.values():
            if not isinstance(component, dict):
                continue
            if component.get("kind") == "HIERARCHY":
                component.pop("parent", None)
                component.pop("children", None)
            elif component.get("kind") == "CLEF":
                icon = component.get("icon")
                if isinstance(icon, str):
                    component["icon"] = icon.removesuffix(".svg")
    return data


# Each migration with the version from which files no longer need it, in
# ascending order.
MIGRATIONS: list[tuple[str, Migration]] = [
    ("0.1.1", _display_position_to_ordinal),
    ("0.7.0", _timeline_kind),
]
# TiLiA 0.1.1 wrote display_position too (see the module's docstring).
_ALSO_AT: dict[Migration, str] = {_display_position_to_ordinal: "0.1.1"}


def applies(target: str, function: Migration, version: str) -> bool:
    """Whether the migration to `target` applies to a file of `version`."""
    key = version_key(version)
    also = _ALSO_AT.get(function)
    return key < version_key(target) or (also is not None and key == version_key(also))


def renames_display_position(version: str) -> bool:
    """Whether a file of this version has its `display_position` renamed."""
    return applies("0.1.1", _display_position_to_ordinal, version)


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Bring an old file's content to TiLiA 0.7.0's shape, in place, as TiLiA
    does when it opens the file. The shapes the migrations touch must have
    been checked: an object of timeline objects, each with its kind as text,
    and an integer `display_position` where the first migration applies."""
    version = data.get("version", "0.0.0")
    for target, function in MIGRATIONS:
        if applies(target, function, version):
            data = function(data)
    return _as_tilia_0_7_opens_it(data)
