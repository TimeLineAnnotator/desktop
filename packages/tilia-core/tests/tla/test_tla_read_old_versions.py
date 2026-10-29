"""Reading files from older TiLiA versions: each is migrated in memory to the
current format, with ids that are the same at every read, and the file on
disk is never touched."""

import copy
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
import unicodedata
import uuid
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla.ids import MIGRATED_BASE_MS, derived_document_id, migrated_id
from tilia_core.tla.migrate import old as old_migrations
from tilia_core.tla.migrate import to_1
from tilia_core.tla.model import TIMELINE_KINDS

OLD = Path(__file__).parent / "old"
OLD_FILES = sorted(OLD.glob("*.tla"))

# Each file's version, and its timelines' kinds in their order.
EXPECTED = {
    "0.0.96.tla": ("0.0.96", ["slider", "hierarchy", "marker", "beat"]),
    "0.0.96-saved-by-0.7.0.tla": ("0.7.0", ["slider", "hierarchy", "marker", "beat"]),
    "0.5.15.tla": (
        "0.5.15",
        [
            "slider",
            "hierarchy",
            "marker",
            "beat",
            "harmony",
            "pdf",
            "audiowave",
            "score",
        ],
    ),
    "0.5.15-saved-by-0.7.0.tla": (
        "0.7.0",
        [
            "slider",
            "hierarchy",
            "marker",
            "beat",
            "harmony",
            "pdf",
            "audiowave",
            "score",
        ],
    ),
    "0.5.15.0-many-beats.tla": ("0.5.15.0", ["beat"]),
    "0.6.0-s4-10.tla": ("0.6.0", ["slider", "hierarchy", "beat"]),
    "0.7.0.tla": (
        "0.7.0",
        [
            "slider",
            "hierarchy",
            "marker",
            "beat",
            "harmony",
            "pdf",
            "audiowave",
            "score",
            "range",
        ],
    ),
}
# Files saved by one version, and the same files opened and saved again
# without an edit by TiLiA 0.7.0.
PAIRS = [
    ("0.0.96.tla", "0.0.96-saved-by-0.7.0.tla"),
    ("0.5.15.tla", "0.5.15-saved-by-0.7.0.tla"),
]


@pytest.fixture(params=OLD_FILES, ids=lambda path: path.name)
def old_file(request):
    return request.param


def content_of(path):
    return json.loads(path.read_bytes())


def loads(content):
    return tla.loads(json.dumps(content).encode())


def by_kind(doc, kind):
    return next(tl for tl in doc.timelines.values() if tl.kind == kind)


def old_timeline(content, kind):
    """The old file's timeline of this kind, with its id."""
    return next(
        (key, tl)
        for key, tl in content["timelines"].items()
        if tl["kind"].lower().removesuffix("_timeline") == kind
    )


def keys_in(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from keys_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from keys_in(item)


def test_there_is_a_file_for_each_shape():
    assert [path.name for path in OLD_FILES] == sorted(EXPECTED)


def test_the_readme_says_where_each_file_comes_from():
    readme = (OLD / "README.md").read_text("utf-8")
    for path in OLD_FILES:
        assert f"`{path.name}`" in readme


# Each old file


def test_reads_in_the_current_format(old_file):
    doc = tla.read(old_file)
    version, kinds = EXPECTED[old_file.name]
    assert doc.format_version == version
    timelines = sorted(doc.timelines.values(), key=lambda tl: tl.ordinal)
    assert [tl.kind for tl in timelines] == kinds
    assert [tl.ordinal for tl in timelines] == list(range(1, len(kinds) + 1))
    assert doc.time_unit == "seconds"
    assert doc.app_name == "TiLiA"
    written = tla.canonical_bytes(doc)
    assert json.loads(written)["version"] == tla.FORMAT_VERSION
    assert tla.canonical_bytes(tla.loads(written)) == written


# Digests of the document and of its canonical bytes, so that a difference
# is shown in two short lines.
READ_IN_A_PROCESS = """
import dataclasses, hashlib, sys
from tilia_core import tla
doc = tla.read(sys.argv[1])
print(hashlib.sha256(ascii(dataclasses.asdict(doc)).encode()).hexdigest())
print(hashlib.sha256(tla.canonical_bytes(doc)).hexdigest())
"""


def read_in_a_process(path, seed):
    env = {**os.environ, "PYTHONHASHSEED": seed}
    result = subprocess.run(
        [sys.executable, "-c", READ_IN_A_PROCESS, str(path)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_two_reads_in_two_processes_give_the_same_document(old_file):
    doc = tla.read(old_file)
    here = (
        hashlib.sha256(ascii(dataclasses.asdict(doc)).encode()).hexdigest()
        + "\n"
        + hashlib.sha256(tla.canonical_bytes(doc)).hexdigest()
        + "\n"
    )
    assert read_in_a_process(old_file, "1") == here
    assert read_in_a_process(old_file, "2") == here


def test_reading_leaves_the_file_and_its_folder_as_they_were(old_file, tmp_path):
    copied = tmp_path / old_file.name
    shutil.copyfile(old_file, copied)
    an_old_time = 1_600_000_000_000_000_000
    os.utime(copied, ns=(an_old_time, an_old_time))
    tla.read(copied)
    assert copied.read_bytes() == old_file.read_bytes()
    assert copied.stat().st_mtime_ns == an_old_time
    assert list(tmp_path.iterdir()) == [copied]


def test_no_stored_hash_or_file_path(old_file):
    written = json.loads(tla.canonical_bytes(tla.read(old_file)))
    stored = {"hash", "components_hash", "timelines_hash", "file_path"}
    old_keys = {"media_path", "media_metadata", "display_position"}
    assert not (stored | old_keys) & set(keys_in(written))
    assert "media length" not in written["metadata"]


def test_ids_are_uuid7s_made_from_the_old_ids(old_file):
    doc = tla.read(old_file)
    content = content_of(old_file)
    assert uuid.UUID(doc.document_id).version == 8
    old_of = {}
    for position, old_id in enumerate(content["timelines"]):
        new_id = migrated_id(doc.document_id, "timeline", old_id, position=position)
        old_of[new_id] = old_id
        components = content["timelines"][old_id]["components"]
        expected = {
            migrated_id(doc.document_id, "component", old_id, key, position=index)
            for index, key in enumerate(components)
        }
        timeline = doc.timelines[new_id]
        if timeline.kind != "audiowave":
            assert set(timeline.components) == expected
    assert set(doc.timelines) == set(old_of)
    every_id = list(doc.timelines) + [
        key for tl in doc.timelines.values() for key in tl.components
    ]
    for value in every_id:
        parsed = uuid.UUID(value)
        assert (parsed.version, parsed.variant) == (7, uuid.RFC_4122)
        assert MIGRATED_BASE_MS <= parsed.int >> 80 < MIGRATED_BASE_MS + 2**39
    # Written in id order, the timelines keep the old ids' order.
    assert [old_of[key] for key in doc.timelines] == sorted(old_of.values(), key=int)


def test_media_length_is_a_number_above_zero_or_none(old_file):
    doc = tla.read(old_file)
    stored = content_of(old_file)["media_metadata"].get("media length")
    assert doc.media_length == stored
    assert doc.media_length is None or doc.media_length > 0


def test_formal_type_and_formal_function_are_gone_with_a_warning_each(old_file):
    doc = tla.read(old_file)
    content = content_of(old_file)
    values = [
        (f"/timelines/{tl_id}/components/{c_id}/{key}", component[key])
        for tl_id, tl in content["timelines"].items()
        for c_id, component in tl["components"].items()
        for key in ("formal_type", "formal_function")
        if component.get(key)
    ]
    for tl in doc.timelines.values():
        for component in tl.components.values():
            assert "formal_type" not in component.attrs | component.extra
            assert "formal_function" not in component.attrs | component.extra
    warnings = [w for w in doc.warnings if "formal_" in w.message]
    assert [(w.place, w.message) for w in warnings] == [
        (
            place,
            f'{place.rpartition("/")[2]} {json.dumps(value, ensure_ascii=False)} dropped',
        )
        for place, value in values
    ]


def test_metadata_is_the_old_files_fields_in_their_order(old_file):
    doc = tla.read(old_file)
    fields = dict(content_of(old_file)["media_metadata"])
    fields.pop("media length", None)
    assert list(doc.metadata.items()) == list(fields.items())


def test_amplitude_bars_are_dropped_with_a_warning(old_file):
    doc = tla.read(old_file)
    content = content_of(old_file)
    waves = [
        (key, tl)
        for key, tl in content["timelines"].items()
        if tl["kind"].lower().removesuffix("_timeline") == "audiowave"
    ]
    assert all(
        not tl.components for tl in doc.timelines.values() if tl.kind == "audiowave"
    )
    assert [(w.place, w.message) for w in doc.warnings if "amplitude" in w.message] == [
        (f"/timelines/{key}/components", "3 amplitude bars dropped")
        for key, tl in waves
        if tl["components"]
    ]


def test_copies_keep_the_ids(old_file, tmp_path):
    def ids(doc):
        components = {key for tl in doc.timelines.values() for key in tl.components}
        return doc.document_id, set(doc.timelines), components

    data = old_file.read_bytes()
    other_line_endings = (
        data.replace(b"\r\n", b"\n")
        if b"\r\n" in data
        else data.replace(b"\n", b"\r\n")
    )
    elsewhere = tmp_path / "elsewhere" / "deeper" / old_file.name
    elsewhere.parent.mkdir(parents=True)
    shutil.copyfile(old_file, elsewhere)
    expected = ids(tla.read(old_file))
    assert ids(tla.read(elsewhere)) == expected
    assert ids(tla.loads(other_line_endings)) == expected
    assert ids(tla.loads(b"\xef\xbb\xbf" + data)) == expected


# What particular files hold


def test_display_position_becomes_a_1_based_ordinal():
    doc = tla.read(OLD / "0.0.96.tla")
    content = content_of(OLD / "0.0.96.tla")
    for position, (old_id, old) in enumerate(content["timelines"].items()):
        new_id = migrated_id(doc.document_id, "timeline", old_id, position=position)
        assert doc.timelines[new_id].ordinal == old["display_position"] + 1


def test_rows_keep_their_ids_and_joined_ranges_follow_the_new_ids():
    doc = tla.read(OLD / "0.7.0.tla")
    old_id, old = old_timeline(content_of(OLD / "0.7.0.tla"), "range")
    timeline = by_kind(doc, "range")
    assert timeline.attrs["rows"] == old["rows"]
    joined = 0
    for position, (key, component) in enumerate(old["components"].items()):
        new = timeline.components[
            migrated_id(doc.document_id, "component", old_id, key, position=position)
        ]
        assert new.attrs["row_id"] == component["row_id"]
        if component["joined_right"] is None:
            assert new.attrs["joined_right"] is None
        else:
            joined += 1
            right = list(old["components"]).index(component["joined_right"])
            assert new.attrs["joined_right"] == migrated_id(
                doc.document_id,
                "component",
                old_id,
                component["joined_right"],
                position=right,
            )
            assert new.attrs["joined_right"] in timeline.components
    assert joined == 1


@pytest.mark.parametrize("name, set_apart", [("0.5.15.tla", 1), ("0.7.0.tla", 2)])
def test_pre_start_and_post_end_equal_to_start_and_end_are_left_unset(name, set_apart):
    doc = tla.read(OLD / name)
    content = content_of(OLD / name)
    found = 0
    for old in content["timelines"].values():
        if old["kind"].lower().removesuffix("_timeline") not in ("hierarchy", "range"):
            continue
        timeline = next(tl for tl in doc.timelines.values() if tl.name == old["name"])
        for component in timeline.components.values():
            attrs = component.attrs
            assert "post_end" not in attrs
            if "pre_start" in attrs:
                found += 1
                assert attrs["pre_start"] < attrs["start"]
    assert found == set_apart


def test_the_s4_file_keeps_its_youtube_link_and_fields():
    doc = tla.read(OLD / "0.6.0-s4-10.tla")
    assert doc.media_path == "https://www.youtube.com/watch?v=_ORrftU6sGA"
    assert doc.metadata["analysis license"] == "CC BY 4.0"
    hierarchy = by_kind(doc, "hierarchy")
    assert hierarchy.name == "Form (de Clercq)"
    assert len(hierarchy.components) == 8


# Saved again by TiLiA 0.7 without an edit


@pytest.mark.parametrize(
    "pair",
    [
        pytest.param(
            PAIRS[0],
            marks=pytest.mark.xfail(
                strict=True,
                reason="TiLiA 0.7 fills the beat timeline's empty lists, as the"
                " fitting of TimeLineAnnotator/project-management#181 will",
            ),
        ),
        PAIRS[1],
    ],
    ids=lambda pair: pair[0],
)
def test_a_save_by_tilia_0_7_without_an_edit_keeps_the_ids(pair):
    first, saved = (tla.read(OLD / name) for name in pair)
    assert first.document_id == saved.document_id
    assert tla.canonical_bytes(first) == tla.canonical_bytes(saved)


def with_beat_lists_filled(content):
    """The old file with its beat timeline's empty lists filled, as TiLiA 0.7
    fills them when it opens the file, and as the migration will fit them
    (TimeLineAnnotator/project-management#181)."""
    content = copy.deepcopy(content)
    for timeline in content["timelines"].values():
        if timeline["kind"] == "BEAT_TIMELINE" and not timeline["beats_in_measure"]:
            count = len(timeline["components"]) // timeline["beat_pattern"][0]
            timeline["beats_in_measure"] = timeline["beat_pattern"] * count
            timeline["measure_numbers"] = list(range(1, count + 1))
    return content


def test_a_save_by_tilia_0_7_keeps_the_ids_of_0_0_96s_file_but_for_its_beat_lists():
    # What else TiLiA 0.7 changes in the 0.0.96 file, the migration makes alike:
    # ordinals, kinds, hierarchies' parent and children, pre_start and post_end.
    first, saved = PAIRS[0]
    content = with_beat_lists_filled(content_of(OLD / first))
    assert content != content_of(OLD / first)
    first_doc = loads(content)
    saved_doc = tla.read(OLD / saved)
    assert first_doc.document_id == saved_doc.document_id
    assert tla.canonical_bytes(first_doc) == tla.canonical_bytes(saved_doc)


def test_hierarchies_written_by_tilia_0_0_96_lose_parent_and_children():
    doc = tla.read(OLD / "0.0.96.tla")
    content = content_of(OLD / "0.0.96.tla")
    _, old = old_timeline(content, "hierarchy")
    assert all("parent" in unit for unit in old["components"].values())
    written = json.loads(tla.canonical_bytes(doc))
    assert not {"parent", "children"} & set(keys_in(written))
    # Dropped without a warning: TiLiA computes them.
    assert all("formal_" in warning.message for warning in doc.warnings)


def test_clef_icons_written_by_tilia_0_5_lose_their_svg():
    doc = tla.read(OLD / "0.5.15.tla")
    _, old = old_timeline(content_of(OLD / "0.5.15.tla"), "score")
    assert [c["icon"] for c in old["components"].values() if c["kind"] == "CLEF"] == [
        "clef-treble.svg"
    ]
    clefs = [c for c in by_kind(doc, "score").components.values() if c.kind == "clef"]
    assert [clef.attrs["icon"] for clef in clefs] == ["clef-treble"]


# The migration, on small files


def old_file_content():
    return {
        "file_path": "C:/Users/someone/corpus/piece.tla",
        "media_path": "C:/Users/someone/corpus/piece.mp3",
        "media_metadata": {
            "title": "Piece",
            "notes": "",
            "media length": 120.5,
            "composer": "Dvořák",
        },
        "timelines": {
            "1": {
                "kind": "Hierarchy",
                "name": "Form",
                "ordinal": 1,
                "height": 30,
                "is_visible": True,
                "hash": "0a1b",
                "components_hash": "2c3d",
                "components": {
                    "2": {
                        "start": 0,
                        "pre_start": 0,
                        "end": 10.5,
                        "post_end": 10.5,
                        "level": 1,
                        "label": "Exposição",
                        "color": "",
                        "formal_type": "",
                        "formal_function": "",
                        "comments": "",
                        "kind": "HIERARCHY",
                        "hash": "4e5f",
                    }
                },
            },
            "3": {
                "kind": "Marker",
                "name": "Cadences",
                "ordinal": 2,
                "height": 30,
                "is_visible": True,
                "hash": "6a7b",
                "components_hash": "8c9d",
                "components": {
                    "4": {
                        "time": 5,
                        "comments": "",
                        "label": "PAC",
                        "color": None,
                        "kind": "MARKER",
                        "hash": "0e1f",
                    }
                },
            },
        },
        "timelines_hash": "2a3b",
        "app_name": "TiLiA",
        "version": "0.6.0",
    }


def edited(*changes):
    content = old_file_content()
    for change in changes:
        change(content)
    return content


def set_key(*path_and_value):
    *path, key, value = path_and_value

    def change(content):
        for step in path:
            content = content[step]
        content[key] = value

    return change


def remove_key(*path):
    *path, key = path

    def change(content):
        for step in path:
            content = content[step]
        del content[key]

    return change


HIERARCHY = ("timelines", "1")
UNIT = ("timelines", "1", "components", "2")
MARKER = ("timelines", "3", "components", "4")


def kinds_before_0_7(content):
    content["version"] = "0.5.15"
    content["timelines"]["1"]["kind"] = "HIERARCHY_TIMELINE"
    content["timelines"]["3"]["kind"] = "MARKER_TIMELINE"


def nfd(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFD", value)
    if isinstance(value, dict):
        return {nfd(key): nfd(item) for key, item in value.items()}
    if isinstance(value, list):
        return [nfd(item) for item in value]
    return value


def reorder_timelines(content):
    content["timelines"] = dict(reversed(list(content["timelines"].items())))


def with_wave(*bars):
    def change(content):
        content["timelines"]["9"] = {
            "kind": "AudioWave",
            "name": "",
            "ordinal": 3,
            "height": 80,
            "is_visible": True,
            "components": {
                str(10 + index): {
                    "start": start,
                    "end": end,
                    "amplitude": amplitude,
                    "kind": "AUDIOWAVE",
                }
                for index, (start, end, amplitude) in enumerate(bars)
            },
        }

    return change


@pytest.mark.parametrize(
    "changes",
    [
        [set_key("file_path", "/home/other/elsewhere/piece.tla")],
        [remove_key("file_path")],
        [set_key("version", "0.7.0")],
        [kinds_before_0_7],
        [set_key("app_name", "TiLiA 2")],
        [set_key("timelines_hash", "ffff"), set_key(*UNIT, "hash", "ffff")],
        [remove_key("timelines_hash"), remove_key(*HIERARCHY, "components_hash")],
        [set_key("media_metadata", "media length", 121.0)],
        [remove_key("media_metadata", "media length")],
        # Written at their default, or left out.
        [remove_key(*MARKER, "comments")],
        [remove_key(*UNIT, "color"), remove_key(*UNIT, "comments")],
        [remove_key(*HIERARCHY, "is_visible")],
        [remove_key(*MARKER, "color")],
        [set_key(*MARKER, "time", 5.0)],
        [remove_key(*UNIT, "pre_start"), remove_key(*UNIT, "post_end")],
        [set_key(*UNIT, "pre_start", 0.0)],
        # Dropped by the migration.
        [set_key(*UNIT, "formal_type", "sonata")],
        # Numbers by value, text in NFC, any key order.
        [set_key(*UNIT, "start", 0.0), set_key(*HIERARCHY, "height", 30.0)],
        [lambda content: content.update(nfd(content))],
        [reorder_timelines],
    ],
)
def test_the_document_id_ignores_what_changes_without_an_edit(changes):
    reference = loads(old_file_content())
    changed = loads(edited(*changes))
    assert changed.document_id == reference.document_id


def with_harmony(timeline=None, chord=None):
    def change(content):
        content["timelines"]["9"] = {
            "kind": "Harmony",
            "name": "Chords",
            "ordinal": 3,
            **(timeline or {}),
            "components": {"10": {"kind": "HARMONY", "time": 2, **(chord or {})}},
        }

    return change


@pytest.mark.parametrize("value", [1, 1.0])
def test_attributes_at_their_default_are_left_out_by_value(value):
    # As a version that doesn't write them leaves them out: 1.0 is 1.
    written = with_harmony({"level_count": value}, {"level": value})
    assert (
        loads(edited(written)).document_id == loads(edited(with_harmony())).document_id
    )


def test_the_amplitude_bars_dont_change_the_document_id():
    one = loads(edited(with_wave((0, 1, 0.5))))
    other = loads(edited(with_wave((0, 2, 0.25), (2, 3, 1))))
    assert one.document_id == other.document_id


@pytest.mark.parametrize(
    "change",
    [set_key(*HIERARCHY, "metadata", {}), set_key(*UNIT, "metadata", {})],
    ids=["timeline", "component"],
)
def test_an_empty_metadata_is_left_out_of_the_document_id(change):
    # As the writer leaves it out. No TiLiA version writes a timeline's or a
    # component's metadata: only a file made by hand has an empty one.
    assert loads(edited(change)).document_id == loads(old_file_content()).document_id


@pytest.mark.parametrize(
    "changes",
    [
        [set_key(*UNIT, "label", "Development")],
        [set_key(*UNIT, "start", 0.5)],
        [set_key(*UNIT, "pre_start", -0.5)],
        [set_key(*MARKER, "comments", "a comment")],
        [set_key("media_metadata", "composer", "Dvorak")],
        [set_key("media_metadata", "hash", "a field a user added")],
        [set_key("media_path", "C:/Users/someone/corpus/other.mp3")],
        [set_key(*HIERARCHY, "ordinal", 3)],
        [set_key(*HIERARCHY, "is_visible", False)],
    ],
)
def test_the_document_id_changes_with_an_edit(changes):
    assert loads(edited(*changes)).document_id != loads(old_file_content()).document_id


def test_the_document_id_is_derived_from_the_content_in_the_current_format():
    # With the old ids, and the media's path as the file stores it.
    expected = derived_document_id(
        {
            "time_unit": "seconds",
            "media": {"path": "C:/Users/someone/corpus/piece.mp3"},
            "metadata": {"title": "Piece", "notes": "", "composer": "Dvořák"},
            "timelines": {
                "1": {
                    "kind": "Hierarchy",
                    "name": "Form",
                    "ordinal": 1,
                    "height": 30,
                    "components": {
                        "2": {
                            "kind": "HIERARCHY",
                            "start": 0,
                            "end": 10.5,
                            "level": 1,
                            "label": "Exposição",
                        }
                    },
                },
                "3": {
                    "kind": "Marker",
                    "name": "Cadences",
                    "ordinal": 2,
                    "height": 30,
                    "components": {"4": {"kind": "MARKER", "time": 5, "label": "PAC"}},
                },
            },
            "scores": [],
        }
    )
    assert loads(old_file_content()).document_id == expected


def test_the_new_ids_come_from_the_document_id_and_the_old_ids():
    doc = loads(old_file_content())
    hierarchy = migrated_id(doc.document_id, "timeline", "1", position=0)
    marker = migrated_id(doc.document_id, "timeline", "3", position=1)
    assert list(doc.timelines) == [hierarchy, marker]
    unit = migrated_id(doc.document_id, "component", "1", "2", position=0)
    assert list(doc.timelines[hierarchy].components) == [unit]
    assert doc.timelines[hierarchy].components[unit].attrs["label"] == "Exposição"


def test_old_ids_that_arent_integers_sort_after_the_others_in_their_order():
    content = old_file_content()
    unit = content["timelines"]["1"]["components"].pop("2")
    content["timelines"]["1"]["components"] = {
        "b": {**unit, "start": 2, "end": 3},
        "7": {**unit, "start": 1, "end": 2},
        "a": {**unit, "start": 0, "end": 1},
    }
    doc = loads(content)
    components = list(by_kind(doc, "hierarchy").components.values())
    assert [c.attrs["start"] for c in components] == [1, 2, 0]


def test_old_timeline_ids_that_arent_integers_sort_after_the_others_in_order():
    content = old_file_content()
    hierarchy, marker = content["timelines"]["1"], content["timelines"]["3"]
    content["timelines"] = {
        "b": hierarchy,
        "7": {**copy.deepcopy(marker), "name": "Seven", "ordinal": 3},
        "a": marker,
    }
    doc = loads(content)
    # Each takes its position in the file, which only the ids of old ids
    # that aren't integers depend on.
    assert list(doc.timelines) == [
        migrated_id(doc.document_id, "timeline", "7", position=1),
        migrated_id(doc.document_id, "timeline", "b", position=0),
        migrated_id(doc.document_id, "timeline", "a", position=2),
    ]
    assert [tl.name for tl in doc.timelines.values()] == ["Seven", "Form", "Cadences"]


# Versions


@pytest.mark.parametrize(
    "version, format_version",
    [
        ("0.6.0", "0.6.0"),
        ("0.7.0rc1", "0.7.0rc1"),
        ("0.5.15.0", "0.5.15.0"),
        ("0", "0"),
        ("", ""),
        (None, "0.0.0"),
    ],
)
def test_old_versions_are_read_through_the_migration(version, format_version):
    content = old_file_content()
    if version is None:
        del content["version"]
    else:
        content["version"] = version
    doc = loads(content)
    assert doc.format_version == format_version
    assert len(doc.timelines) == 2


@pytest.mark.parametrize(
    "version, expected",
    [
        ("0.7.0rc1", "0.7.0"),
        ("0.5.15.0", "0.5.15.0"),
        ("0.10", "0.10"),
        ("", "0"),
        ("abc", "0"),
        ("1.x.3", "1"),
        ("٣.0", "0"),
        ("0." + "9" * 5000, "0." + "9" * 5000),
    ],
)
def test_versions_compare_as_tilia_compares_them(version, expected):
    assert old_migrations.version_key(version) == old_migrations.version_key(expected)


def test_versions_compare_by_number():
    key = old_migrations.version_key
    assert key("0.1.1") < key("0.7.0") < key("0.10.0") < key("0." + "1" * 5000)
    assert key("0.7") < key("0.7.0")
    assert key("0.07.0") == key("0.7.0")


def timeline_without_ordinal(version, **keys):
    content = old_file_content()
    content["version"] = version
    content["timelines"]["1"].pop("ordinal")
    content["timelines"]["3"].pop("ordinal")
    content["timelines"]["1"].update(keys)
    content["timelines"]["3"]["display_position"] = 0
    return content


@pytest.mark.parametrize("version", ["0.0.1", "0.0.96", "0.1.0", "0.1.1", None])
def test_display_position_becomes_ordinal_up_to_tilia_0_1_1(version):
    # TiLiA 0.1.1 itself still wrote display_position.
    content = timeline_without_ordinal(version or "", display_position=1)
    if version is None:
        del content["version"]
    doc = loads(content)
    assert [tl.ordinal for tl in doc.timelines.values()] == [2, 1]
    assert all("display_position" not in tl.extra for tl in doc.timelines.values())


def test_display_position_stays_where_a_file_has_its_ordinals():
    content = old_file_content()
    content["version"] = "0.1.1"
    doc = loads(content)
    assert [tl.ordinal for tl in doc.timelines.values()] == [1, 2]


def test_kind_names_change_below_0_7_as_tilia_changes_them():
    content = edited(kinds_before_0_7)
    content["timelines"]["5"] = {
        "kind": "AUDIOWAVE_TIMELINE",
        "ordinal": 3,
        "height": 80,
        "components": {},
    }
    content["timelines"]["6"] = {"kind": "LYRICS_TIMELINE", "ordinal": 4, "words": []}
    doc = loads(content)
    assert [tl.kind for tl in doc.timelines.values()] == [
        "hierarchy",
        "marker",
        "audiowave",
        tla.UnknownKind("Lyrics"),
    ]
    written = json.loads(tla.canonical_bytes(doc))
    assert [tl["kind"] for tl in written["timelines"].values()] == [
        "Hierarchy",
        "Marker",
        "AudioWave",
        "Lyrics",
    ]


@pytest.mark.parametrize(
    "version, spelling",
    [
        ("0.7.0", "Marker"),
        ("0.7.0", "marker"),
        ("0.7.0", "MARKER"),
        ("0.7.0", "MARKER_TIMELINE"),
        ("0.7.2", "Marker_TIMELINE"),
        ("0.5.15", "MARKER_TIMELINE"),
        ("0.5.15", "marker"),
    ],
)
def test_the_migration_spells_known_kinds_exactly(version, spelling):
    # In any letter case, and with the suffix TiLiA before 0.7 wrote, only in
    # old files: the current format's kinds are read exactly.
    content = old_file_content()
    content["version"] = version
    content["timelines"]["3"]["kind"] = spelling
    migrated = to_1.migrate(content)
    kinds = [tl["kind"] for tl in migrated.content["timelines"].values()]
    assert kinds == ["Hierarchy", "Marker"]


@pytest.mark.parametrize(
    "version, spelling",
    [
        ("0.5.15", "AUDIOWAVE_TIMELINE"),  # "Audiowave" after TiLiA's migration
        ("0.7.0", "Audiowave"),
        ("0.7.0", "AUDIOWAVE"),
        ("0.7.0", "AudioWave"),
    ],
)
def test_the_migration_spells_audiowave_exactly(version, spelling):
    content = edited(with_wave())
    content["version"] = version
    content["timelines"]["9"]["kind"] = spelling
    migrated = to_1.migrate(content)
    assert [tl["kind"] for tl in migrated.content["timelines"].values()] == [
        "Hierarchy",
        "Marker",
        "AudioWave",
    ]


def test_old_files_kinds_come_out_in_the_formats_spelling(old_file):
    # The current format's reader reads kinds exactly: an old file's come out
    # of the migration as the format spells them, whatever the file's spelling.
    migrated = to_1.migrate(content_of(old_file))
    timelines = sorted(
        migrated.content["timelines"].values(), key=lambda tl: tl["ordinal"]
    )
    _, kinds = EXPECTED[old_file.name]
    assert [tl["kind"] for tl in timelines] == [TIMELINE_KINDS[k] for k in kinds]


# What TiLiA 0.7 changes when it opens an old file


def with_unit_keys(**keys):
    def change(content):
        content["timelines"]["1"]["components"]["2"].update(keys)

    return change


@pytest.mark.parametrize("version", ["0.0.96", "0.5.5", "0.6.0", "0.7.0"])
def test_hierarchies_lose_parent_and_children_without_a_warning(version):
    # Written before 0.5.6; TiLiA computes them from levels and times.
    content = edited(with_unit_keys(parent=None, children=["5"], analyst_note="x"))
    content["version"] = version
    doc = loads(content)
    unit = next(iter(by_kind(doc, "hierarchy").components.values()))
    assert unit.extra == {"analyst_note": "x"}
    assert "parent" not in unit.attrs and "children" not in unit.attrs
    assert doc.warnings == []
    without = loads(
        edited(with_unit_keys(analyst_note="x"), set_key("version", version))
    )
    assert doc.document_id == without.document_id


def test_parent_and_children_stay_where_they_arent_a_hierarchys():
    content = old_file_content()
    content["timelines"]["3"]["components"]["4"]["parent"] = "2"
    content["timelines"]["7"] = {
        "kind": "Lyrics",
        "ordinal": 3,
        "components": {"8": {"kind": "HIERARCHY", "parent": None, "children": []}},
    }
    doc = loads(content)
    marker = next(iter(by_kind(doc, "marker").components.values()))
    assert marker.extra == {"parent": "2"}
    lyrics = by_kind(doc, tla.UnknownKind("Lyrics"))
    assert lyrics.raw["components"]["8"] == {
        "kind": "HIERARCHY",
        "parent": None,
        "children": [],
    }


def with_score(*components):
    def change(content):
        content["timelines"]["7"] = {
            "kind": "Score",
            "name": "Score",
            "ordinal": 3,
            "height": 160,
            "components": {str(10 + index): c for index, c in enumerate(components)},
        }

    return change


def clef(icon):
    return {
        "kind": "CLEF",
        "staff_index": 0,
        "time": 0,
        "line_number": 2,
        "step": 4,
        "octave": 4,
        "icon": icon,
    }


@pytest.mark.parametrize(
    "icon, read",
    [
        ("clef-treble.svg", "clef-treble"),
        ("clef-bass.svg", "clef-bass"),
        ("clef-alto.svg", "clef-alto"),
        ("clef-treble-8vb.svg", "clef-treble-8vb"),
        ("clef-treble", "clef-treble"),
        (None, None),
    ],
)
def test_clef_icons_lose_their_svg(icon, read):
    doc = loads(edited(with_score(clef(icon))))
    (component,) = by_kind(doc, "score").components.values()
    assert component.attrs["icon"] == read
    as_tilia_0_7_saves_it = loads(edited(with_score(clef(read))))
    assert doc.document_id == as_tilia_0_7_saves_it.document_id


def test_icons_of_what_isnt_a_clef_stay():
    staff = {"kind": "STAFF", "line_count": 5, "index": 0, "icon": "staff.svg"}
    doc = loads(edited(with_score(staff)))
    (component,) = by_kind(doc, "score").components.values()
    assert component.extra == {"icon": "staff.svg"}


# The height TiLiA 0.7.0 gives a timeline whose file has none
# (`Timeline.__init__`: `height or self.default_height or 1`): its kind's
# default height as TiLiA 0.7.0 ships its settings, or 1 for a kind without
# one. TimeLineAnnotator/project-management#312.
TILIA_0_7_HEIGHTS = {
    "slider": 40,
    "hierarchy": 120,
    "marker": 30,
    "beat": 35,
    "pdf": 30,
    "audiowave": 80,
    "score": 1,
    "range": 1,
}
MISSING = object()


def with_timeline_of_kind(kind, height=MISSING):
    def change(content):
        timeline = {"kind": TIMELINE_KINDS[kind], "name": "Added", "ordinal": 3}
        if height is not MISSING:
            timeline["height"] = height
        if kind == "range":
            timeline["rows"] = []
        if kind == "pdf":
            timeline["path"] = ""
        timeline["components"] = {}
        content["timelines"]["9"] = timeline

    return change


def added(doc):
    return next(tl for tl in doc.timelines.values() if tl.name == "Added")


@pytest.mark.parametrize(
    "height", [MISSING, None, 0, 0.0], ids=["missing", "null", "0", "0.0"]
)
@pytest.mark.parametrize("kind", list(TILIA_0_7_HEIGHTS))
def test_a_timeline_without_a_height_gets_tilia_0_7s(kind, height):
    # TiLiA 0.7 reads a null or 0 as no height.
    doc = loads(edited(with_timeline_of_kind(kind, height)))
    assert added(doc).kind == kind
    assert added(doc).attrs["height"] == TILIA_0_7_HEIGHTS[kind]
    assert doc.warnings == []


@pytest.mark.parametrize("kind", list(TILIA_0_7_HEIGHTS))
def test_a_filled_in_height_keeps_the_id_of_tilia_0_7s_save(kind):
    # Saved again by TiLiA 0.7, the file has the height filled in.
    filled = loads(edited(with_timeline_of_kind(kind))).document_id
    saved = loads(edited(with_timeline_of_kind(kind, TILIA_0_7_HEIGHTS[kind])))
    other = loads(edited(with_timeline_of_kind(kind, TILIA_0_7_HEIGHTS[kind] + 1)))
    assert filled == saved.document_id != other.document_id


@pytest.mark.parametrize("height", [1, 7, 25, 35.0, -5])
def test_a_height_is_kept_as_it_is(height):
    doc = loads(edited(with_timeline_of_kind("beat", height)))
    assert added(doc).attrs["height"] == height


def test_a_harmony_timeline_gets_no_height():
    # Its levels have one.
    doc = loads(edited(with_harmony()))
    written = json.loads(tla.canonical_bytes(doc))
    harmony = next(
        tl for tl in written["timelines"].values() if tl["kind"] == "Harmony"
    )
    assert "height" not in harmony


def with_slider(content):
    content["timelines"]["0"] = {
        "kind": "Slider",
        "ordinal": 3,
        "height": 40,
        "is_visible": True,
        "components": {},
    }


def with_lyrics_at(ordinal):
    def change(content):
        content["timelines"]["7"] = {"kind": "Lyrics", "ordinal": ordinal}
        if ordinal == 1:
            content["timelines"]["1"]["ordinal"] = 2
            content["timelines"]["3"]["ordinal"] = 3

    return change


@pytest.mark.parametrize(
    "before, after",
    [
        ([], [with_slider]),
        ([with_lyrics_at(1)], [with_lyrics_at(3)]),
        ([], [set_key("media_path", "")]),
    ],
    ids=["slider added", "unknown kind moved last", "media path cleared"],
)
def test_what_else_tilia_0_7_changes_on_saving_changes_the_id(before, after):
    # Saved again by TiLiA 0.7 without an edit, a file without a slider
    # timeline gains one, timelines of kinds TiLiA doesn't know move after the
    # others, and a media path TiLiA can't find (and isn't shown) is cleared.
    # These change the document id, as accepted in
    # TimeLineAnnotator/project-management#312.
    assert loads(edited(*before)).document_id != loads(edited(*after)).document_id


# Keys and kinds the core doesn't know


def test_a_timeline_of_an_unknown_kind_keeps_its_content_under_a_new_id():
    content = old_file_content()
    lyrics = {
        "kind": "Lyrics",
        "name": "Words",
        "ordinal": 3,
        "hash": "3c4d",
        "components_hash": "5e6f",
        "components": {"8": {"kind": "WORD", "time": 1, "text": "Ah", "hash": "7a8b"}},
        "font": "serif",
    }
    content["timelines"]["7"] = copy.deepcopy(lyrics)
    doc = loads(content)
    timeline = doc.timelines[migrated_id(doc.document_id, "timeline", "7", position=2)]
    assert timeline.kind == tla.UnknownKind("Lyrics")
    # TiLiA's stored hashes, the timeline's and its components'.
    del lyrics["hash"], lyrics["components_hash"], lyrics["components"]["8"]["hash"]
    assert timeline.raw == lyrics


def with_lyrics(components):
    def change(content):
        content["timelines"]["7"] = {
            "kind": "Lyrics",
            "name": "Words",
            "ordinal": 3,
            "components": components,
        }

    return change


def word(stored_hash):
    return {"kind": "WORD", "time": 1, "text": "Ah", "hash": stored_hash}


def test_a_timeline_of_an_unknown_kind_loses_its_components_stored_hashes():
    # As in a timeline of a known kind: TiLiA stores them, and they change
    # without an edit.
    one = edited(with_lyrics({"8": word("aaaa")}))
    other = edited(with_lyrics({"8": word("bbbb")}))
    assert loads(one).document_id == loads(other).document_id
    migrated = to_1.migrate(one)
    assert "hash" not in set(keys_in(migrated.content["timelines"]))
    lyrics = by_kind(loads(other), tla.UnknownKind("Lyrics"))
    assert lyrics.raw["components"] == {"8": {"kind": "WORD", "time": 1, "text": "Ah"}}


@pytest.mark.parametrize(
    "components", [{"8": "Ah"}, {"8": ["Ah"]}, ["Ah"], "Ah"], ids=repr
)
def test_a_timeline_of_an_unknown_kind_keeps_components_that_arent_objects(
    components,
):
    doc = loads(edited(with_lyrics(copy.deepcopy(components))))
    assert by_kind(doc, tla.UnknownKind("Lyrics")).raw["components"] == components


def test_keys_the_core_doesnt_know_are_kept():
    content = old_file_content()
    content["corpus"] = {"name": "s4"}
    content["timelines"]["1"]["colour_scheme"] = "dark"
    content["timelines"]["1"]["components"]["2"]["analyst_note"] = ["5"]
    doc = loads(content)
    assert doc.extra == {"corpus": {"name": "s4"}}
    hierarchy = by_kind(doc, "hierarchy")
    assert hierarchy.extra == {"colour_scheme": "dark"}
    unit = next(iter(hierarchy.components.values()))
    assert unit.extra == {"analyst_note": ["5"]}


def test_a_component_of_an_unknown_kind_gets_a_new_id_and_stays_as_it_was():
    content = old_file_content()
    content["timelines"]["1"]["components"]["5"] = {
        "kind": "LCMA_FORM",
        "start": 0,
        "annotation_data": {"form": "AABA"},
        "hash": "9c0d",
    }
    doc = loads(content)
    component = by_kind(doc, "hierarchy").components[
        migrated_id(doc.document_id, "component", "1", "5", position=1)
    ]
    assert component.kind == tla.UnknownKind("LCMA_FORM")
    assert component.extra == {"start": 0, "annotation_data": {"form": "AABA"}}


# The file's fields and the media


@pytest.mark.parametrize(
    "value, expected",
    [
        (120.5, 120.5),
        (1000, 1000),
        ("120.5", 120.5),
        (" 7 ", 7.0),
        (0, None),
        (0.0, None),
        ("0", None),
        (-1, None),
        ("", None),
        ("2:00", None),
        ("nan", None),
        ("inf", None),
        ("1e999", None),
        (None, None),
        (True, None),
        ([120], None),
    ],
)
def test_the_media_length(value, expected):
    doc = loads(edited(set_key("media_metadata", "media length", value)))
    assert doc.media_length == expected
    assert type(doc.media_length) is type(expected)
    assert "media length" not in doc.metadata


def test_no_media_length_is_none():
    doc = loads(edited(remove_key("media_metadata", "media length")))
    assert doc.media_length is None


def test_the_media_path_is_made_relative_and_a_missing_one_is_empty():
    # Relative from the old file_path's folder: the other cases are in
    # test_tla_migrate_media.py.
    assert loads(old_file_content()).media_path == "piece.mp3"
    assert loads(edited(remove_key("media_path"))).media_path == ""


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Dvořák", "Dvořák"),
        ("", ""),
        (1787, "1787"),
        (17.5, "17.5"),
        (True, "true"),
        (False, "false"),
        (None, ""),
        (["a", 1, None, False], ["a", "1", "", "false"]),
        ([], []),
        ({"born": 1841}, '{"born": 1841}'),
        ([["a"], "b"], '[["a"], "b"]'),
    ],
)
def test_metadata_values_become_text(value, expected):
    doc = loads(edited(set_key("media_metadata", "composer", value)))
    assert doc.metadata["composer"] == expected


def test_metadata_keeps_its_order_and_its_empty_fields():
    content = old_file_content()
    content["media_metadata"] = {"z": "", "media length": 3, "a": 1, "m": ""}
    assert list(loads(content).metadata.items()) == [("z", ""), ("a", "1"), ("m", "")]


def test_a_file_without_fields_has_empty_metadata():
    doc = loads(edited(remove_key("media_metadata")))
    assert doc.metadata == {}
    assert doc.media_length is None


# Beat timelines


def with_beats(**keys):
    def change(content):
        content["timelines"]["9"] = {
            "kind": "Beat",
            "name": "Measures",
            "ordinal": 3,
            "height": 35,
            **keys,
            "components": {"10": {"time": 0.0, "kind": "BEAT"}},
        }

    return change


@pytest.mark.parametrize(
    "pattern, text",
    [
        ([4], "4"),
        ([4, 4, 3], "4 4 3"),
        ([3], "3"),
        ([2, 3], "2 3"),
        # Never written by TiLiA: kept as text, which a pattern that doesn't
        # parse is (FR-084).
        ([], ""),
        ([4, "x"], "4 x"),
        ([4, None, True], "4  true"),
    ],
)
def test_a_beat_pattern_becomes_text(pattern, text):
    # contracts/migration.md, *Beat timelines*, step 6: as desktop#621 joins
    # a list, which it reads as the same pattern.
    doc = loads(edited(with_beats(beat_pattern=pattern)))
    assert by_kind(doc, "beat").attrs["beat_pattern"] == text
    written = json.loads(tla.canonical_bytes(doc))
    beat = next(tl for tl in written["timelines"].values() if tl["kind"] == "Beat")
    assert beat.get("beat_pattern", "4") == text


@pytest.mark.parametrize("pattern", ["3 4", None])
def test_a_beat_pattern_that_isnt_a_list_stays(pattern):
    doc = loads(edited(with_beats(beat_pattern=pattern)))
    assert by_kind(doc, "beat").attrs["beat_pattern"] == (pattern or "4")


def test_a_beat_pattern_becomes_text_before_the_document_id_is_derived():
    # [4] is "4", the default, so it is left out, as TiLiA 0.7 writing it
    # would be.
    with_list = loads(edited(with_beats(beat_pattern=[4])))
    without = loads(edited(with_beats()))
    assert with_list.document_id == without.document_id
    assert (
        with_list.document_id != loads(edited(with_beats(beat_pattern=[3]))).document_id
    )


def test_only_beat_timelines_have_their_beat_pattern_changed():
    content = old_file_content()
    content["timelines"]["3"]["beat_pattern"] = [4, 3]
    marker = by_kind(loads(content), "marker")
    assert marker.extra == {"beat_pattern": [4, 3]}


# What the migration drops


def test_each_non_empty_formal_value_is_dropped_with_a_warning():
    content = old_file_content()
    unit = content["timelines"]["1"]["components"]["2"]
    unit["formal_type"] = "sonata form"
    unit["formal_function"] = None
    content["timelines"]["1"]["components"]["3"] = {
        **unit,
        "start": 10.5,
        "end": 20,
        "formal_type": "",
        "formal_function": "exposição",
    }
    doc = loads(content)
    for component in by_kind(doc, "hierarchy").components.values():
        assert not {"formal_type", "formal_function"} & set(component.attrs)
        assert not {"formal_type", "formal_function"} & set(component.extra)
    assert [(w.place, w.line, w.message) for w in doc.warnings] == [
        (
            "/timelines/1/components/2/formal_type",
            None,
            'formal_type "sonata form" dropped',
        ),
        (
            "/timelines/1/components/3/formal_function",
            None,
            'formal_function "exposição" dropped',
        ),
    ]


def test_only_hierarchies_lose_formal_values():
    content = old_file_content()
    content["timelines"]["3"]["components"]["4"]["formal_type"] = "cadence"
    doc = loads(content)
    marker = next(iter(by_kind(doc, "marker").components.values()))
    assert marker.extra == {"formal_type": "cadence"}
    assert doc.warnings == []


@pytest.mark.parametrize(
    "count, message", [(1, "1 amplitude bar dropped"), (2, "2 amplitude bars dropped")]
)
def test_amplitude_bars_are_dropped_with_one_warning(count, message):
    bars = [(index, index + 1, 0.5) for index in range(count)]
    doc = loads(edited(with_wave(*bars)))
    assert by_kind(doc, "audiowave").components == {}
    assert [(w.place, w.message) for w in doc.warnings] == [
        ("/timelines/9/components", message)
    ]


def test_an_audiowave_timeline_without_bars_has_no_warning():
    doc = loads(edited(with_wave()))
    assert doc.warnings == []


# What the migration refuses


@pytest.mark.parametrize(
    "change, place, message",
    [
        (set_key("timelines", []), "/timelines", "expected an object at /timelines"),
        (
            set_key("timelines", "1", 5),
            "/timelines/1",
            "expected an object at /timelines/1",
        ),
        (remove_key(*HIERARCHY, "kind"), "/timelines/1/kind", '"kind" is missing'),
        (
            set_key(*HIERARCHY, "kind", 4),
            "/timelines/1/kind",
            "expected text at /timelines/1/kind",
        ),
        (
            remove_key(*HIERARCHY, "ordinal"),
            "/timelines/1/ordinal",
            '"ordinal" is missing',
        ),
        (
            remove_key(*HIERARCHY, "components"),
            "/timelines/1/components",
            '"components" is missing',
        ),
        (
            set_key(*HIERARCHY, "components", []),
            "/timelines/1/components",
            "expected an object at /timelines/1/components",
        ),
        (
            set_key(*UNIT[:-1], "2", "x"),
            "/timelines/1/components/2",
            "expected an object at /timelines/1/components/2",
        ),
        (
            remove_key(*UNIT, "kind"),
            "/timelines/1/components/2/kind",
            '"kind" is missing',
        ),
        (
            set_key(*UNIT, "kind", None),
            "/timelines/1/components/2/kind",
            "expected text at /timelines/1/components/2/kind",
        ),
        (set_key("media_path", 3), "/media_path", "expected text at /media_path"),
        (
            set_key("media_metadata", ["a"]),
            "/media_metadata",
            "expected an object at /media_metadata",
        ),
        (
            set_key("metadata", {}),
            "/metadata",
            'a file from TiLiA 0.6.0 can\'t hold "metadata", a key of the current format',
        ),
        (
            set_key("scores", []),
            "/scores",
            'a file from TiLiA 0.6.0 can\'t hold "scores", a key of the current format',
        ),
    ],
)
def test_a_broken_old_file_is_refused_naming_the_place(change, place, message):
    with pytest.raises(tla.UnreadableFile) as error:
        loads(edited(change))
    assert (error.value.place, error.value.message) == (place, message)


@pytest.mark.parametrize("value", ["1", 1.0, True, None])
def test_a_display_position_that_isnt_an_integer_is_refused(value):
    content = timeline_without_ordinal("0.0.96", display_position=value)
    with pytest.raises(tla.UnreadableFile) as error:
        loads(content)
    assert error.value.place == "/timelines/1/display_position"
    assert error.value.message == "expected an integer at /timelines/1/display_position"


@pytest.mark.parametrize("version", ["0.0.96", "0.1.1", "0.6.0", "0.7.0"])
@pytest.mark.parametrize(
    "change, message",
    [
        (remove_key(*HIERARCHY, "ordinal"), '"ordinal" is missing'),
        (
            set_key(*HIERARCHY, "ordinal", None),
            '"ordinal" should be an integer, not null',
        ),
    ],
    ids=["missing", "null"],
)
def test_a_timeline_without_an_ordinal_is_refused_at_its_old_place(
    change, message, version
):
    # TiLiA 0.7 would give it the next ordinal, but TiLiA has written one in
    # every file since 0.1.1: only a file edited by hand lacks one, and the
    # migration doesn't fill it in as it fills in a height.
    with pytest.raises(tla.UnreadableFile) as error:
        loads(edited(change, set_key("version", version)))
    assert (error.value.place, error.value.message) == ("/timelines/1/ordinal", message)


# The migrated content, checked as a file of the current format is (FR-053):
# its places are the migrated document's, with the new ids, and have no line.


def migrated_place(content, timeline, *rest):
    """The place in the migrated document of what the old file has under
    timeline `timeline` and, when `rest` starts with "components", under its
    component `rest[1]`."""
    document_id = to_1.migrate(copy.deepcopy(content)).content["document_id"]
    timelines = list(content["timelines"])
    steps = [
        "timelines",
        migrated_id(
            document_id, "timeline", timeline, position=timelines.index(timeline)
        ),
    ]
    if rest[:1] == ("components",):
        component = rest[1]
        components = list(content["timelines"][timeline]["components"])
        steps += [
            "components",
            migrated_id(
                document_id,
                "component",
                timeline,
                component,
                position=components.index(component),
            ),
        ]
        rest = rest[2:]
    return "/" + "/".join([*steps, *rest])


def with_range(**first):
    """A range timeline "9" with one row and two ranges, "10" with the keys
    `first` and "11" after it, as TiLiA 0.7.0 writes them."""

    def change(content):
        content["version"] = "0.7.0"
        content["timelines"]["9"] = {
            "kind": "Range",
            "name": "Rows",
            "ordinal": 3,
            "height": 1,
            "rows": [{"id": "r", "name": "Row", "color": None, "height": None}],
            "components": {
                "10": {"kind": "RANGE", "start": 0, "end": 1, "row_id": "r", **first},
                "11": {"kind": "RANGE", "start": 1, "end": 2, "row_id": "r"},
            },
        }

    return change


RANGE = ("timelines", "9")


@pytest.mark.parametrize(
    "changes, place, message",
    [
        (
            [set_key(*HIERARCHY, "ordinal", "1")],
            ("1", "ordinal"),
            '"ordinal" should be an integer, not text',
        ),
        (
            [set_key(*HIERARCHY, "height", "x")],
            ("1", "height"),
            '"height" should be an integer, not text',
        ),
        # Not a number to the core, though TiLiA 0.7 reads it as no height.
        (
            [set_key(*HIERARCHY, "height", False)],
            ("1", "height"),
            '"height" should be an integer, not true or false',
        ),
        (
            [set_key(*MARKER, "time", "3")],
            ("3", "components", "4", "time"),
            '"time" should be a number, not text',
        ),
        (
            [with_range(), set_key(*RANGE, "rows", {"a": 1})],
            ("9", "rows"),
            '"rows" should be a list, not an object',
        ),
        (
            [with_range(joined_right="99")],
            ("9", "components", "10", "joined_right"),
            '"joined_right" isn\'t a UUID: "99"',
        ),
        (
            [with_range(row_id="s")],
            ("9", "components", "10", "row_id"),
            'a range names row "s", which its timeline doesn\'t have',
        ),
    ],
)
def test_the_migrated_content_is_checked(changes, place, message):
    content = edited(*changes)
    with pytest.raises(tla.UnreadableFile) as error:
        loads(content)
    assert error.value.message == message
    assert error.value.place == migrated_place(content, *place)
    assert error.value.line is None


def test_the_checks_warnings_come_after_the_migrations():
    content = old_file_content()
    content["timelines"]["1"]["components"]["2"]["formal_type"] = "sonata form"
    content["timelines"]["1"]["components"]["5"] = {"kind": "MARKER", "time": 1}
    doc = loads(content)
    assert [(w.place, w.line, w.message) for w in doc.warnings] == [
        (
            "/timelines/1/components/2/formal_type",
            None,
            'formal_type "sonata form" dropped',
        ),
        (
            migrated_place(content, "1", "components", "5"),
            None,
            'the timeline "Form" holds a component of kind "MARKER", which a'
            ' timeline of kind "Hierarchy" doesn\'t have: it is kept as it is',
        ),
    ]


def test_an_integer_written_with_a_fraction_is_read_as_one():
    # As in a file of the current format: the check makes it an integer.
    doc = loads(
        edited(set_key(*HIERARCHY, "ordinal", 1.0), set_key(*UNIT, "level", 1.0))
    )
    hierarchy = by_kind(doc, "hierarchy")
    assert type(hierarchy.ordinal) is int
    (unit,) = hierarchy.components.values()
    assert type(unit.attrs["level"]) is int


def test_old_files_have_no_warnings_but_the_migrations(old_file):
    # Every place a warning names is in the old file, with its old ids.
    doc = tla.read(old_file)
    content = content_of(old_file)
    for warning in doc.warnings:
        timeline = warning.place.split("/")[2]
        assert timeline in content["timelines"]


# Ranges


def test_a_joined_right_written_as_an_integer_follows_the_new_ids():
    # TiLiA writes it as text: range timelines came with TiLiA 0.7.0, whose
    # ids are text. Only a file edited by hand has an integer.
    doc = loads(edited(with_range(joined_right=11)))
    first = migrated_id(doc.document_id, "component", "9", "10", position=0)
    second = migrated_id(doc.document_id, "component", "9", "11", position=1)
    ranges = by_kind(doc, "range").components
    assert ranges[first].attrs["joined_right"] == second


def rows(*rows):
    return set_key(*RANGE, "rows", list(rows))


def test_a_row_at_its_defaults_is_left_out_of_the_document_id():
    # TiLiA 0.7 writes every row's color and height, null when unset.
    written = loads(edited(with_range())).document_id
    left_out = edited(with_range(), rows({"id": "r", "name": "Row"}))
    assert loads(left_out).document_id == written
    coloured = edited(with_range(), rows({"id": "r", "name": "Row", "color": "#f00"}))
    assert loads(coloured).document_id != written


def test_a_missing_app_name_is_tilias():
    doc = loads(edited(remove_key("app_name")))
    assert doc.app_name == "TiLiA"
    assert doc.document_id == loads(old_file_content()).document_id
