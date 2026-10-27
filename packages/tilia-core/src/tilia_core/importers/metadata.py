"""Importing a file's fields from a JSON object, as TiLiA's `metadata import` does."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

from tilia_core import build, tla
from tilia_core.importers._csv import UTF8_DECODE_FAILED
from tilia_core.importers._results import ImportFailed, ImportResult
from tilia_core.tla.parse import MAX_DEPTH

# TiLiA's texts (tilia/errors.py), word for word.
_JSON_FAILED = "Error when parsing file {}:\n{}"
_FILE_FAILED = "File {} not found."
_MEDIA_LOADED = "Can't change media length when a media file is loaded."
# Where TiLiA has none (TimeLineAnnotator/project-management#326).
_NOT_AN_OBJECT = "expected an object of fields"
_LENGTH_IGNORED = "{} ignored: " + _MEDIA_LOADED
# tla's reader's, with its limit. How deep json.loads reads depends on the
# system and Python version.
_TOO_DEEP = f"nested more than {MAX_DEPTH} levels deep"
# A text, whose brackets don't count, or a bracket. A text that never closes
# runs to the end, so that it is read once, not again from each quote in it.
_TOKEN = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"?|[\[\]{}]')

_MEDIA_LENGTH = "media length"
# A number written as text, in ASCII, as WP3's migration reads an old file's
# media length (TimeLineAnnotator/project-management#326).
_NUMBER = re.compile(r"\s*[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\s*")


def import_metadata(
    document: tla.Document, path: str | os.PathLike[str]
) -> ImportResult:
    """Add a JSON object's fields to the document's (FR-053).

    Each field is set, or added after the others; where the document has it,
    the JSON's value wins. Values become text as WP3's migration makes an old
    file's fields text. A `media length` key, in any letter case, sets the
    media length as `build.set_media_length` does while no media is attached,
    and is ignored, with a note, while media is.

    Raises `ImportFailed`, and changes nothing, for a file that doesn't exist,
    isn't UTF-8, isn't JSON, nests deeper than `MAX_DEPTH` levels (the top
    level counts as one) or isn't an object, and for a media length
    `build.set_media_length` refuses; `OSError` for a file that can't be opened.
    """
    path = Path(path)
    content = _read(path)
    fields: dict[str, str | list[str]] = {}
    lengths: dict[str, Any] = {}
    try:
        for name, value in content.items():
            if name.lower() == _MEDIA_LENGTH:
                lengths[name] = value
            else:
                fields[name] = _field(value)
    except RecursionError as error:
        raise ImportFailed(path, _JSON_FAILED.format(path, repr(error))) from None

    result = ImportResult(rows=len(content))
    if lengths and document.media_path:
        result.notes.extend(_LENGTH_IGNORED.format(name) for name in lengths)
    elif lengths:
        _set_media_length(document, path, list(lengths.values()))
    # Every value is text by now, and no name is the media length's, so none
    # of these raises: a failure has happened before any of them.
    for name, text in fields.items():
        build.set_field(document, name, text)
    return result


def _read(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8-sig") as file:
            text = file.read()
    except FileNotFoundError:
        raise ImportFailed(path, _FILE_FAILED.format(path)) from None
    except UnicodeDecodeError:
        raise ImportFailed(path, UTF8_DECODE_FAILED.format(path, "JSON")) from None
    # Only the text before the first level too deep is read, so that json.loads
    # never runs out of stack, and a problem there comes first.
    deep = _too_deep(text)
    try:
        content = json.loads(text if deep is None else text[:deep])
    except ValueError as error:
        # A JSONDecodeError as TiLiA shows it, or an integer too long to read;
        # but not the end of the text cut short.
        if (
            deep is None
            or not isinstance(error, json.JSONDecodeError)
            or error.pos < deep
        ):
            raise ImportFailed(path, _JSON_FAILED.format(path, repr(error))) from None
    if deep is not None:
        raise ImportFailed(path, _JSON_FAILED.format(path, _TOO_DEEP))
    if not isinstance(content, dict):
        raise ImportFailed(path, _JSON_FAILED.format(path, _NOT_AN_OBJECT))
    return content


def _too_deep(text: str) -> int | None:
    """Where the text first opens a level deeper than MAX_DEPTH, or None. Right
    as far as the text is JSON."""
    depth = 0
    for token in _TOKEN.finditer(text):
        if token[0] in ("[", "{"):
            depth += 1
            if depth > MAX_DEPTH:
                return token.start()
        elif token[0] in ("]", "}"):
            depth -= 1
    return None


def _field(value: Any) -> str | list[str]:
    """A value as text, as WP3's migration makes an old file's fields text
    (`tla/migrate/to_1.py`): a list of plain values as a list of texts."""
    if isinstance(value, list) and not any(
        isinstance(item, (dict, list)) for item in value
    ):
        return [_text(item) for item in value]
    return _text(value)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _set_media_length(document: tla.Document, path: Path, values: list[Any]) -> None:
    """Set each value as the media length, in order; on a refusal, put the
    length back as it was and fail."""
    before = document.media_length
    try:
        for value in values:
            build.set_media_length(document, _length(value))
    except ValueError as error:
        document.media_length = before
        raise ImportFailed(path, str(error)) from None


def _length(value: Any) -> Any:
    """A positive number written as text, as a number; anything else as it is,
    for `build.set_media_length` to refuse as the JSON wrote it."""
    if isinstance(value, str) and _NUMBER.fullmatch(value):
        number = float(value)
        if math.isfinite(number) and number > 0:
            return number
    return value
