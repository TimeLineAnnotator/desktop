"""Ids in `.tla` files: new UUIDv7s, and the ids derived for files from older TiLiA versions.

Derived ids must never change: reading an old file before and after an update
of tilia-core has to give the same ids.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
import unicodedata
import uuid
from collections import Counter
from collections.abc import Iterator
from operator import itemgetter
from typing import Any

ID_KINDS = ("timeline", "component", "score")
MIGRATED_BASE_MS = 946_684_800_000  # 2000-01-01T00:00:00Z, in Unix milliseconds
# Old integer ids below this offset take the base plus the id; other old ids take
# the base plus the offset plus their position, also below the offset. So every
# migrated time field is below the base plus 2**39 ms, in June 2017.
NON_INTEGER_OFFSET = 1 << 38

_DECIMAL = re.compile(r"0|[1-9][0-9]*")
_OFFSET_DIGITS = len(str(NON_INTEGER_OFFSET))
_RAND_A_BITS = 12
_RAND_B_BITS = 62


def _uuid(ms: int, version: int, rand_a: int, rand_b: int) -> str:
    value = ms << 80 | version << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


class _Clock:
    """UUIDv7's time field, with RFC 9562's method 1: a counter within each millisecond."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ms = -1
        self._counter = 0

    def next(self) -> tuple[int, int]:
        with self._lock:
            now = time.time_ns() // 1_000_000
            if now > self._ms:
                self._ms, self._counter = now, secrets.randbits(_RAND_A_BITS - 1)
            else:
                # The same millisecond, or the clock went back: count on.
                self._counter += 1
                if self._counter >> _RAND_A_BITS:
                    self._ms, self._counter = self._ms + 1, secrets.randbits(
                        _RAND_A_BITS - 1
                    )
            return self._ms, self._counter


_clock = _Clock()


def new_id() -> str:
    """A new UUIDv7. Ids from one process sort in the order they were made."""
    ms, counter = _clock.next()
    return _uuid(ms, 7, counter, secrets.randbits(_RAND_B_BITS))


def _as_offset(old_id: Any) -> int | None:
    if isinstance(old_id, bool):
        return None
    if isinstance(old_id, int):
        value = old_id
    elif (
        isinstance(old_id, str)
        # Longer can't be below the offset, and int() refuses very long text.
        and len(old_id) <= _OFFSET_DIGITS
        and _DECIMAL.fullmatch(old_id)
    ):
        value = int(old_id)
    else:
        return None
    return value if 0 <= value < NON_INTEGER_OFFSET else None


def migrated_id(
    document_id: str, kind: str, *old_ids: str | int, position: int | None = None
) -> str:
    """The id a migrated timeline, component or score gets, in UUIDv7's form.

    `old_ids` are the entry's old ids, outermost first: a timeline's, then a
    component's. The time field is 2000-01-01 plus the last old id in
    milliseconds, so the ids sort as the old ids did, and before any id made
    since 2017. An old id that isn't a non-negative integer below 2**38 takes
    2**38 plus `position`, its position in the old file, also below 2**38, so
    such ids sort after the others. The other bits come from a SHA-256 of the
    document id, the kind and the old ids, so the same file always gives the
    same ids.
    """
    if kind not in ID_KINDS:
        raise ValueError(f"kind must be one of {', '.join(ID_KINDS)}, not {kind!r}")
    if not old_ids:
        raise ValueError("migrated_id needs the entry's old id")
    offset = _as_offset(old_ids[-1])
    if offset is None:
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or not 0 <= position < NON_INTEGER_OFFSET
        ):
            raise ValueError(
                f"old id {old_ids[-1]!r} isn't an integer: give its position in the"
                " old file, an integer from 0 to 2**38 - 1"
            )
        offset = NON_INTEGER_OFFSET + position
    # A JSON list, which no other list of strings gives, in ASCII: a lone
    # surrogate is escaped.
    key = json.dumps([document_id, kind, *(str(old_id) for old_id in old_ids)])
    digest = hashlib.sha256(key.encode("ascii")).digest()
    bits = int.from_bytes(digest[:10], "big")
    rand_a = bits >> (80 - _RAND_A_BITS)
    rand_b = bits & ((1 << _RAND_B_BITS) - 1)
    return _uuid(MIGRATED_BASE_MS + offset, 7, rand_a, rand_b)


def _normal(value: Any) -> Any:
    """`value` with its text in NFC, and its numbers by value: 10.0 as 10."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        keys = _nfc_keys(list(value))
        return dict(zip(keys, map(_normal, value.values()), strict=True))
    if isinstance(value, list):
        return [_normal(item) for item in value]
    return value


def _nfc_keys(keys: list[str]) -> list[str]:
    """The keys in NFC, except those NFC would merge with another, which are kept
    as they are, so that no value is lost."""
    normal = [unicodedata.normalize("NFC", key) for key in keys]
    if len(set(normal)) == len(normal):
        return normal
    counts = Counter(normal)
    return [
        key if counts[nfc] > 1 else nfc for key, nfc in zip(keys, normal, strict=True)
    ]


_ENCODER = json.JSONEncoder(sort_keys=True, ensure_ascii=False, separators=(",", ":"))
# The levels of objects and arrays that are hashed in parts: an old file's
# document, its timelines, a timeline and its components. Text there is hashed
# in slices, so that the hash never holds a copy of the file or of its scores.
_TAKEN_APART = 4
_SLICE = 1 << 16


def _json_parts(value: Any, levels: int) -> Iterator[str]:
    """`value` made normal as sorted-key JSON, in parts: the outer `levels` of objects
    and arrays taken apart, and their text sliced. They join into the text
    `json.dumps(_normal(value), sort_keys=True, ...)` would give at once."""
    if isinstance(value, str):
        value = unicodedata.normalize("NFC", value)
        yield '"'
        for start in range(0, len(value), _SLICE):
            # Each character is escaped on its own, so slices escape as the whole.
            yield _ENCODER.encode(value[start : start + _SLICE])[1:-1]
        yield '"'
    elif levels == 0 or not isinstance(value, (dict, list)):
        yield _ENCODER.encode(_normal(value))
    elif isinstance(value, dict):
        pairs = zip(_nfc_keys(list(value)), value.values(), strict=True)
        yield "{"
        for index, (key, item) in enumerate(sorted(pairs, key=itemgetter(0))):
            yield ("," if index else "") + _ENCODER.encode(key) + ":"
            yield from _json_parts(item, levels - 1)
        yield "}"
    else:
        yield "["
        for index, item in enumerate(value):
            if index:
                yield ","
            yield from _json_parts(item, levels - 1)
        yield "]"


def _without(data: Any, keys: tuple[str, ...]) -> Any:
    if not isinstance(data, dict):
        return data
    return {key: value for key, value in data.items() if key not in keys}


def derived_document_id(old: dict[str, Any]) -> str:
    """The document id of a file from an older TiLiA version, a version-8 UUID.

    It comes from a SHA-256 of `old`, in NFC, with numbers by value (10.0 as
    10), as sorted-key JSON, leaving out what changes without an edit:
    `file_path`, `version`, `app_name`, the stored hashes and the media
    length. So a moved file, a file with other line endings, and a file saved
    again without an edit by a TiLiA version that writes the same keys keep
    their id. A version that renames or adds keys changes it, unless the
    caller passes the content after the migrations that bring every version
    to the same keys.
    """
    content = _without(old, ("file_path", "version", "app_name", "timelines_hash"))
    if "media_metadata" in content:
        content["media_metadata"] = _without(
            content["media_metadata"], ("media length",)
        )
    timelines = content.get("timelines")
    if isinstance(timelines, dict):
        content["timelines"] = {}
        for timeline_id, timeline in timelines.items():
            timeline = _without(timeline, ("hash", "components_hash"))
            if isinstance(timeline, dict) and isinstance(
                timeline.get("components"), dict
            ):
                timeline["components"] = {
                    component_id: _without(component, ("hash",))
                    for component_id, component in timeline["components"].items()
                }
            content["timelines"][timeline_id] = timeline
    digest = hashlib.sha256()
    for part in _json_parts(content, _TAKEN_APART):
        # surrogatepass: a label cut inside an emoji is a lone surrogate, which
        # TiLiA saved as an escape and json.loads accepts.
        digest.update(part.encode("utf-8", "surrogatepass"))
    value = int.from_bytes(digest.digest()[:16], "big")
    value = value & ~(0xF << 76) | 8 << 76
    value = value & ~(0b11 << 62) | 0b10 << 62
    return str(uuid.UUID(int=value))
