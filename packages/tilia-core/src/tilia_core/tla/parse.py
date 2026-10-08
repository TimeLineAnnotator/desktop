"""From a `.tla` file's bytes to JSON: the byte-order mark, line numbers and repeated keys."""

from __future__ import annotations

import json
import re
from json.decoder import scanstring
from pathlib import Path
from typing import Any

from tilia_core.tla.errors import UnreadableFile

_BOM = b"\xef\xbb\xbf"
_JSON_WHITESPACE = " \t\n\r"
_SKIP = re.compile(r"[ \t\n\r]*")


class _RepeatedKey(Exception):
    pass


def _no_repeated_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise _RepeatedKey
    return result


def parse(data: bytes, *, path: Path | None = None) -> dict[str, Any]:
    """Parse a file's bytes, or raise `UnreadableFile` saying why they aren't a TiLiA file.

    One UTF-8 byte-order mark is skipped; CRLF reads like LF. Text is returned
    as it is, without normalisation.
    """
    start = len(_BOM) if data.startswith(_BOM) else 0
    try:
        text = data[start:].decode("utf-8")
    except UnicodeDecodeError as error:
        at = start + error.start
        line = data.count(b"\n", 0, at) + 1
        raise UnreadableFile(f"not UTF-8, at byte {at}", path=path, line=line) from None
    if not text.strip(_JSON_WHITESPACE):
        raise UnreadableFile("empty file", path=path)
    try:
        content = json.loads(text, object_pairs_hook=_no_repeated_keys)
    except _RepeatedKey:
        key, place, line = _find_repeated_key(text)
        raise UnreadableFile(
            f"{json.dumps(key, ensure_ascii=False)} appears twice in one object",
            path=path,
            line=line,
            place=place,
        ) from None
    except json.JSONDecodeError as error:
        raise UnreadableFile(
            f"not valid JSON ({error.msg})", path=path, line=error.lineno
        ) from None
    if not isinstance(content, dict) or "timelines" not in content:
        raise UnreadableFile("not a TiLiA file", path=path)
    return content


def pointer(path: list[str]) -> str:
    """A JSON Pointer (RFC 6901) to the place `path` names."""
    return "".join("/" + step.replace("~", "~0").replace("/", "~1") for step in path)


class _Found(Exception):
    def __init__(self, key: str, path: list[str], position: int) -> None:
        self.key, self.path, self.position = key, path, position


_scan_value = json.JSONDecoder().scan_once


def _walk(text: str, position: int, path: list[str]) -> int:
    """Skip the JSON value at `position`, raising `_Found` at a key repeated in one object."""
    position = _SKIP.match(text, position).end()
    if text[position] == "{":
        seen: set[str] = set()
        position = _SKIP.match(text, position + 1).end()
        if text[position] == "}":
            return position + 1
        while True:
            key_at = position
            key, position = scanstring(text, position + 1)
            if key in seen:
                raise _Found(key, [*path, key], key_at)
            seen.add(key)
            position = _SKIP.match(text, position).end() + 1  # the colon
            position = _walk(text, position, [*path, key])
            position = _SKIP.match(text, position).end()
            if text[position] == "}":
                return position + 1
            position = _SKIP.match(text, position + 1).end()  # the comma
    if text[position] == "[":
        index = 0
        position = _SKIP.match(text, position + 1).end()
        if text[position] == "]":
            return position + 1
        while True:
            position = _walk(text, position, [*path, str(index)])
            index += 1
            position = _SKIP.match(text, position).end()
            if text[position] == "]":
                return position + 1
            position += 1  # the comma
    _, end = _scan_value(text, position)
    return end


def _find_repeated_key(text: str) -> tuple[str | None, str | None, int | None]:
    """The first key repeated in one object, its place and its line. Runs only on a refusal."""
    try:
        _walk(text, 0, [])
    except _Found as found:
        return found.key, pointer(found.path), text.count("\n", 0, found.position) + 1
    except (ValueError, IndexError, RecursionError, StopIteration):
        pass
    return None, None, None
