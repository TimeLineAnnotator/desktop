"""Reading `.tla` files of any TiLiA version into a `Document`."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from tilia_core.tla.errors import UnreadableFile, printable
from tilia_core.tla.model import (
    Component,
    Document,
    Score,
    Timeline,
    UnknownKind,
    component_kind_from_file,
    timeline_kind_from_file,
)
from tilia_core.tla.parse import parse
from tilia_core.tla.write import (
    COMPONENT_SHAPES,
    FORMAT_VERSION,
    MEDIA_SHAPE,
    TIMELINE_SHAPES,
    TOP_SHAPE,
    UNKNOWN_COMPONENT,
    Shape,
    nfc_object,
    nfc_value,
    pointer_to,
)


def read(path: str | os.PathLike[str]) -> Document:
    """Read a `.tla` file. Nothing is written, created or touched.

    Raises `UnreadableFile` for content the reader refuses, and lets the
    system's `OSError` through for a file it can't open or read.
    """
    with open(path, "rb") as file:
        data = file.read()
    return loads(data, path=path)


def loads(data: bytes, *, path: str | os.PathLike[str] | None = None) -> Document:
    """Read a `.tla` file's bytes. `path`, when given, is where the file is."""
    content = parse(data, path=path)
    _check_version(content, path)
    return _Reader(path).document(content)


# Semantic Versioning's form, which the format's versions take from 1.0.0 on.
_SEMANTIC = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
_LEADING_DIGITS = re.compile(r"[0-9]*")


def _number(digits: str) -> tuple[int, str]:
    # Compared without int(), which refuses very long digit strings.
    digits = digits.lstrip("0")
    return len(digits), digits


_RELEASE = (1,)  # a release sorts after all of its prereleases


def _precedence(version: str) -> tuple[Any, ...] | None:
    """A key that orders versions as Semantic Versioning does, where
    1.0.0-draft.1 < 1.0.0-draft.2 < 1.0.0; None for another form."""
    match = _SEMANTIC.fullmatch(version)
    if match is None:
        return None
    major, minor, patch, prerelease = match.groups()
    if prerelease is None:
        release: tuple[Any, ...] = _RELEASE
    else:
        release = (0,) + tuple(
            (0, _number(part), "") if part.isdigit() else (1, (0, ""), part)
            for part in prerelease.split(".")
        )
    return _number(major), _number(minor), _number(patch), release


def _check_version(
    content: dict[str, Any], path: str | os.PathLike[str] | None
) -> None:
    """Return if the file is in the current format, and raise otherwise: a
    draft other than the current one is converted again from its sources, never
    read (FR-007), and a newer format is refused, naming its version (FR-014)."""
    version = content.get("version", "0.0.0")
    if not isinstance(version, str):
        raise UnreadableFile(
            "the format version isn't text", path=path, place="/version"
        )
    if version == FORMAT_VERSION:
        return
    if not _LEADING_DIGITS.match(version).group().strip("0"):
        # Major version 0, as TiLiA compares versions: a file from TiLiA 0.x.
        raise NotImplementedError(
            f"reading files from TiLiA {printable(version)} needs the migration"
        )
    ours, theirs = _precedence(FORMAT_VERSION), _precedence(version)
    if theirs is not None and (
        theirs < ours or (theirs[:3] == ours[:3] and theirs[3] != _RELEASE)
    ):
        message = (
            f"a draft of the format ({printable(version)}):"
            " convert it again from its sources"
        )
    else:
        message = f"written by a newer TiLiA (format {printable(version)})"
    raise UnreadableFile(message, path=path, place="/version")


_TIMELINE_FIELDS = frozenset({"kind", "name", "ordinal", "metadata", "components"})
_COMPONENT_FIELDS = frozenset({"kind", "metadata"})
_SCORE_FIELDS = frozenset({"id", "format", "source", "license", "content"})


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _attrs(
    value: dict[str, Any], shape: Shape, fields: frozenset[str]
) -> dict[str, Any]:
    """An entry's attributes, with those at their default filled in, derived
    ones (`pre_start` = `start`) included."""
    attrs: dict[str, Any] = {}
    for key in shape.keys:
        if key in fields:
            continue
        if key in value:
            item = value[key]
            kind = type(item)
            if kind is float or kind is int or (kind is str and item.isascii()):
                attrs[key] = item  # what most values are: nothing to normalise
            else:
                attrs[key] = nfc_value(item)
        elif key in shape.defaults:
            attrs[key] = shape.defaults[key]
        elif shape.derived.get(key) in value:
            attrs[key] = nfc_value(value[shape.derived[key]])
    return attrs


def _unknown(value: dict[str, Any], known: frozenset[str]) -> dict[str, Any]:
    if value.keys() <= known:
        return {}
    return {key: nfc_value(item) for key, item in value.items() if key not in known}


class _Reader:
    """Makes a `Document` of a file in the current format: kinds in lower case,
    attributes at their default filled in, unknown keys in `extra`, text in
    NFC except a score's lines. A beat's measure mark and beat unit are kept as
    stored: a mark's number, label and source depend on the marks before it,
    and the timeline's measure table is where they are resolved."""

    def __init__(self, path: str | os.PathLike[str] | None) -> None:
        self.path = path

    def _refuse(self, message: str, place: str) -> UnreadableFile:
        return UnreadableFile(message, path=self.path, place=place)

    def _object(self, value: Any, place: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise self._refuse(f"expected an object at {place}", place)
        return nfc_object(value)

    def _text(self, value: Any, parent: str, key: str | int) -> str:
        if not isinstance(value, str):
            place = pointer_to(parent, key)
            raise self._refuse(f"expected text at {place}", place)
        return value

    def _require(self, value: dict[str, Any], key: str, place: str) -> Any:
        if key not in value:
            name = json.dumps(key, ensure_ascii=False)
            raise self._refuse(f"{name} is missing", pointer_to(place, key))
        return value[key]

    def _metadata(self, value: dict[str, Any], place: str) -> dict[str, Any]:
        if "metadata" not in value:
            return {}
        return nfc_value(self._object(value["metadata"], pointer_to(place, "metadata")))

    def document(self, content: dict[str, Any]) -> Document:
        content = nfc_object(content)
        for key in TOP_SHAPE.keys:
            self._require(content, key, "")
        media = self._object(content["media"], "/media")
        for key in MEDIA_SHAPE.keys:
            self._require(media, key, "/media")
        origin = None if self.path is None else Path(os.path.abspath(self.path))
        return Document(
            document_id=nfc_value(content["document_id"]),
            format_version=content["version"],
            time_unit=nfc_value(content["time_unit"]),
            media_path=nfc_value(media["path"]),
            media_length=media["length"],
            media_extra=_unknown(media, MEDIA_SHAPE.known),
            metadata=self._metadata(content, ""),
            timelines=self._timelines(content["timelines"], "/timelines"),
            scores=self._scores(content["scores"], "/scores"),
            app_name=nfc_value(content["app_name"]),
            extra=_unknown(content, TOP_SHAPE.known),
            origin=origin,
        )

    def _timelines(self, value: Any, place: str) -> dict[str, Timeline]:
        timelines = self._object(value, place)
        return {
            key: self._timeline(key, timelines[key], pointer_to(place, key))
            for key in sorted(timelines)
        }

    def _timeline(self, timeline_id: str, value: Any, place: str) -> Timeline:
        timeline = self._object(value, place)
        spelling = self._text(self._require(timeline, "kind", place), place, "kind")
        kind = timeline_kind_from_file(spelling)
        if isinstance(kind, UnknownKind):
            # Kept whole, and written back from `raw`; its name, ordinal and
            # metadata are given as well, for reading.
            raw = nfc_value(timeline)
            name, ordinal, metadata = (
                raw.get(k) for k in ("name", "ordinal", "metadata")
            )
            return Timeline(
                id=timeline_id,
                kind=kind,
                ordinal=ordinal if _is_integer(ordinal) else 0,
                name=name if isinstance(name, str) else "",
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
                raw=raw,
            )
        shape = TIMELINE_SHAPES[kind]
        components = self._require(timeline, "components", place)
        return Timeline(
            id=timeline_id,
            kind=kind,
            ordinal=self._require(timeline, "ordinal", place),
            name=nfc_value(timeline.get("name", shape.defaults["name"])),
            metadata=self._metadata(timeline, place),
            attrs=_attrs(timeline, shape, _TIMELINE_FIELDS),
            components=self._components(components, pointer_to(place, "components")),
            extra=_unknown(timeline, shape.known),
        )

    def _components(self, value: Any, place: str) -> dict[str, Component]:
        components = self._object(value, place)
        return {
            key: self._component(key, components[key], pointer_to(place, key))
            for key in sorted(components)
        }

    def _component(self, component_id: str, value: Any, place: str) -> Component:
        component = self._object(value, place)
        spelling = self._text(self._require(component, "kind", place), place, "kind")
        kind = component_kind_from_file(spelling)
        metadata = self._metadata(component, place)
        if isinstance(kind, UnknownKind):
            known = UNKNOWN_COMPONENT.known
            return Component(
                id=component_id,
                kind=kind,
                metadata=metadata,
                extra=_unknown(component, known),
            )
        shape = COMPONENT_SHAPES[kind]
        return Component(
            id=component_id,
            kind=kind,
            attrs=_attrs(component, shape, _COMPONENT_FIELDS),
            metadata=metadata,
            extra=_unknown(component, shape.known),
        )

    def _scores(self, value: Any, place: str) -> dict[str, Score]:
        if not isinstance(value, list):
            raise self._refuse(f"expected a list at {place}", place)
        scores = {}
        for index, item in enumerate(value):
            score = self._score(item, pointer_to(place, index))
            scores[score.id] = score
        return dict(sorted(scores.items()))

    def _score(self, value: Any, place: str) -> Score:
        score = self._object(value, place)
        score_id = self._require(score, "id", place)
        score_format = self._require(score, "format", place)
        content = self._require(score, "content", place)
        self._text(score_id, place, "id")
        self._text(score_format, place, "format")
        lines = pointer_to(place, "content")
        if not isinstance(content, list):
            raise self._refuse(f"expected a list at {lines}", lines)
        for index, line in enumerate(content):
            self._text(line, lines, index)
        return Score(
            id=nfc_value(score_id),
            format=nfc_value(score_format),
            lines=list(content),  # as imported: never in NFC
            source=nfc_value(score["source"]) if "source" in score else None,
            license=nfc_value(score["license"]) if "license" in score else None,
            # A legacy score's beat_x among them.
            extra=_unknown(score, _SCORE_FIELDS),
        )
