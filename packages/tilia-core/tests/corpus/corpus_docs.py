"""Documents of every kind for the corpus tests, and files written from them.

The builders give ``TimelineDoc``s with the attributes contracts/reader.md
lists ("The attributes the index uses"), and ``document`` puts them in a
``Document``. ``write_doc`` writes a document as the stand-in reader reads it
(``json_reader``), with the distortions a test asks for.
``document_from_fixture`` turns a fixture of WP13's ``examples.toml`` into the
document whose rows equal the tables ``fixture_index.build_index`` builds.
"""

import json
from pathlib import Path
from typing import Any

import fixture_index
from fake_timemap import FakeTimeMap
from json_reader import JsonDocumentReader, to_json

from tilia_core.corpus.documents import ComponentDoc, Document, TimelineDoc

READER = JsonDocumentReader()
FORMAT_VERSION = "1.0"


def component(cid: str, kind: str, fields: dict | None = None, **attrs: Any):
    return ComponentDoc(id=cid, kind=kind, attrs=attrs, fields=fields or {})


def timeline(
    tid: str,
    kind: str,
    name: str,
    ordinal: int,
    components=(),
    *,
    fields: dict | None = None,
    **attrs: Any,
) -> TimelineDoc:
    return TimelineDoc(
        id=tid,
        kind=kind,
        name=name,
        ordinal=ordinal,
        fields=fields or {},
        attrs=attrs,
        components=tuple(components),
    )


def hierarchy(units, *, tid="t1", name="Form (A)", ordinal=1, fields=None):
    """``units``: ``(label, level, start, end)`` or with a colour after them."""
    comps = []
    for n, (label, level, start, end, *rest) in enumerate(units, 1):
        comps.append(
            component(
                f"{tid}:c{n}",
                "hierarchy",
                start=start,
                end=end,
                level=level,
                label=label,
                color=rest[0] if rest else None,
                comments="",
            )
        )
    return timeline(tid, "hierarchy", name, ordinal, comps, fields=fields)


def markers(units, *, tid="t2", name="Cadences", ordinal=2, fields=None):
    """``units``: ``(label, time)`` or with a colour after them."""
    comps = [
        component(
            f"{tid}:c{n}",
            "marker",
            time=time,
            label=label,
            color=rest[0] if rest else None,
            comments="",
        )
        for n, (label, time, *rest) in enumerate(units, 1)
    ]
    return timeline(tid, "marker", name, ordinal, comps, fields=fields)


def ranges(rows, units, *, tid="t3", name="Layers", ordinal=3, fields=None):
    """``rows``: row names; ``units``: ``(row, label, start, end)``."""
    row_ids = {row: f"{tid}:r{i}" for i, row in enumerate(rows, 1)}
    comps = [
        component(
            f"{tid}:c{n}",
            "range",
            start=start,
            end=end,
            row_id=row_ids[row],
            label=label,
            color=None,
            comments="",
        )
        for n, (row, label, start, end) in enumerate(units, 1)
    ]
    rows_attr = [{"id": row_ids[row], "name": row} for row in rows]
    return timeline(tid, "range", name, ordinal, comps, fields=fields, rows=rows_attr)


def key_component(cid: str, time: float, tonic: str, mode: str) -> ComponentDoc:
    step, accidental = fixture_index._spell(tonic)
    return component(
        cid, "mode", time=time, step=step, accidental=accidental, type=mode, comments=""
    )


def chord_component(cid: str, time, root, quality, inversion=0, applied_to=0):
    step, accidental = fixture_index._spell(root)
    return component(
        cid,
        "harmony",
        time=time,
        step=step,
        accidental=accidental,
        quality=quality,
        inversion=inversion,
        applied_to=applied_to,
        custom_text=None,
        comments="",
        # the label TiLiA shows: the examples print chords as Roman numerals
        display_mode="roman",
    )


def harmony(keys, chords, *, tid="t4", name="Harmony", ordinal=4, fields=None):
    """``keys``: ``(time, tonic, "major" | "minor")``; ``chords``: ``(time,
    root, quality, inversion?, applied_to?)``, a quality as TiLiA stores it."""
    comps = [key_component(f"{tid}:k{n}", *k) for n, k in enumerate(keys, 1)]
    comps += [chord_component(f"{tid}:c{n}", *c) for n, c in enumerate(chords, 1)]
    return timeline(tid, "harmony", name, ordinal, comps, fields=fields)


def beats(start, every, beats_per_bar, numbers, *, tid="t5", name="Beats", ordinal=5):
    """A regular grid: ``beats_per_bar`` beats of ``every`` seconds from
    ``start``, a bar per printed number in ``numbers``. The timeline's
    attributes are today's ``beat_pattern``, ``measure_numbers`` and
    ``beats_in_measure`` (contracts/time-map.md)."""
    tmap = FakeTimeMap(start, every, beats_per_bar, numbers)
    comps = [
        component(f"{tid}:c{i}", "beat", time=t)
        for i, t in enumerate(tmap.beat_times(), 1)
    ]
    return timeline(
        tid,
        "beat",
        name,
        ordinal,
        comps,
        beat_pattern=[beats_per_bar],
        measure_numbers=list(numbers),
        beats_in_measure=[beats_per_bar] * len(numbers),
    )


def unindexed(kind: str, *, tid="t9", name=None, ordinal=9, **attrs: Any):
    """A timeline of a kind the index doesn't read: ``score``, ``pdf``,
    ``audiowave``, ``slider``, or one the core doesn't know."""
    comps = [component(f"{tid}:c1", "note" if kind == "score" else kind, start=0)]
    return timeline(tid, kind, name or kind.title(), ordinal, comps, **attrs)


def document(*timelines, document_id="doc", fields=None, media_length=60.0, **kw):
    return Document(
        document_id=document_id,
        format_version=kw.get("format_version", FORMAT_VERSION),
        media_length=media_length,
        time_unit=kw.get("time_unit", "seconds"),
        fields=fields or {},
        timelines=tuple(timelines),
    )


# One builder per kind, with a few units each: ``KINDS[kind](tid, ordinal)``.
KINDS = {
    "hierarchy": lambda tid, ordinal: hierarchy(
        [["A", 2, 0, 20, "pink"], ["a", 1, 0, 10], ["b", 1, 10, 20]],
        tid=tid,
        ordinal=ordinal,
        fields={"role": "form", "author": "Ana", "tags": ["draft", "done"]},
    ),
    "marker": lambda tid, ordinal: markers(
        [["PAC", 5, "#ff0000"], ["HC", 15]], tid=tid, ordinal=ordinal
    ),
    "range": lambda tid, ordinal: ranges(
        ["solo", "tutti"],
        [["solo", "S", 2, 8], ["tutti", "T", 8, 12]],
        tid=tid,
        ordinal=ordinal,
    ),
    "harmony": lambda tid, ordinal: harmony(
        [[0, "C", "major"], [10, "G", "minor"]],
        [[0, "C", "major"], [5, "G", "dominant-seventh", 1], [10, "G", "minor"]],
        tid=tid,
        ordinal=ordinal,
    ),
    "beat": lambda tid, ordinal: beats(0, 1, 4, [1, 2, 3], tid=tid, ordinal=ordinal),
    "score": lambda tid, ordinal: unindexed("score", tid=tid, ordinal=ordinal),
    "pdf": lambda tid, ordinal: unindexed(
        "pdf", tid=tid, ordinal=ordinal, path="score.pdf"
    ),
    "unknown": lambda tid, ordinal: unindexed("spectrogram", tid=tid, ordinal=ordinal),
}


def every_kind(**kw) -> Document:
    """A document with one timeline of every kind, in the order of ``KINDS``."""
    timelines = [
        build(f"t{ordinal}", ordinal) for ordinal, build in enumerate(KINDS.values(), 1)
    ]
    return document(*timelines, fields={"title": "Every kind", "tags": ["test"]}, **kw)


def _reversed_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _reversed_keys(value[k]) for k in sorted(value, reverse=True)}
    if isinstance(value, list):
        return [_reversed_keys(v) for v in value]
    return value


def write_doc(
    path: Path,
    document: Document,
    *,
    crlf: bool = False,
    shuffle_keys: bool = False,
    bom: bool = False,
) -> Path:
    """Write ``document`` as the stand-in reader reads it: its canonical bytes,
    or, as asked, with every object's keys in reverse order, CRLF line endings
    or a UTF-8 byte-order mark. Returns ``path``."""
    if shuffle_keys:
        text = json.dumps(
            _reversed_keys(to_json(document)), ensure_ascii=False, indent=2
        )
        data = (text + "\n").encode("utf-8")
    else:
        data = READER.canonical_bytes(document)
    if crlf:
        data = data.replace(b"\n", b"\r\n")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def document_from_fixture(fixture: dict, document_id: str | None = None) -> Document:
    """The document of an ``examples.toml`` fixture (WP13's ``examples.py``).

    Ids, roles and labels follow ``fixture_index``, so that the rows built from
    the document equal the tables it builds: the document id is the fixture's
    ``name`` (else ``f1``), timeline ``k`` is ``<id>:t<k>``, its units are
    ``<id>:t<k>:c<n>`` (keys ``…:k<n>``, rows ``…:r<n>``), in the order the
    fixture index numbers them. A hierarchy called "Form (X)" has the fields
    role ``form`` and author ``X``, a marker timeline called "Cadences" role
    ``cadences``, a harmony timeline role ``harmony``. A beat timeline holds
    one beat component per beat of its grid."""
    fid = document_id or fixture.get("name", "f1")
    timelines = []
    for ordinal, tl in enumerate(fixture["timelines"], 1):
        tid = f"{fid}:t{ordinal}"
        role, author = fixture_index._timeline_role(tl)
        fields = {k: v for k, v in (("role", role), ("author", author)) if v}
        kind = tl["kind"]
        if kind == "hierarchy":
            doc = hierarchy(tl["units"], tid=tid, name=tl["name"], ordinal=ordinal)
        elif kind == "marker":
            doc = markers(tl["units"], tid=tid, name=tl["name"], ordinal=ordinal)
        elif kind == "range":
            doc = ranges(
                tl["rows"], tl["units"], tid=tid, name=tl["name"], ordinal=ordinal
            )
        elif kind == "harmony":
            keys, chords = fixture_index._in_lane_order(
                tl.get("keys", []), tl.get("chords", [])
            )
            doc = harmony(keys, chords, tid=tid, name=tl["name"], ordinal=ordinal)
        elif kind == "beats":
            numbers = tl.get("numbers") or list(range(1, tl["bars"] + 1))
            doc = beats(
                tl["start"],
                tl["every"],
                tl["beats_per_bar"],
                numbers,
                tid=tid,
                name=tl["name"],
                ordinal=ordinal,
            )
        else:
            raise ValueError(f"no fixture kind {kind!r}")
        timelines.append(
            TimelineDoc(
                id=doc.id,
                kind=doc.kind,
                name=doc.name,
                ordinal=doc.ordinal,
                fields=fields,
                attrs=doc.attrs,
                components=doc.components,
            )
        )
    fields = {
        name: [str(v) for v in value] if isinstance(value, list) else str(value)
        for name, value in fixture.get("fields", {}).items()
    }
    return document(
        *timelines,
        document_id=fid,
        fields=fields,
        media_length=float(fixture["length"]),
    )
