"""Upgrade ``.tla`` file data across TiLiA versions.

Adding a migration
------------------
Write a function ``dict -> dict`` that performs one breaking-change upgrade and
append ``(target_version, function)`` to ``MIGRATIONS`` in ascending version
order. Keep each function defensive (a no-op when the field it touches is
absent).
"""

from __future__ import annotations

from typing import Callable

from tilia.constants import VERSION

Migration = Callable[[dict], dict]


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple of ints.

    Reads the leading integer of each dot-separated segment, so suffixes
    are ignored (``"0.7.0rc1"`` -> ``(0, 7, 0)``).
    """
    parts: list[int] = []
    for segment in version.split("."):
        digits = ""
        for char in segment:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)


def is_from_newer_version(data: dict, app_version: str = VERSION) -> bool:
    return _parse_version(data.get("version", "0.0.0")) > _parse_version(app_version)


def _to_0_1_1_display_position_to_ordinal(data: dict) -> dict:
    """Rename each timeline's ``display_position`` to ``ordinal``.

    ``ordinal`` is 1-based; the old ``display_position`` was 0-based.
    """
    for timeline in data.get("timelines", {}).values():
        if "display_position" in timeline:
            timeline["ordinal"] = timeline.pop("display_position") + 1
    return data


def _to_0_7_0_timeline_kind(data: dict) -> dict:
    """Shorten the serialized timeline ``kind``.

    TiLiA < 0.7 wrote the kind as e.g. ``"MARKER_TIMELINE"``; 0.7 writes the
    ``Timeline`` subclass name without the suffix, e.g. ``"Marker"``.
    """
    for timeline in data.get("timelines", {}).values():
        kind = timeline.get("kind", "")
        if kind.endswith("_TIMELINE"):
            timeline["kind"] = kind.replace("_TIMELINE", "").capitalize()
    return data


# Ascending by target version. See module docstring before editing.
MIGRATIONS: list[tuple[str, Migration]] = [
    ("0.1.1", _to_0_1_1_display_position_to_ordinal),
    ("0.7.0", _to_0_7_0_timeline_kind),
]


def migrate(data: dict, app_version: str = VERSION) -> tuple[dict, list[str]]:
    """Upgrade ``data`` from its stored version up to ``app_version``.

    Applies, in order, every migration whose target is newer than the file's
    version and not newer than ``app_version``. Mutates and returns ``data``
    along with the list of target versions that were applied.
    """
    file_version = _parse_version(data.get("version", "0.0.0"))
    app = _parse_version(app_version)
    applied: list[str] = []
    for target, function in MIGRATIONS:
        if file_version < _parse_version(target) <= app:
            data = function(data)
            data["version"] = target
            applied.append(target)
    return data, applied
