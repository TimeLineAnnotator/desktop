"""Real ``.tla`` files for the corpus's tests.

The stand-in reader (``json_reader``) never gives the documents that broke the
index: its documents always have complete attributes, and its fingerprints refuse
a lone surrogate before the index sees it. So these tests read small files in the
current format through WP3's reader, with a thin :class:`TlaReader` on
``tla.read``. T014 makes WP3's reader the default; this goes away with it.
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from tilia_core import tla
from tilia_core.corpus.documents import (
    ComponentDoc,
    Document,
    TimelineDoc,
    UnreadableFile,
)


@dataclass(frozen=True)
class TlaDocument(Document):
    source: Any = field(default=None, compare=False, repr=False)


def _kind(kind: Any) -> str:
    return kind.spelling if isinstance(kind, tla.UnknownKind) else str(kind)


class TlaReader:
    """The index's ``DocumentReader`` on ``tilia_core.tla``."""

    extensions: tuple[str, ...] = (".tla",)

    def read(self, path: Path) -> Document:
        try:
            doc = tla.read(path)
        except tla.UnreadableFile as err:
            raise UnreadableFile(Path(path), err.message, err.line) from err
        return TlaDocument(
            document_id=doc.document_id,
            format_version=doc.format_version,
            media_length=doc.media_length,
            time_unit=doc.time_unit,
            fields=dict(doc.metadata),
            timelines=tuple(
                TimelineDoc(
                    id=tl.id,
                    kind=_kind(tl.kind),
                    name=tl.name or "",
                    ordinal=tl.ordinal,
                    fields=dict(tl.metadata),
                    attrs=dict(tl.attrs),
                    components=tuple(
                        ComponentDoc(
                            id=c.id,
                            kind=_kind(c.kind),
                            attrs=dict(c.attrs),
                            fields=dict(c.metadata),
                        )
                        for c in tl.components.values()
                    ),
                )
                for tl in sorted(doc.timelines.values(), key=lambda t: t.ordinal)
            ),
            source=doc,
        )

    def canonical_bytes(self, document: Document) -> bytes:
        return tla.canonical_bytes(document.source)

    def is_temporary(self, name: str) -> bool:
        return tla.is_temporary(name)


class Doctored(TlaReader):
    """A reader that keeps to the contract, where ``attrs`` may hold anything,
    and is laxer than WP3's: in ``bad.tla`` the first unit of the timelines of
    ``kind`` has ``value`` as its ``attr``."""

    def __init__(self, kind: str, attr: str, value: Any) -> None:
        self.kind, self.attr, self.value = kind, attr, value

    def read(self, path: Path) -> Document:
        document = super().read(path)
        if Path(path).name != "bad.tla":
            return document
        timelines = []
        for tl in document.timelines:
            if tl.kind == self.kind:
                first = replace(
                    tl.components[0],
                    attrs={**tl.components[0].attrs, self.attr: self.value},
                )
                tl = replace(tl, components=(first, *tl.components[1:]))
            timelines.append(tl)
        return replace(document, timelines=tuple(timelines))


def song(label: str = "verse") -> dict[str, Any]:
    """A small file in the current format, as the data ``json.dumps`` writes:
    a hierarchy, markers, beats and a range, each with one or two units."""
    return {
        "app_name": "TiLiA",
        "version": tla.FORMAT_VERSION,
        "document_id": tla.new_id(),
        "time_unit": "seconds",
        "media": {"path": "", "length": 20.0},
        "metadata": {},
        "scores": [],
        "timelines": {
            tla.new_id(): {
                "kind": "Hierarchy",
                "name": "Form",
                "ordinal": 1,
                "height": 60,
                "components": {
                    tla.new_id(): {
                        "kind": "HIERARCHY",
                        "start": 0.0,
                        "end": 10.0,
                        "level": 1,
                        "label": label,
                    },
                    tla.new_id(): {
                        "kind": "HIERARCHY",
                        "start": 10.0,
                        "end": 20.0,
                        "level": 1,
                        "label": "chorus",
                    },
                },
            },
            tla.new_id(): {
                "kind": "Marker",
                "name": "Cadences",
                "ordinal": 2,
                "height": 30,
                "components": {
                    tla.new_id(): {"kind": "MARKER", "time": 5.0, "label": "HC"}
                },
            },
            tla.new_id(): {
                "kind": "Beat",
                "name": "Beats",
                "ordinal": 3,
                "height": 35,
                "beat_pattern": "4",
                "components": {
                    tla.new_id(): {
                        "kind": "BEAT",
                        "time": 0.0,
                        "measure": {"number": 1},
                    },
                    tla.new_id(): {"kind": "BEAT", "time": 1.0},
                },
            },
            tla.new_id(): {
                "kind": "Range",
                "name": "Texture",
                "ordinal": 4,
                "height": 60,
                "rows": [{"id": "r1", "name": "Upper"}],
                "default_row_height": 30,
                "components": {
                    tla.new_id(): {
                        "kind": "RANGE",
                        "start": 0.0,
                        "end": 5.0,
                        "row_id": "r1",
                        "label": "tune",
                    }
                },
            },
        },
    }


def unit(data: dict[str, Any], timeline_kind: str) -> dict[str, Any]:
    """The first unit of the first timeline of ``timeline_kind`` in ``data``."""
    for tl in data["timelines"].values():
        if tl["kind"] == timeline_kind:
            return next(iter(tl["components"].values()))
    raise KeyError(timeline_kind)


def write(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def null_beat(data: dict[str, Any]) -> None:
    unit(data, "Beat")["time"] = None


def surrogate_label(data: dict[str, Any]) -> None:
    unit(data, "Marker")["label"] = "\ud800"


def huge_level(data: dict[str, Any]) -> None:
    unit(data, "Hierarchy")["level"] = 10**30


def spoiled(change) -> dict[str, Any]:
    data = song()
    change(data)
    return data
