"""Write the broken files: `.tla` files the reader refuses, one for each way a
file can be broken.

Most are one valid file in the current format, `base()`, with one thing
broken, laid out as the writer lays a file out, so that the line a refusal
names is exact. They are written with `json.dumps` directly, not with
`tilia_core`, so that they don't depend on the code they test.

Run it from anywhere, after changing it: `python make_broken.py`. A test
checks that the files on disk are what it writes.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
VERSION = "1.0.0-draft.1"
BASE_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
BOM = b"\xef\xbb\xbf"


def make_id(n: int) -> str:
    """The n-th id of these files: a UUIDv7, the same on every run."""
    bits = int.from_bytes(hashlib.sha256(f"broken:{n}".encode()).digest()[:10], "big")
    rand_a = bits >> 68
    rand_b = bits & ((1 << 62) - 1)
    value = (BASE_MS + n) << 80 | 7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


# The ids of base(), by name, for the tests to name places with.
IDS = {
    name: make_id(n)
    for n, name in enumerate(
        [
            "document",
            "beats",
            "form",
            "cadences",
            "texture",
            "score_timeline",
            "score",
            "beat_1",
            "beat_2",
            "section",
            "cadence",
            "melody_1",
            "melody_2",
            # Named nowhere in base().
            "nothing",
        ]
    )
}


def base() -> dict[str, Any]:
    """A valid file with every reference the reader follows: a range's row and
    the range it is joined to, a score timeline's score and measure table, and
    the measure table a timeline was imported against."""
    i = IDS
    return {
        "app_name": "TiLiA",
        "version": VERSION,
        "document_id": i["document"],
        "time_unit": "seconds",
        "media": {"path": "", "length": None},
        "metadata": {"title": "Broken"},
        "timelines": {
            i["beats"]: {
                "kind": "Beat",
                "name": "Beats",
                "ordinal": 1,
                "height": 35,
                "components": {
                    i["beat_1"]: {
                        "kind": "BEAT",
                        "time": 0.0,
                        "measure": {},
                        "beat_unit": {"denominator": 4, "units": "1"},
                    },
                    i["beat_2"]: {"kind": "BEAT", "time": 1.0},
                },
            },
            i["form"]: {
                "kind": "Hierarchy",
                "name": "Form",
                "ordinal": 2,
                "height": 60,
                "metadata": {"vocabulary": "lcma-form@0.3.0"},
                "components": {
                    i["section"]: {
                        "kind": "HIERARCHY",
                        "start": 0.0,
                        "end": 2.0,
                        "level": 1,
                        "label": "A",
                    },
                },
            },
            i["cadences"]: {
                "kind": "Marker",
                "name": "Cadences",
                "ordinal": 3,
                "height": 30,
                "measure_table": i["beats"],
                "components": {
                    i["cadence"]: {"kind": "MARKER", "time": 1.0, "label": "PAC"},
                },
            },
            i["texture"]: {
                "kind": "Range",
                "name": "Texture",
                "ordinal": 4,
                "height": 60,
                "rows": [{"id": "aZ3k9P", "name": "Melody"}],
                "components": {
                    i["melody_1"]: {
                        "kind": "RANGE",
                        "start": 0.0,
                        "end": 1.0,
                        "row_id": "aZ3k9P",
                        "joined_right": i["melody_2"],
                    },
                    i["melody_2"]: {
                        "kind": "RANGE",
                        "start": 1.0,
                        "end": 2.0,
                        "row_id": "aZ3k9P",
                    },
                },
            },
            i["score_timeline"]: {
                "kind": "Score",
                "name": "Score",
                "ordinal": 5,
                "height": 100,
                "score": i["score"],
                "measure_table": i["beats"],
                "components": {},
            },
        },
        "scores": [
            {
                "id": i["score"],
                "format": "mei",
                "source": {"file": "a.mei"},
                "content": ["<mei/>", ""],
            }
        ],
    }


def text_of(content: Any) -> str:
    """As the writer lays a file out."""
    return json.dumps(content, indent=2, ensure_ascii=False) + "\n"


def timeline(content: dict[str, Any], name: str) -> dict[str, Any]:
    return content["timelines"][IDS[name]]


def component(content: dict[str, Any], name: str, of: str) -> dict[str, Any]:
    return timeline(content, of)["components"][IDS[name]]


def renamed(entries: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    """`entries` with the key `old` renamed `new`, in its place."""
    return {new if key == old else key: value for key, value in entries.items()}


def _changed(change: Callable[[dict[str, Any]], None]) -> Callable[[], bytes]:
    def make() -> bytes:
        content = copy.deepcopy(base())
        change(content)
        return text_of(content).encode("utf-8")

    return make


def _version(version: str) -> Callable[[dict[str, Any]], None]:
    def change(content: dict[str, Any]) -> None:
        content["version"] = version

    return change


def _component_id(new: str) -> Callable[[dict[str, Any]], None]:
    def change(content: dict[str, Any]) -> None:
        cadences = timeline(content, "cadences")
        cadences["components"] = renamed(cadences["components"], IDS["cadence"], new)

    return change


def _set(
    where: Callable[[dict[str, Any]], dict[str, Any]], key: str, value: Any
) -> Callable[[dict[str, Any]], None]:
    def change(content: dict[str, Any]) -> None:
        where(content)[key] = value

    return change


def _without_level(content: dict[str, Any]) -> None:
    del component(content, "section", of="form")["level"]


def _second_row(row_id: str) -> Callable[[dict[str, Any]], None]:
    def change(content: dict[str, Any]) -> None:
        timeline(content, "texture")["rows"].append({"id": row_id, "name": "Bass"})

    return change


def _unknown_ordinal_as_text(content: dict[str, Any]) -> None:
    form = timeline(content, "form")
    form["kind"] = "Lyrics"
    form["ordinal"] = "2"


def _not_json() -> bytes:
    # The comma after the time unit is missing.
    text = text_of(base()).replace('"seconds",\n', '"seconds"\n', 1)
    return text.encode("utf-8")


def _cut_short() -> bytes:
    # As a scan might find a file while it is being saved.
    text = text_of(base())
    return text[: text.index('"label": "A"') + len('"label": "A')].encode("utf-8")


def _repeated_key() -> bytes:
    # The section's label, given twice.
    text = text_of(base())
    second = ",\n" + " " * 10 + '"label": "B"\n'
    return text.replace('"label": "A"\n', '"label": "A"' + second, 1).encode()


def _error_page() -> bytes:
    # A browser saved an error page under the file's name.
    return b"<!DOCTYPE html>\n<html>\n<title>404 Not Found</title>\n</html>\n"


def _another_program() -> bytes:
    return text_of({"name": "notes", "pages": [1, 2]}).encode("utf-8")


FILES: dict[str, Callable[[], bytes]] = {
    # Not JSON, or not a TiLiA file.
    "not-json.tla": _not_json,
    "cut-short.tla": _cut_short,
    "error-page.tla": _error_page,
    "second-byte-order-mark.tla": lambda: BOM + BOM + text_of(base()).encode(),
    "empty-file.tla": lambda: b"",
    "another-program.tla": _another_program,
    "repeated-key.tla": _repeated_key,
    # Another format version.
    "newer-format.tla": _changed(_version("2.0.0")),
    "older-draft.tla": _changed(_version("1.0.0-draft.0")),
    # A broken structure.
    "component-without-id.tla": _changed(_component_id("")),
    "id-not-a-uuid.tla": _changed(_component_id("7")),
    "id-in-two-timelines.tla": _changed(_component_id(IDS["section"])),
    "time-as-text.tla": _changed(
        _set(lambda c: component(c, "cadence", of="cadences"), "time", "1.0")
    ),
    "level-missing.tla": _changed(_without_level),
    # A null is a missing key: on a required key, refused.
    "time-null.tla": _changed(
        _set(lambda c: component(c, "cadence", of="cadences"), "time", None)
    ),
    # A timeline of a kind the core doesn't know still has its name, ordinal
    # and metadata checked.
    "unknown-kind-ordinal-as-text.tla": _changed(_unknown_ordinal_as_text),
    "metadata-not-an-object.tla": _changed(
        _set(lambda c: timeline(c, "form"), "metadata", ["lcma-form@0.3.0"])
    ),
    "score-without-lines.tla": _changed(_set(lambda c: c["scores"][0], "content", [])),
    # An id used twice: a row's, in its timeline.
    "row-id-twice.tla": _changed(_second_row("aZ3k9P")),
    # A reference that names nothing.
    "row-named-nowhere.tla": _changed(
        _set(lambda c: component(c, "melody_1", of="texture"), "row_id", "Qm7x2L")
    ),
    "joined-to-nothing.tla": _changed(
        _set(
            lambda c: component(c, "melody_1", of="texture"),
            "joined_right",
            IDS["nothing"],
        )
    ),
    "score-named-nowhere.tla": _changed(
        _set(lambda c: timeline(c, "score_timeline"), "score", IDS["nothing"])
    ),
    "score-measure-table-named-nowhere.tla": _changed(
        _set(lambda c: timeline(c, "score_timeline"), "measure_table", IDS["nothing"])
    ),
    "imported-measure-table-named-nowhere.tla": _changed(
        _set(lambda c: timeline(c, "cadences"), "measure_table", IDS["nothing"])
    ),
    "measure-table-not-a-beat-timeline.tla": _changed(
        _set(lambda c: timeline(c, "cadences"), "measure_table", IDS["form"])
    ),
}


def broken_bytes() -> dict[str, bytes]:
    """Each broken file's name and bytes."""
    return {name: make() for name, make in FILES.items()}


def main() -> None:
    for name, data in broken_bytes().items():
        (HERE / name).write_bytes(data)
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
