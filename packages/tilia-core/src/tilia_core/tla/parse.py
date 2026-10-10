"""From a `.tla` file's bytes to JSON: the byte-order mark, line numbers and repeated keys."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from json.decoder import WHITESPACE, scanstring
from typing import Any

from tilia_core.tla.errors import UnreadableFile, printable

_BOM = b"\xef\xbb\xbf"


class _RepeatedKey(Exception):
    pass


class _Constant(Exception):
    pass


class _TooLarge(Exception):
    pass


def _refuse_constant(name: str) -> Any:
    # NaN, Infinity and -Infinity: json.loads accepts them, but they aren't JSON.
    raise _Constant


def _finite_float(text: str) -> float:
    # A number like 1e999, which json.loads reads as an infinity.
    value = float(text)
    if not math.isfinite(value):
        raise _TooLarge
    return value


def _no_repeated_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise _RepeatedKey
    return result


def parse(
    data: bytes,
    *,
    path: str | os.PathLike[str] | None = None,
    check: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Parse a file's bytes, or raise `UnreadableFile` saying why they aren't a TiLiA file.

    One UTF-8 byte-order mark is skipped; CRLF reads like LF. Text is returned
    as it is, without normalisation. `check`, when given, is called with the
    top level as soon as it is an object, before anything is required of it:
    the reader checks the version there, since a newer format may lay out
    the rest otherwise.
    """
    start = len(_BOM) if data.startswith(_BOM) else 0
    try:
        text = data[start:].decode("utf-8")
    except UnicodeDecodeError as error:
        at = start + error.start
        line = data.count(b"\n", 0, at) + 1
        raise UnreadableFile(f"not UTF-8, at byte {at}", path=path, line=line) from None
    if WHITESPACE.fullmatch(text):
        raise UnreadableFile("empty file", path=path)
    try:
        content = json.loads(
            text, object_pairs_hook=_no_repeated_keys, parse_constant=_refuse_constant
        )
    except (_RepeatedKey, _Constant, ValueError, RecursionError) as error:
        raise _refusal(text, error, path) from None
    if not isinstance(content, dict):
        raise UnreadableFile("not a TiLiA file", path=path)
    if check is not None:
        check(content)
    if "timelines" not in content:
        raise UnreadableFile("not a TiLiA file", path=path)
    problem = _first_problem(content, MAX_DEPTH)
    if problem is not None:
        raise _refusal(text, problem, path)
    return content


# A TiLiA file nests about eight levels deep. The limit keeps the code that walks
# a document from running out of stack, whatever the system and Python version.
MAX_DEPTH = 100
_TOO_DEEP = f"nested more than {MAX_DEPTH} levels deep"
_TOO_LARGE = "number too large to read"
# What a strict JSON parser says at NaN or Infinity.
_NOT_A_VALUE = "not valid JSON (Expecting value)"


def _first_problem(content: Any, limit: int) -> str | None:
    """What json.loads let through: nesting deeper than `limit`, or a number too
    large for a float, which it reads as an infinity."""
    stack = [(content, 1)]
    while stack:
        value, depth = stack.pop()
        children = value.values() if isinstance(value, dict) else value
        for child in children:
            if isinstance(child, (dict, list)):
                if depth == limit:
                    return _TOO_DEEP
                stack.append((child, depth + 1))
            elif type(child) is float and not math.isfinite(child):
                return _TOO_LARGE
    return None


def _refusal(
    text: str, error: Exception | str, path: str | os.PathLike[str] | None
) -> UnreadableFile:
    """Why the text is refused: the first problem in it, so that a file gives the
    same message on every Python version, whose parsers run out of stack at
    different depths. `error` is what json.loads raised, or what it let through."""
    found = _find(text)
    if found is not None and (
        not isinstance(error, json.JSONDecodeError) or found.position < error.pos
    ):
        line = text.count("\n", 0, found.position) + 1
        place = None if found.key is None else pointer(found.path)
        return UnreadableFile(found.message, path=path, line=line, place=place)
    # The walk found nothing before the text stops being JSON.
    if isinstance(error, json.JSONDecodeError):
        message = f"not valid JSON ({error.msg})"
        return UnreadableFile(message, path=path, line=error.lineno)
    if isinstance(error, _RepeatedKey):
        return UnreadableFile("a key appears twice in one object", path=path)
    if isinstance(error, _Constant):
        return UnreadableFile(_NOT_A_VALUE, path=path)
    if isinstance(error, RecursionError):
        return UnreadableFile(_TOO_DEEP, path=path)
    if isinstance(error, ValueError):
        # An integer longer than Python reads (4300 digits since Python 3.10.7).
        return UnreadableFile(_TOO_LARGE, path=path)
    return UnreadableFile(str(error), path=path)


def pointer(path: list[str]) -> str:
    """A JSON Pointer (RFC 6901) to the place `path` names."""
    return "".join("/" + step.replace("~", "~0").replace("/", "~1") for step in path)


class _Found(Exception):
    def __init__(
        self, message: str, path: list[str], position: int, key: str | None = None
    ) -> None:
        self.message, self.path, self.position, self.key = message, path, position, key


def _walk(text: str, position: int, path: list[str], scan_value: Any) -> int:
    """Skip the JSON value at `position`, raising `_Found` at the first problem:
    an object or array nested deeper than MAX_DEPTH, a key repeated in one object,
    or a value `scan_value` refuses."""
    position = WHITESPACE.match(text, position).end()
    if text[position] in "{[" and len(path) == MAX_DEPTH:
        raise _Found(_TOO_DEEP, path, position)
    if text[position] == "{":
        seen: set[str] = set()
        position = WHITESPACE.match(text, position + 1).end()
        if text[position] == "}":
            return position + 1
        while True:
            key_at = position
            key, position = scanstring(text, position + 1)
            if key in seen:
                named = printable(json.dumps(key, ensure_ascii=False))
                message = f"{named} appears twice in one object"
                raise _Found(message, [*path, key], key_at, key)
            seen.add(key)
            position = WHITESPACE.match(text, position).end() + 1  # the colon
            position = _walk(text, position, [*path, key], scan_value)
            position = WHITESPACE.match(text, position).end()
            if text[position] == "}":
                return position + 1
            position = WHITESPACE.match(text, position + 1).end()  # the comma
    if text[position] == "[":
        index = 0
        position = WHITESPACE.match(text, position + 1).end()
        if text[position] == "]":
            return position + 1
        while True:
            position = _walk(text, position, [*path, str(index)], scan_value)
            index += 1
            position = WHITESPACE.match(text, position).end()
            if text[position] == "]":
                return position + 1
            position += 1  # the comma
    try:
        _, end = scan_value(text, position)
    except json.JSONDecodeError:
        raise  # where the text stops being JSON
    except _Constant:
        raise _Found(_NOT_A_VALUE, path, position) from None
    except (_TooLarge, ValueError):
        raise _Found(_TOO_LARGE, path, position) from None
    return end


def _find(text: str) -> _Found | None:
    """The first problem in the text, found by walking it as json.loads reads it,
    or None when the text stops being JSON first. Runs only on a refusal."""
    decoder = json.JSONDecoder(
        parse_constant=_refuse_constant, parse_float=_finite_float
    )
    try:
        _walk(text, 0, [], decoder.scan_once)
    except _Found as found:
        return found
    except (ValueError, IndexError, RecursionError, StopIteration):
        pass
    return None
