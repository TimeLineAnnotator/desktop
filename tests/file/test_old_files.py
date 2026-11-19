"""Old files, as TiLiA 0.7 showed them.

Each of WP3's files from an older TiLiA version opens holding what TiLiA 0.7 held of
it: its timelines, components, labels, colours, times and measure numbers, apart from
what the migration drops. TiLiA 0.7 can't run here, and WP3's files were saved by it,
so what it held is read from the old file's JSON: from TiLiA 0.7's own save of the
file, opened without an edit, where WP3 keeps one, and otherwise from the file. The
first save of an old file writes what `tilia migrate --apply` writes for it.

WP3's files are read in place; a file a test saves is a copy in the test's folder.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import canonicalize

import pytest

from tests.mock import Serve
from tests.utils import get_blank_file_data
from tilia.requests import Get
from tilia.ui import commands
from tilia_core import tla
from tilia_core.tla.ids import migrated_id

FILES = Path(__file__).parents[2] / "packages" / "tilia-core" / "tests" / "tla"
OLD = sorted((FILES / "old").glob("*.tla"))
assert OLD, f"no old files in {FILES / 'old'}"
# What the migration drops, each with a warning (US2, scenario 1): a hierarchy's
# formal type and function, and an AudioWave timeline's amplitude bars, which TiLiA
# computes from the media.
DROPPED = {"hierarchy": ("formal_type", "formal_function")}
WITHOUT_COMPONENTS = ("audiowave",)
# The marks in a comment that the migration moves into the component's fields
# (WP3's `contracts/migration.md`, *Comment marks*).
SEPARATORS = re.compile(r"[\s|]+")
MARKS = ("tag=", "gen=")
NOT_COMPARED = ("hash",)


def names(paths):
    return [path.name for path in paths]


def open_file(path) -> bool:
    """Opens `path`, as the File menu does, without saving the file open, declining to
    look for media or PDFs that aren't there, and closing the warnings it opens
    with."""
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, False),
        Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
        Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, False)),
        Serve(Get.FROM_USER_SHOW_PROBLEMS, None),
    ):
        return commands.execute("file.open", path)


def json_of(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def held_by_tilia_0_7(path: Path) -> dict:
    """What TiLiA 0.7 held of the old file at `path`: TiLiA 0.7's own save of it,
    opened without an edit, where WP3 keeps one; otherwise the file itself."""
    resaved = path.with_name(f"{path.stem}-saved-by-0.7.0.tla")
    return json_of(resaved if resaved.exists() else path)


def kind_of(kind: str) -> str:
    """A timeline's kind, however a TiLiA version spells it."""
    return kind.lower().removesuffix("_timeline")


def is_mark(word: str) -> bool:
    return any(word.startswith(mark) and word != mark for mark in MARKS)


def comment_words(comment: str) -> list[str]:
    """A comment's words, without the marks the migration moves into fields."""
    return [word for word in SEPARATORS.split(comment) if word and not is_mark(word)]


def expected_comment(comment: Any) -> Any:
    """A comment as TiLiA shows it once migrated: unchanged without a mark; with
    one, its other words, each with the separator before it, which in the old files
    is a space (WP3's `contracts/migration.md`, *Comment marks*: "the rest of the
    comment stays character for character")."""
    if not isinstance(comment, str):
        return comment
    if not any(is_mark(word) for word in SEPARATORS.split(comment)):
        return comment
    return " ".join(comment_words(comment))


def as_drawn(svg: str) -> str:
    """A score's SVG as XML, which is what the viewer draws: the viewer writes back
    the SVG it loads as `lxml` serializes it, so `<svg></svg>` becomes `<svg/>`."""
    return canonicalize(svg) if svg else svg


def timeline_held(timeline: dict) -> dict:
    """A timeline TiLiA holds, as `expected_timeline` gives one."""
    held = dict(timeline)
    if held.get("svg_data"):
        held["svg_data"] = as_drawn(held["svg_data"])
    return held


def in_display_order(timelines: dict) -> list[str]:
    def position(item):
        _, timeline = item
        return timeline.get("ordinal", timeline.get("display_position"))

    return [id for id, _ in sorted(timelines.items(), key=position)]


class Ids:
    """The ids TiLiA holds for the old file's timelines and components, which the
    migration derives from the document id and the old ids (WP3's
    `contracts/migration.md`, *Ids*). The old files' ids are whole numbers, which
    don't need their position in the file."""

    def __init__(self, document_id: str):
        self.document_id = document_id

    def timeline(self, old_id: str) -> str:
        return migrated_id(self.document_id, "timeline", old_id, position=0)

    def component(self, old_timeline_id: str, old_id: str) -> str:
        return migrated_id(
            self.document_id, "component", old_timeline_id, old_id, position=0
        )


def lists_by_measure(timeline: dict) -> dict[str, list[int]]:
    """A beat timeline's measures, as TiLiA 0.7 showed them: its lists by measure,
    or, where a file leaves them empty, as TiLiA 0.0.96 did, the measures TiLiA 0.7
    counts from the beat pattern, numbered from 1, the last holding the beats
    left."""
    counts = list(timeline["beats_in_measure"])
    numbers = list(timeline["measure_numbers"])
    beats = len(timeline["components"])
    if not counts and not numbers and beats:
        pattern = timeline["beat_pattern"]
        while sum(counts) < beats:
            counts.append(pattern[len(counts) % len(pattern)])
        counts[-1] -= sum(counts) - beats
        numbers = list(range(1, len(counts) + 1))
    assert sum(counts) == beats and len(numbers) == len(counts), (
        "TiLiA 0.7 fits these lists to the beats: give this file a save by TiLiA"
        " 0.7.0, which shows what it made of them"
    )
    return {
        "beats_in_measure": counts,
        "measure_numbers": numbers,
        "measures_to_force_display": list(timeline["measures_to_force_display"]),
    }


def expected_timeline(kind: str, old: dict) -> dict:
    """The attributes of a timeline TiLiA 0.7 showed, as TiLiA holds them. Not a PDF
    timeline's path, which, like the media's, TiLiA looks for on opening (FR-036)."""
    expected = {}
    if kind != "slider":
        expected["name"] = old["name"]
    for attr in (
        "is_visible",
        "height",
        "level_count",
        "level_height",
        "visible_level_count",
        "default_row_height",
    ):
        if attr in old:
            expected[attr] = old[attr]
    if kind == "range":
        expected["rows"] = old["rows"]
    if kind == "beat":
        expected["beat_pattern"] = old["beat_pattern"]
        expected.update(lists_by_measure(old))
    if kind == "score":
        expected["svg_data"] = as_drawn(old["svg_data"])
        expected["viewer_beat_x"] = {
            float(position): x for position, x in old["viewer_beat_x"].items()
        }
    return expected


def expected_component(
    kind: str, old: dict, old_timeline_id: str, ids: Ids
) -> dict[str, Any]:
    """The attributes of a component TiLiA 0.7 showed, as TiLiA holds them."""
    expected = {
        attr: value
        for attr, value in old.items()
        if attr not in NOT_COMPARED and attr not in DROPPED.get(kind, ())
    }
    if "comments" in expected:
        expected["comments"] = expected_comment(expected["comments"])
    if kind == "harmony" and expected.get("display_mode") == "chord":
        # TiLiA 0.5's name for letters, which TiLiA 0.7 couldn't draw: the migration
        # writes `letter` (WP3's `contracts/migration.md`;
        # TimeLineAnnotator/project-management#425, option A).
        expected["display_mode"] = "letter"
    if kind == "time_signature" and expected.get("numerator") is not None:
        # TiLiA holds a numerator as it is written and drawn, as text, "3" or "3+2",
        # where TiLiA 0.7 wrote a whole number.
        expected["numerator"] = str(expected["numerator"])
    if expected.get("joined_right") is not None:
        expected["joined_right"] = ids.component(
            old_timeline_id, expected["joined_right"]
        )
    return expected


@pytest.fixture
def old_file_open(qtui, tilia, tls):
    def open_it(path: Path) -> dict:
        assert open_file(path)
        return tilia.get_app_state()

    return open_it


def assert_the_same_timelines(held: dict, old: dict, ids: Ids) -> None:
    """TiLiA holds the timelines of `old`, an old file's, in their order."""
    for old_id, timeline in old.items():
        id = ids.timeline(old_id)
        assert id in held, f"timeline {old_id}"
        kind = kind_of(timeline["kind"])
        assert kind_of(held[id]["kind"]) == kind
        expected = expected_timeline(kind, timeline)
        shown = timeline_held(held[id])
        assert {
            attr: shown.get(attr, "<missing>") for attr in expected
        } == expected, f"timeline {old_id}"
    the_file_s = [ids.timeline(old_id) for old_id in in_display_order(old)]
    assert [id for id in in_display_order(held) if id in the_file_s] == the_file_s
    # The one slider timeline TiLiA shows when the file has none (FR-007), and no
    # other.
    others = [held[id]["kind"] for id in held.keys() - set(the_file_s)]
    has_a_slider = any(kind_of(tl["kind"]) == "slider" for tl in old.values())
    assert others == ([] if has_a_slider else ["Slider"])


def assert_the_same_components(held: dict, old: dict, ids: Ids) -> None:
    """TiLiA holds the components of `old`, an old file's timelines, and no other."""
    for old_timeline_id, timeline in old.items():
        if kind_of(timeline["kind"]) in WITHOUT_COMPONENTS:
            continue
        components = held[ids.timeline(old_timeline_id)]["components"]
        expected_ids = {
            ids.component(old_timeline_id, old_id): old_id
            for old_id in timeline["components"]
        }
        assert set(components) == set(expected_ids), f"timeline {old_timeline_id}"
        assert len(components) == len(timeline["components"])
        for id, old_id in expected_ids.items():
            old_component = timeline["components"][old_id]
            expected = expected_component(
                old_component["kind"].lower(), old_component, old_timeline_id, ids
            )
            component = components[id]
            assert {
                attr: component.get(attr, "<missing>") for attr in expected
            } == expected, f"component {old_id}"


def assert_first_save_is_what_tilia_migrate_writes(old: Path, folder: Path) -> None:
    """Opens a copy of `old` in TiLiA and saves it, and has `tla.migrate_folder` write
    another, each in a folder of its own in `folder`, so that the paths they store are
    the same."""
    (folder / "saved").mkdir()
    (folder / "migrated").mkdir()
    saved = Path(shutil.copy(old, folder / "saved"))
    migrated = Path(shutil.copy(old, folder / "migrated"))
    assert open_file(saved)

    assert commands.execute("file.save")

    (result,) = tla.migrate_folder(migrated.parent, apply=True).files
    assert result.outcome == tla.Outcome.MIGRATED
    assert saved.read_bytes() == migrated.read_bytes()


class TestAsTiLiA07ShowedThem:
    @pytest.mark.parametrize("path", OLD, ids=names(OLD))
    def test_the_same_timelines_in_the_same_order(self, tilia, old_file_open, path):
        old = held_by_tilia_0_7(path)["timelines"]

        held = old_file_open(path)["timelines"]

        ids = Ids(tilia.file_manager.file.document.document_id)
        assert_the_same_timelines(held, old, ids)

    @pytest.mark.parametrize("path", OLD, ids=names(OLD))
    def test_the_same_components(self, tilia, old_file_open, path):
        old = held_by_tilia_0_7(path)["timelines"]

        held = old_file_open(path)["timelines"]

        ids = Ids(tilia.file_manager.file.document.document_id)
        assert_the_same_components(held, old, ids)

    @pytest.mark.parametrize("path", OLD, ids=names(OLD))
    def test_the_same_fields_and_media_length(self, old_file_open, path):
        old = dict(held_by_tilia_0_7(path)["media_metadata"])

        held = dict(old_file_open(path)["media_metadata"])

        # The fields in the file's order, as the Metadata window lists them. TiLiA
        # puts the notes and the media length in places of its own.
        assert [key for key in held if key not in ("notes", "media length")] == [
            key for key in old if key not in ("notes", "media length")
        ]
        # The file's media length, which the Metadata window shows with the fields
        # (FR-035): none, as TiLiA 0.0.96 stored, shows as 0.
        length = held.pop("media length")
        assert length == old.pop("media length", 0)
        assert held == old


class TestTheFirstSave:
    @pytest.mark.parametrize("path", OLD, ids=names(OLD))
    def test_writes_what_tilia_migrate_writes(self, qtui, tilia, tls, tmp_path, path):
        assert_first_save_is_what_tilia_migrate_writes(path, tmp_path)


def measures_tilia_0_7_read(folder: Path) -> Path:
    """A file of TiLiA 0.7's, made from the app's own old-format data, whose measures
    TiLiA can't count from its beats: a pickup numbered 0, a measure of two beats in
    a pattern of three, a number that jumps, and a number always shown. WP3's old
    files number every measure from 1 as TiLiA counts them, so only a file like this
    one tells measures read from the file from measures counted."""
    data = get_blank_file_data()
    data["version"] = "0.7.0"
    data["media_metadata"]["media length"] = 10.0
    data["timelines"]["1"] = {
        "kind": "Beat",
        "name": "Measures",
        "height": 35,
        "is_visible": True,
        "ordinal": 2,
        "beat_pattern": [3],
        "beats_in_measure": [1, 3, 2, 3],
        "measure_numbers": [0, 1, 2, 10],
        "measures_to_force_display": [2],
        "components": {str(n + 2): {"time": n * 0.5, "kind": "BEAT"} for n in range(9)},
    }
    path = folder / "measures.tla"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


class TestMeasuresTiLiA07Read:
    def test_the_same_measures(self, tilia, old_file_open, tmp_path):
        path = measures_tilia_0_7_read(tmp_path)
        old = json_of(path)["timelines"]

        held = old_file_open(path)["timelines"]

        ids = Ids(tilia.file_manager.file.document.document_id)
        assert_the_same_timelines(held, old, ids)
        assert_the_same_components(held, old, ids)

    def test_the_first_save_is_what_tilia_migrate_writes(
        self, qtui, tilia, tls, tmp_path
    ):
        (tmp_path / "made").mkdir()
        path = measures_tilia_0_7_read(tmp_path / "made")

        assert_first_save_is_what_tilia_migrate_writes(path, tmp_path)


class TestTheAppsOwnOldFormatData:
    def test_opens(self, qtui, tilia, tls, tmp_path):
        data = get_blank_file_data()
        path = tmp_path / "old.tla"
        path.write_text(json.dumps(data), encoding="utf-8")

        assert open_file(path)

        assert [type(tl).type_name() for tl in tls] == ["Slider"]
        assert tilia.file_manager.file.media_metadata["title"] == "Untitled"
        assert not tilia.is_file_modified()
