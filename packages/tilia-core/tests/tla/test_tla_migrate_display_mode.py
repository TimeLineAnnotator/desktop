"""TiLiA 0.5's harmonies hold a `display_mode` of `chord`, which drew a chord
symbol: the migration writes `letter` for it, on harmonies only, counts it,
and warns of nothing (contracts/migration.md, *Changes the migration makes*;
TimeLineAnnotator/project-management#430)."""

import copy
import json
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.commands import migrate as migrate_command
from tilia_core.tla.migrate import to_1

OLD = Path(__file__).parent / "old"
CHORD_FILES = ["0.5.15.tla", "0.5.15-saved-by-0.7.0.tla"]


def harmony_modes(doc):
    return [
        c.attrs.get("display_mode", "letter")
        for tl in doc.timelines.values()
        if tl.kind == "harmony"
        for c in tl.components.values()
        if c.kind == "harmony"
    ]


def old_file(kind="HARMONY", timeline="Harmony", mode="chord", **attrs):
    return {
        "file_path": "",
        "media_path": "",
        "media_metadata": {"title": "Piece"},
        "timelines": {
            "1": {
                "kind": timeline,
                "name": "Chords",
                "ordinal": 1,
                "height": 30,
                "is_visible": True,
                "components": {
                    "2": {"kind": kind, "time": 1, "display_mode": mode, **attrs}
                },
            }
        },
        "app_name": "TiLiA",
        "version": "0.5.15",
    }


def loads(content):
    return tla.loads(json.dumps(content).encode())


@pytest.mark.parametrize("name", CHORD_FILES)
def test_the_old_files_chords_read_as_letter(name):
    doc = tla.read(OLD / name)
    assert harmony_modes(doc) == ["letter", "letter"]
    assert not [w for w in doc.warnings if "display mode" in w.message.lower()]


@pytest.mark.parametrize("name", CHORD_FILES)
def test_the_old_files_chords_are_counted(name):
    changes = to_1.migrate(json.loads((OLD / name).read_bytes())).changes
    assert changes["display_modes_renamed"] == 2


def test_a_file_without_chords_counts_none():
    changes = to_1.migrate(json.loads((OLD / "0.0.96.tla").read_bytes())).changes
    assert "display_modes_renamed" not in changes


def test_the_file_is_written_with_letter_left_out_as_the_default():
    written = tla.canonical_bytes(tla.read(OLD / "0.5.15.tla"))
    assert b'"chord"' not in written


def test_other_modes_stay_and_are_not_counted():
    content = old_file(mode="roman")
    assert harmony_modes(loads(content)) == ["roman"]
    assert "display_modes_renamed" not in to_1.migrate(content).changes


def test_a_chord_on_something_that_is_not_a_harmony_stays():
    content = old_file(kind="MARKER", timeline="Marker")
    migrated = to_1.migrate(copy.deepcopy(content))
    assert "display_modes_renamed" not in migrated.changes
    (timeline,) = loads(content).timelines.values()
    (component,) = timeline.components.values()
    assert component.extra["display_mode"] == "chord"


def test_a_harmony_in_a_timeline_that_does_not_hold_it_stays():
    content = old_file(timeline="Marker")
    assert "display_modes_renamed" not in to_1.migrate(copy.deepcopy(content)).changes
    (timeline,) = loads(content).timelines.values()
    (component,) = timeline.components.values()
    assert component.extra["display_mode"] == "chord"


def test_the_document_id_is_the_same_with_chord_or_letter():
    assert (
        loads(old_file(mode="chord")).document_id
        == loads(old_file(mode="letter")).document_id
    )


@pytest.mark.parametrize(
    "files, line",
    [
        (1, "changed 1 display mode from chord to letter"),
        (2, "changed 2 display modes from chord to letter"),
    ],
)
def test_the_report_words_the_count(tmp_path, capsys, files, line):
    content = old_file()
    if files == 2:
        content["timelines"]["1"]["components"]["3"] = {
            "kind": "HARMONY",
            "time": 2,
            "display_mode": "chord",
        }
    (tmp_path / "piece.tla").write_bytes(json.dumps(content).encode())

    migrate_command.main([str(tmp_path)])

    assert f"  piece.tla               {line}\n" in capsys.readouterr().out
