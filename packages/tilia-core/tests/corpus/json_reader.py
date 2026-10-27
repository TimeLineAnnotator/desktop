"""A test-only document reader: files that hold a ``Document`` as JSON.

It stands in for WP3's reader (TimeLineAnnotator/project-management#7) until
that lands (contracts/reader.md). It reads its own JSON shape, never TiLiA's
format: the core has one reader of the format, WP3's.

A file holds an object with the fields of ``Document``; ``timelines`` is a
list of objects with the fields of ``TimelineDoc``, each with its
``components``, objects with the fields of ``ComponentDoc``.
"""

import json
from pathlib import Path
from typing import Any

from tilia_core.corpus.documents import (
    ComponentDoc,
    Document,
    TimelineDoc,
    UnreadableFile,
)

TEMPORARY_SUFFIX = ".tmp.tla"


def to_json(document: Document) -> dict[str, Any]:
    """``document`` as the plain data the stand-in writes."""
    return {
        "document_id": document.document_id,
        "format_version": document.format_version,
        "media_length": document.media_length,
        "time_unit": document.time_unit,
        "fields": dict(document.fields),
        "timelines": [
            {
                "id": tl.id,
                "kind": tl.kind,
                "name": tl.name,
                "ordinal": tl.ordinal,
                "fields": dict(tl.fields),
                "attrs": dict(tl.attrs),
                "components": [
                    {
                        "id": c.id,
                        "kind": c.kind,
                        "attrs": dict(c.attrs),
                        "fields": dict(c.fields),
                    }
                    for c in tl.components
                ],
            }
            for tl in document.timelines
        ],
    }


def from_json(data: dict[str, Any]) -> Document:
    """The document that ``to_json`` wrote as ``data``. Sequences of timelines
    and components are tuples; attributes and fields are as JSON gives them."""
    return Document(
        document_id=data["document_id"],
        format_version=data["format_version"],
        media_length=data["media_length"],
        time_unit=data["time_unit"],
        fields=data["fields"],
        timelines=tuple(
            TimelineDoc(
                id=tl["id"],
                kind=tl["kind"],
                name=tl["name"],
                ordinal=tl["ordinal"],
                fields=tl["fields"],
                attrs=tl["attrs"],
                components=tuple(
                    ComponentDoc(
                        id=c["id"], kind=c["kind"], attrs=c["attrs"], fields=c["fields"]
                    )
                    for c in tl["components"]
                ),
            )
            for tl in data["timelines"]
        ),
    )


class JsonDocumentReader:
    """Reads ``.tla`` files that hold a ``Document`` as JSON (a byte-order mark
    and CRLF line endings are accepted); writes them sorted by key, UTF-8, with
    LF line endings and a final newline."""

    extensions: tuple[str, ...] = (".tla",)

    def read(self, path: Path) -> Document:
        data = Path(path).read_bytes()  # an OSError goes through
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as err:
            raise UnreadableFile(Path(path), f"not UTF-8: {err.reason}") from err
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as err:
            raise UnreadableFile(
                Path(path), f"not valid JSON: {err.msg}", err.lineno
            ) from err
        try:
            return from_json(parsed)
        except (KeyError, TypeError) as err:
            raise UnreadableFile(Path(path), f"not a document: {err!r}") from err

    def canonical_bytes(self, document: Document) -> bytes:
        text = json.dumps(
            to_json(document), sort_keys=True, ensure_ascii=False, indent=2
        )
        return (text + "\n").encode("utf-8")

    def is_temporary(self, name: str) -> bool:
        return name.lower().endswith(TEMPORARY_SUFFIX)
