"""Real ``.tla`` files for the corpus's tests.

The stand-in reader (``json_reader``) never gives the documents that broke the
index: its documents always have complete attributes, and its fingerprints refuse
a lone surrogate before the index sees it. So these tests read small files in the
current format through WP3's reader, the corpus's :class:`TlaReader`.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from tilia_core import tla
from tilia_core.corpus.documents import Document
from tilia_core.corpus.tla_reader import TlaReader

__all__ = ["Doctored", "TlaReader", "song", "spoiled", "unit", "write"]


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


def as_tla(document: Document) -> tla.Document:
    """``document``, built by ``corpus_docs`` in the index's shape, as a
    document of the core, for ``tla.write``: new ids, the kinds the core names,
    the fields as metadata, and a beat timeline's bars as measure marks on its
    downbeats (``beats_in_measure`` or ``beat_pattern``, and
    ``measure_numbers``), as the current format stores them."""
    doc = tla.new_document(time_unit=document.time_unit)
    doc.media_length = document.media_length
    doc.metadata = dict(document.fields)
    for tl in document.timelines:
        attrs = {"height": 60, **tl.attrs}
        components = {}
        # a row's id is six letters and digits
        rows = {row["id"]: f"row{n:03}" for n, row in enumerate(attrs.get("rows", []))}
        if rows:
            attrs["rows"] = [{**row, "id": rows[row["id"]]} for row in attrs["rows"]]
        marks: dict[int, int] = {}
        if tl.kind == "beat":
            per_bar = (attrs.pop("beats_in_measure", None) or attrs["beat_pattern"])[0]
            attrs.pop("beat_pattern", None)
            numbers = attrs.pop("measure_numbers")
            marks = {i * per_bar: number for i, number in enumerate(numbers)}
        beats = sorted(
            (c for c in tl.components if c.kind == "beat"),
            key=lambda c: float(c.attrs["time"]),
        )
        order = {c.id: i for i, c in enumerate(beats)}
        for c in tl.components:
            cattrs = {k: v for k, v in c.attrs.items() if k != "display_mode"}
            if "row_id" in cattrs:
                cattrs["row_id"] = rows[cattrs["row_id"]]
            if c.kind == "beat" and order[c.id] in marks:
                cattrs["measure"] = {"number": marks[order[c.id]]}
            cid = tla.new_id()
            components[cid] = tla.Component(
                id=cid, kind=c.kind, attrs=cattrs, metadata=dict(c.fields)
            )
        tid = tla.new_id()
        doc.timelines[tid] = tla.Timeline(
            id=tid,
            kind=tl.kind,
            ordinal=tl.ordinal,
            name=tl.name,
            metadata=dict(tl.fields),
            attrs=attrs,
            components=components,
        )
    return doc
