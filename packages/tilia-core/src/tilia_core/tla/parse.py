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


class _Constant(Exception):
    pass


def _refuse_constant(name: str) -> Any:
    # NaN, Infinity and -Infinity: json.loads accepts them, but they aren't JSON.
    raise _Constant


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
        content = json.loads(
            text, object_pairs_hook=_no_repeated_keys, parse_constant=_refuse_constant
        )
    except _RepeatedKey:
        key, place, line = _find(text, keys=True)
        named = "a key" if key is None else json.dumps(key, ensure_ascii=False)
        raise UnreadableFile(
            f"{named} appears twice in one object", path=path, line=line, place=place
        ) from None
    except json.JSONDecodeError as error:
        raise UnreadableFile(
            f"not valid JSON ({error.msg})", path=path, line=error.lineno
        ) from None
    except _Constant:
        # What a strict JSON parser says there.
        _, _, line = _find(text, keys=False)
        raise UnreadableFile(
            "not valid JSON (Expecting value)", path=path, line=line
        ) from None
    except RecursionError:
        # Where the parser runs out of stack first, which depends on the system.
        raise UnreadableFile(_TOO_DEEP, path=path) from None
    if not isinstance(content, dict) or "timelines" not in content:
        raise UnreadableFile("not a TiLiA file", path=path)
    if _deeper_than(content, MAX_DEPTH):
        raise UnreadableFile(_TOO_DEEP, path=path)
    return content


# A TiLiA file nests about eight levels deep. The limit keeps the code that walks
# a document from running out of stack, whatever the system and Python version.
MAX_DEPTH = 100
_TOO_DEEP = f"nested more than {MAX_DEPTH} levels deep"


def _deeper_than(content: Any, limit: int) -> bool:
    stack = [(content, 1)]
    while stack:
        value, depth = stack.pop()
        children = value.values() if isinstance(value, dict) else value
        for child in children:
            if isinstance(child, (dict, list)):
                if depth == limit:
                    return True
                stack.append((child, depth + 1))
    return False


def pointer(path: list[str]) -> str:
    """A JSON Pointer (RFC 6901) to the place `path` names."""
    return "".join("/" + step.replace("~", "~0").replace("/", "~1") for step in path)


class _Found(Exception):
    def __init__(self, key: str | None, path: list[str], position: int) -> None:
        self.key, self.path, self.position = key, path, position


def _walk(
    text: str, position: int, path: list[str], scan_value: Any, keys: bool
) -> int:
    """Skip the JSON value at `position`, raising `_Found` at a key repeated in one
    object when `keys` is true, and at a value `scan_value` refuses."""
    position = _SKIP.match(text, position).end()
    if text[position] == "{":
        seen: set[str] = set()
        position = _SKIP.match(text, position + 1).end()
        if text[position] == "}":
            return position + 1
        while True:
            key_at = position
            key, position = scanstring(text, position + 1)
            if keys and key in seen:
                raise _Found(key, [*path, key], key_at)
            seen.add(key)
            position = _SKIP.match(text, position).end() + 1  # the colon
            position = _walk(text, position, [*path, key], scan_value, keys)
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
            position = _walk(text, position, [*path, str(index)], scan_value, keys)
            index += 1
            position = _SKIP.match(text, position).end()
            if text[position] == "]":
                return position + 1
            position += 1  # the comma
    try:
        _, end = scan_value(text, position)
    except _Constant:
        raise _Found(None, path, position) from None
    return end


def _find(text: str, *, keys: bool) -> tuple[str | None, str | None, int | None]:
    """Where json.loads stopped, found again: the first key repeated in one object
    when `keys` is true, else the first value it refused. Gives the key, the place
    and the line. Runs only on a refusal."""
    decoder = json.JSONDecoder(parse_constant=None if keys else _refuse_constant)
    try:
        _walk(text, 0, [], decoder.scan_once, keys)
    except _Found as found:
        return found.key, pointer(found.path), text.count("\n", 0, found.position) + 1
    except (ValueError, IndexError, RecursionError, StopIteration):
        pass
    return None, None, None
