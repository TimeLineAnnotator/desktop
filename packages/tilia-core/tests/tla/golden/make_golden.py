"""Write the golden files: `.tla` files in the current format, for T5's tests.

They are written with `json.dumps` directly, not with `tilia_core`, so that they
don't depend on the code they test. Each one is laid out by hand as the writer
lays a file out: keys in their fixed order, attributes at their default left
out, timelines and components in id order, text in NFC except score lines.

Run it from anywhere, after changing it: `python make_golden.py`. A test checks
that the files on disk are what it writes.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
VERSION = "1.0.0-draft.1"
# 2026-01-01T00:00:00Z: earlier than any id a test makes, so that a component or
# timeline a test adds sorts after the golden ones, as a new one does in a file.
BASE_MS = 1_767_225_600_000


def make_id(file: str, n: int) -> str:
    """The n-th id of a golden file: a UUIDv7, the same on every run."""
    bits = int.from_bytes(hashlib.sha256(f"{file}:{n}".encode()).digest()[:10], "big")
    rand_a = bits >> 68
    rand_b = bits & ((1 << 62) - 1)
    value = (BASE_MS + n) << 80 | 7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


def every_kind() -> dict[str, Any]:
    """Every timeline kind, metadata at every level, two beat timelines, an MEI
    score, and labels in German, Portuguese, Greek, Chinese, Hebrew and emoji."""
    ids = iter(make_id("every-kind", n) for n in range(100))
    document_id = next(ids)
    slider, beats, bars, form, cadences, harmony, texture, score_tl, pdf, wave = (
        next(ids) for _ in range(10)
    )
    score_id = next(ids)
    # A recording, tapped: a pickup, bars 1 and 2a, the repeat, 1 and 2b, a
    # cadenza 2c, then bars 3 and 4 in 6/8, tapped in two.
    b = [next(ids) for _ in range(17)]
    # The same bars from the score, folded: each written bar once, and `next`
    # for the playing order; then a second movement.
    q = [next(ids) for _ in range(6)]
    h = [next(ids) for _ in range(5)]
    m = [next(ids) for _ in range(3)]
    k = [next(ids) for _ in range(4)]
    r = [next(ids) for _ in range(3)]
    p = [next(ids) for _ in range(2)]

    def beat(time: float, **keys: Any) -> dict[str, Any]:
        return {"kind": "BEAT", "time": time, **keys}

    return {
        "app_name": "TiLiA",
        "version": VERSION,
        "document_id": document_id,
        "time_unit": "seconds",
        "media": {"path": "../audio/Ständchen.flac", "length": 17.5},
        "metadata": {
            "title": "Ständchen (excerpt)",
            "notes": "",
            "composer": "Franz Schubert",
            "performer": "内田光子",
            "genre": ["Lied", "romantic"],
        },
        "timelines": {
            slider: {
                "kind": "Slider",
                "ordinal": 1,
                "height": 16,
                "components": {},
            },
            beats: {
                "kind": "Beat",
                "name": "Beats",
                "ordinal": 2,
                "height": 35,
                "beat_pattern": "3",
                "metadata": {"role": "time_map", "author": "Maria João Costa"},
                "components": {
                    b[0]: beat(
                        0.0,
                        measure={"number": 0},
                        beat_unit={"denominator": 4, "units": "1"},
                    ),
                    b[1]: beat(1.0, measure={}, metadata={"tags": ["check"]}),
                    b[2]: beat(2.0),
                    b[3]: beat(3.0),
                    b[4]: beat(4.0, measure={"label": "2a", "force_display": True}),
                    b[5]: beat(5.0),
                    b[6]: beat(6.0),
                    b[7]: beat(
                        7.0,
                        measure={
                            "number": 1,
                            "source": "edited",
                            "metadata": {"tags": ["repeat"]},
                        },
                    ),
                    b[8]: beat(8.0),
                    b[9]: beat(9.0),
                    b[10]: beat(10.0, measure={"label": "2b"}),
                    b[11]: beat(11.0),
                    b[12]: beat(12.0),
                    b[13]: beat(
                        13.0, measure={"number": 2, "label": "2c", "cadenza": True}
                    ),
                    b[14]: beat(
                        14.5,
                        measure={},
                        beat_unit={"denominator": 8, "units": "3"},
                    ),
                    b[15]: beat(15.25),
                    b[16]: beat(16.0, measure={}),
                },
            },
            bars: {
                "kind": "Beat",
                "name": "Bars of the score",
                "ordinal": 3,
                "height": 35,
                "beat_pattern": "3",
                "show_time_signatures": False,
                "measure_source": "score",
                "components": {
                    q[0]: beat(
                        0.0,
                        measure={"number": 0},
                        beat_unit={"denominator": 4, "units": "1", "assumed": True},
                    ),
                    q[1]: beat(1.0, measure={"next": [q[2], q[3]]}),
                    q[2]: beat(4.0, measure={"label": "2a", "next": [q[1]]}),
                    q[3]: beat(
                        10.0, measure={"number": 2, "label": "2b", "source": "edited"}
                    ),
                    q[4]: beat(
                        14.5,
                        measure={},
                        beat_unit={"denominator": 8, "units": "2+1"},
                    ),
                    q[5]: beat(16.0, measure={"number": 1, "restart": True}),
                },
            },
            form: {
                "kind": "Hierarchy",
                "name": "Form",
                "ordinal": 4,
                "height": 60,
                "metadata": {
                    "role": "form",
                    "author": "Anne",
                    "source": "Caplin 1998",
                    "vocabulary": "lcma-form@0.3.0",
                },
                "components": {
                    h[0]: {
                        "kind": "HIERARCHY",
                        "start": 1.0,
                        "end": 17.5,
                        "level": 3,
                        "label": "Exposição",
                        "color": "#5c6bc0",
                    },
                    h[1]: {
                        "kind": "HIERARCHY",
                        "start": 1.0,
                        "pre_start": 0.0,
                        "end": 7.0,
                        "level": 2,
                        "label": "Hauptsatz – Überleitung",
                        "comments": "Sätze, not periods",
                        "metadata": {
                            "tags": ["check", "Satz"],
                            "generated_by": "group/MT",
                        },
                    },
                    h[2]: {
                        "kind": "HIERARCHY",
                        "start": 7.0,
                        "end": 14.5,
                        "post_end": 15.0,
                        "level": 2,
                        "label": "Θέμα β",
                    },
                    h[3]: {
                        "kind": "HIERARCHY",
                        "start": 14.5,
                        "end": 16.0,
                        "level": 1,
                        "label": "主題",
                    },
                    h[4]: {
                        "kind": "HIERARCHY",
                        "start": 16.0,
                        "end": 17.5,
                        "level": 1,
                        "label": "נושא",
                    },
                },
            },
            cadences: {
                "kind": "Marker",
                "name": "Cadences",
                "ordinal": 5,
                "height": 30,
                "measure_table": beats,
                "metadata": {"role": "cadences", "vocabulary": "cadences"},
                "components": {
                    m[0]: {
                        "kind": "MARKER",
                        "time": 7.0,
                        "label": "HC",
                        "color": "#5c6bc0",
                    },
                    m[1]: {
                        "kind": "MARKER",
                        "time": 14.5,
                        "comments": "Schluss 🎵",
                        "label": "PAC 🎻",
                    },
                    m[2]: {"kind": "MARKER", "time": 16.0},
                },
            },
            harmony: {
                "kind": "Harmony",
                "name": "Harmony",
                "ordinal": 6,
                "level_count": 2,
                "visible_level_count": 1,
                "components": {
                    k[0]: {"kind": "MODE", "time": 0.0, "step": 3},
                    k[1]: {
                        "kind": "HARMONY",
                        "time": 1.0,
                        "step": 3,
                        "display_mode": "roman",
                    },
                    k[2]: {
                        "kind": "HARMONY",
                        "time": 4.0,
                        "comments": "applied",
                        "step": 2,
                        "accidental": -1,
                        "quality": "minor",
                        "inversion": 1,
                        "applied_to": 4,
                        "level": 2,
                    },
                    k[3]: {
                        "kind": "HARMONY",
                        "time": 7.0,
                        "display_mode": "custom",
                        "custom_text": "Ger⁺⁶",
                        "custom_text_font_type": "normal",
                    },
                },
            },
            texture: {
                "kind": "Range",
                "name": "Texture",
                "ordinal": 7,
                "height": 60,
                "rows": [
                    {"id": "aZ3k9P", "name": "Mão direita"},
                    {
                        "id": "Qm7x2L",
                        "name": "Linke Hand",
                        "color": "#e57373",
                        "height": 40,
                    },
                ],
                "default_row_height": 30,
                "components": {
                    r[0]: {
                        "kind": "RANGE",
                        "start": 1.0,
                        "end": 4.0,
                        "row_id": "aZ3k9P",
                        "label": "melodia",
                        "joined_right": r[1],
                    },
                    r[1]: {
                        "kind": "RANGE",
                        "start": 4.0,
                        "end": 7.0,
                        "row_id": "aZ3k9P",
                        "color": "#81c784",
                        "pre_start": 3.5,
                        "post_end": 7.5,
                    },
                    r[2]: {
                        "kind": "RANGE",
                        "start": 1.0,
                        "end": 17.5,
                        "row_id": "Qm7x2L",
                        "comments": "Alberti",
                    },
                },
            },
            score_tl: {
                "kind": "Score",
                "name": "Score",
                "ordinal": 8,
                "height": 160,
                "score": score_id,
                "measure_table": bars,
                "components": {},
            },
            pdf: {
                "kind": "Pdf",
                "name": "Edition",
                "ordinal": 9,
                "height": 30,
                "path": "../scores/Ständchen.pdf",
                "components": {
                    p[0]: {"kind": "PDF_MARKER", "time": 0.0, "page_number": 1},
                    p[1]: {"kind": "PDF_MARKER", "time": 10.0, "page_number": 2},
                },
            },
            wave: {
                "kind": "AudioWave",
                "ordinal": 10,
                "height": 40,
                "is_visible": False,
                "components": {},
            },
        },
        "scores": [
            {
                "id": score_id,
                "format": "mei",
                "source": {
                    "file": "Ständchen.musicxml",
                    "origin": "made for these tests",
                    "converter": "Verovio 4.3.1",
                },
                "license": "CC0-1.0",
                "content": [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    '<mei xmlns="http://www.music-encoding.org/ns/mei" meiversion="5.0">',
                    "  <meiHead>",
                    "    <fileDesc>",
                    # Decomposed, as imported: score lines are never normalised.
                    "      <titleStmt><title>Ständchen</title></titleStmt>",
                    "    </fileDesc>",
                    "  </meiHead>",
                    "  <music>",
                    "    <body>",
                    "      <mdiv>",
                    "        <score>",
                    '          <scoreDef meter.count="3" meter.unit="4" key.sig="1f">',
                    '\t\t\t<staffGrp><staffDef n="1" lines="5" clef.shape="G" clef.line="2"/></staffGrp>',
                    "          </scoreDef>",
                    "          <section>",
                    '            <measure n="0" metcon="false">',
                    '              <staff n="1"><layer n="1">',
                    '                <note xml:id="n1" pname="c" oct="5" dur="4"/>',
                    "              </layer></staff>",
                    '              <dir xml:id="tilia-0001" type="tilia" staff="1"'
                    ' tstamp="1">dolce \\ 柔和</dir>',
                    "            </measure>",
                    "          </section>",
                    "        </score>",
                    "      </mdiv>",
                    "    </body>",
                    "  </music>",
                    "</mei>",
                    "",
                ],
            }
        ],
    }


def empty() -> dict[str, Any]:
    """A new document: no media, no metadata, no timelines, no scores."""
    return {
        "app_name": "TiLiA",
        "version": VERSION,
        "document_id": make_id("empty", 0),
        "time_unit": "seconds",
        "media": {"path": "", "length": None},
        "metadata": {},
        "timelines": {},
        "scores": [],
    }


def unknown() -> dict[str, Any]:
    """A timeline of a kind the core doesn't know, kept as it is, a component of
    a kind it doesn't know, and keys it doesn't know at every level, after the
    known ones in code-point order. A quarters file: its times are integers."""
    ids = iter(make_id("unknown", n) for n in range(100))
    document_id = next(ids)
    beats, markers, rows, lyrics = (next(ids) for _ in range(4))
    score_id = next(ids)
    b = [next(ids) for _ in range(2)]
    m = [next(ids) for _ in range(2)]
    lyric = next(ids)
    return {
        "app_name": "TiLiA",
        "version": VERSION,
        "document_id": document_id,
        "time_unit": "quarters",
        "media": {"path": "", "length": None, "x_media": "kept"},
        "metadata": {"title": "Unknown kinds and keys"},
        "timelines": {
            beats: {
                "kind": "Beat",
                "ordinal": 1,
                "height": 35,
                "components": {
                    b[0]: {
                        "kind": "BEAT",
                        "time": 0,
                        "measure": {"number": 1, "x_mark": "kept"},
                        "beat_unit": {"denominator": 4, "units": "1", "x_unit": 0},
                        "x_beat": "kept",
                    },
                    b[1]: {"kind": "BEAT", "time": 1},
                },
                "x_timeline": "kept",
            },
            markers: {
                "kind": "Marker",
                "name": "Markers",
                "ordinal": 2,
                "height": 30,
                "components": {
                    m[0]: {
                        "kind": "MARKER",
                        "time": 1,
                        "label": "known",
                        "metadata": {"tags": ["x"]},
                        "Y": True,
                        "x_component": {"b": 1, "a": [2, {"d": 3, "c": 4}]},
                    },
                    # Component kinds are read exactly: this isn't a marker.
                    m[1]: {"kind": "marker", "label": "spelled otherwise", "time": 2},
                },
            },
            rows: {
                "kind": "Range",
                "ordinal": 3,
                "height": 60,
                "rows": [{"id": "aZ3k9P", "name": "Row", "x_row": "kept"}],
                "components": {},
            },
            # Kept as it is: nothing left out at a default, its components as
            # they were; its own keys after the ones every timeline has.
            lyrics: {
                "kind": "Lyrics",
                "name": "Lyrics",
                "ordinal": 4,
                "height": 40,
                "is_visible": True,
                "metadata": {"role": "lyrics"},
                "components": {
                    lyric: {"kind": "LYRIC", "time": 1, "text": "Ἀλληλούϊα"},
                },
                "font": "serif",
            },
        },
        "scores": [
            {
                "id": score_id,
                "format": "mei",
                "source": {"file": "a.mei", "x_source": "kept"},
                "license": "NOASSERTION",
                "content": ["<mei/>", ""],
                "x_score": "kept",
            }
        ],
        "Alpha": 1,
        "zeta": {"b": 1, "a": [1, {"d": 2, "c": 3}]},
        "ärger": "kept",
    }


FILES = {"every-kind.tla": every_kind, "empty.tla": empty, "unknown.tla": unknown}


def _check_nfc(value: Any, in_score: bool = False) -> None:
    """Fail if any text outside a score's lines isn't NFC, as the writer would change it."""
    if isinstance(value, str):
        assert in_score or unicodedata.is_normalized("NFC", value), value
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_nfc(key)
            _check_nfc(item, key == "content")
    elif isinstance(value, list):
        for item in value:
            _check_nfc(item, in_score)


def golden_bytes() -> dict[str, bytes]:
    """Each golden file's name and bytes."""
    result = {}
    for name, make in FILES.items():
        content = make()
        _check_nfc(content)
        text = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
        result[name] = text.encode("utf-8")
    return result


def main() -> None:
    for name, data in golden_bytes().items():
        (HERE / name).write_bytes(data)
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
