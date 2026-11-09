"""`scripts/check_migration.py`, on a small folder made here (SC-002)."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.importers import harmony_available
from tilia_core.tla import reader

HERE = Path(__file__).parent
OLD = HERE / "old"
GOLDEN = HERE / "golden"
SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_migration.py"

spec = importlib.util.spec_from_file_location("check_migration", SCRIPT)
check_migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_migration)

S4 = "0.6.0-s4-10.tla"  # labels and colours
COMMENTS = "sub/0.0.96.tla"  # comments, with marks in one
SCORE = "0.7.0-osmd.tla"  # an SVG
CURRENT = "unknown.tla"  # in the current format
EVERY_KIND = "0.7.0.tla"
HIERARCHIES, MARKERS, BEATS, HARMONIES, SCORES, RANGES = "1", "6", "9", "22", "34", "42"
PDFS = "26"
# Absolute paths of this system's form, and of the other's, that name nothing.
HERE, ELSEWHERE = (
    ("C:/Nowhere", "/nowhere") if os.name == "nt" else ("/nowhere", "C:/Nowhere")
)
# A core that checks the rules won't write chords and keys without music21.
needs_chords = pytest.mark.skipif(
    hasattr(tla, "BrokenRules") and not harmony_available(),
    reason="writing chords and keys needs the `harmony` extra",
)


@pytest.fixture
def source(tmp_path):
    folder = tmp_path / "source"
    (folder / "sub").mkdir(parents=True)
    shutil.copy(OLD / "0.6.0-s4-10.tla", folder / S4)
    shutil.copy(OLD / "0.0.96.tla", folder / COMMENTS)
    shutil.copy(OLD / "0.7.0-osmd.tla", folder / SCORE)
    shutil.copy(GOLDEN / "unknown.tla", folder / CURRENT)
    return folder


@pytest.fixture
def copied(tmp_path, source):
    return Path(shutil.copytree(source, tmp_path / "copy"))


def contents(folder):
    return {path: path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def edit(path, change):
    """Change a file of the current format as the writer would write it."""
    content = json.loads(path.read_bytes())
    change(content)
    text = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))


def first_with(content, key):
    """The first component of `content` with `key`, and its timeline."""
    for timeline in content["timelines"].values():
        for component in timeline["components"].values():
            if component.get(key):
                return timeline, component
    raise AssertionError(f"no component has {key}")


class TestAnUneditedCopy:
    def test_as_a_command_it_finds_no_difference(self, source, copied):
        original = contents(source)

        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(source), str(copied)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "4 files, 0 with a difference." in result.stdout
        assert contents(source) == original

    def test_its_old_files_are_migrated_and_the_others_left_as_they_were(
        self, source, copied, capsys
    ):
        before = (copied / CURRENT).read_bytes()

        assert check_migration.main([str(source), str(copied)]) == 0

        assert tla.read(copied / S4).format_version == tla.FORMAT_VERSION
        assert (copied / CURRENT).read_bytes() == before

    def test_a_copy_migrated_before_finds_no_difference(self, source, copied, capsys):
        tla.migrate_folder(copied, apply=True)

        assert check_migration.main([str(source), str(copied)]) == 0

    def test_checking_again_finds_no_difference(self, source, copied, capsys):
        check_migration.main([str(source), str(copied)])
        migrated = contents(copied)

        assert check_migration.main([str(source), str(copied)]) == 0
        assert contents(copied) == migrated

    def test_the_report_says_what_it_found_in_each_file_and_in_all(
        self, source, copied, capsys
    ):
        check_migration.main([str(source), str(copied)])

        out = capsys.readouterr().out
        assert f"{S4} (from 0.6.0): no difference: timelines 3, components 281" in out
        assert "legacy scores 1" in out
        assert "In all: timelines " in out

    def test_amplitude_bars_arent_missing(self, source, copied, capsys):
        # What FR-021 drops: TiLiA computes them from the media.
        for folder in (source, copied):
            content = json.loads((folder / S4).read_bytes())
            bar = {"start": 0.0, "end": 1.0, "amplitude": 0.25, "kind": "AUDIOWAVE"}
            content["timelines"]["900"] = {
                "kind": "AudioWave",
                "height": 80,
                "is_visible": False,
                "ordinal": 9,
                "components": {"901": bar},
            }
            (folder / S4).write_text(json.dumps(content), encoding="utf-8")

        assert check_migration.main([str(source), str(copied)]) == 0

        out = capsys.readouterr().out
        assert (
            "dropped, with its warning: /timelines/900/components, 1 amplitude" in out
        )

    def test_a_media_path_relative_from_each_folder_isnt_a_difference(
        self, source, copied, capsys
    ):
        # An absolute path that exists here is made relative from where the file
        # is read, and these two files are in different folders (FR-021).
        media = source / "media.ogg"
        media.touch()
        for folder in (source, copied):
            content = json.loads((folder / S4).read_bytes())
            content["media_path"] = str(media)
            (folder / S4).write_text(json.dumps(content), encoding="utf-8")

        assert check_migration.main([str(source), str(copied)]) == 0

        assert tla.read(copied / S4).media_path == "../source/media.ogg"

    def test_two_beat_units_in_one_measure_stay(self, folders_with, capsys):
        # On two of its beats: not a drop (contract, *Beat timelines*, step 4).
        content = old_file()
        components = components_of(content, BEATS)
        for key, beat in ("900", "10"), ("901", "11"):
            components[key] = {"kind": "BEAT_UNIT", "beat_id": beat, "units": "1"}

        assert check_migration.main(folders_with(content)) == 0

        out = capsys.readouterr().out
        assert "which isn't a difference: 1." in out  # the amplitude bars


def set_label(content):
    first_with(content, "label")[1]["label"] = "another label"


def set_time(content):
    first_with(content, "start")[1]["start"] += 0.5


def set_colour(content):
    first_with(content, "color")[1]["color"] = "#012345"


def set_comment(content):
    first_with(content, "comments")[1]["comments"] = "another comment"


def set_metadata(content):
    content["metadata"]["title"] = "another title"


def remove_component(content):
    timeline, component = first_with(content, "label")
    timeline["components"] = {
        key: value
        for key, value in timeline["components"].items()
        if value != component
    }


def remove_timeline(content):
    key = next(k for k, t in content["timelines"].items() if t["kind"] == "Hierarchy")
    del content["timelines"][key]


def change_score(content):
    content["scores"][0]["content"][0] = "<svg/>"


class TestAChangeInTheCopy:
    @pytest.mark.parametrize(
        "file, change, place",
        [
            (S4, set_label, "/label: "),
            (S4, set_time, "/start: "),
            (S4, set_colour, "/color: "),
            (COMMENTS, set_comment, "/comments: "),
            (S4, set_metadata, "/metadata/title: "),
            (S4, remove_component, ": missing from the copy, was "),
            (S4, remove_timeline, ": missing from the copy, was "),
            (SCORE, change_score, "/lines/0: "),
        ],
    )
    def test_is_a_difference_at_its_place(
        self, source, copied, file, change, place, capsys
    ):
        tla.migrate_folder(copied, apply=True)
        edit(copied / file, change)

        assert check_migration.main([str(source), str(copied)]) == 1

        out = capsys.readouterr().out
        assert place in out
        assert "4 files, 1 with a difference." in out

    def test_a_layout_of_its_own_is_a_difference(self, source, copied, capsys):
        tla.migrate_folder(copied, apply=True)
        content = json.loads((copied / S4).read_bytes())
        (copied / S4).write_text(json.dumps(content, indent=4), encoding="utf-8")

        assert check_migration.main([str(source), str(copied)]) == 1

        out = capsys.readouterr().out
        assert "the copy isn't what the original migrates to" in out
        assert "a second read and write changed its bytes" in out

    def test_a_long_list_of_differences_is_cut_short(self, source, copied, capsys):
        tla.migrate_folder(copied, apply=True)

        def every_time(content):
            for timeline in content["timelines"].values():
                for component in timeline["components"].values():
                    component["time"] = 1.0

        edit(copied / S4, every_time)

        assert check_migration.main([str(source), str(copied)]) == 1

        assert "more\n" in capsys.readouterr().out


def a_migration_that_does(change):
    """The migration, followed by `change` to what it gives, in every read."""
    migrate = reader.migrate

    def changed(*args, **kwargs):
        migrated = migrate(*args, **kwargs)
        change(migrated.content)
        return migrated

    return changed


def lose_a_label(content):
    first_with(content, "label")[1].pop("label")


def lose_a_time(content):
    first_with(content, "start")[1]["start"] = 0.125


def lose_a_colour(content):
    first_with(content, "color")[1].pop("color")


def lose_a_comment(content):
    first_with(content, "comments")[1].pop("comments")


def lose_a_mark(content):
    first_with(content, "metadata")[1]["metadata"].pop("tags")


def lose_a_metadata_entry(content):
    content["metadata"].pop("title")


def lose_a_score(content):
    content["scores"][0]["content"][0] = "<svg/>"


class TestWhatAMigrationLoses:
    """Both sides are read through the migration, so only the original's own JSON
    shows these."""

    @pytest.mark.parametrize(
        "file, lose, place",
        [
            (S4, lose_a_label, "/label: "),
            (S4, lose_a_time, "/start: "),
            (S4, lose_a_colour, "/color: "),
            (COMMENTS, lose_a_comment, "/comments: "),
            (COMMENTS, lose_a_mark, "/metadata/tags: "),
            (S4, lose_a_metadata_entry, "/metadata/title: missing from the copy"),
            (S4, remove_component, ": missing from the copy, was {"),
            (S4, remove_timeline, "was a hierarchy timeline"),
            (SCORE, lose_a_score, "/score/lines/0: "),
        ],
    )
    def test_is_a_difference(
        self, source, copied, monkeypatch, file, lose, place, capsys
    ):
        for other in {S4, COMMENTS, SCORE} - {file}:
            (source / other).unlink()
            (copied / other).unlink()
        monkeypatch.setattr(reader, "migrate", a_migration_that_does(lose))

        assert check_migration.main([str(source), str(copied)]) == 1

        assert place in capsys.readouterr().out


def old_file(harmonies=False):
    """The old file with every kind, and a second hierarchy timeline: without its
    harmonies, unless a test is about them, since a core that checks the rules
    needs music21 to write them."""
    content = json.loads((OLD / EVERY_KIND).read_bytes())
    if not harmonies:
        del content["timelines"][HARMONIES]
    content["timelines"]["100"] = {
        "kind": "Hierarchy",
        "name": "Second",
        "height": 120,
        "is_visible": True,
        "ordinal": 10,
        "components": {
            "101": {
                "start": 0.0,
                "end": 9.952,
                "level": 1,
                "label": "Whole",
                "kind": "HIERARCHY",
            }
        },
    }
    return content


@pytest.fixture
def folders_with(tmp_path):
    """SOURCE and COPY, each with one file holding `content`."""

    def make(content):
        folders = tmp_path / "source", tmp_path / "copy"
        for folder in folders:
            folder.mkdir()
            data = json.dumps(content, ensure_ascii=False).encode("utf-8")
            (folder / EVERY_KIND).write_bytes(data)
        return [str(folder) for folder in folders]

    return make


def of_kind(content, kind):
    """The components of that kind in `content`."""
    return [
        component
        for timeline in content["timelines"].values()
        for component in timeline["components"].values()
        if component.get("kind") == kind
    ]


def timeline_of(content, kind):
    return next(t for t in content["timelines"].values() if t["kind"] == kind)


def swap(content, kind, key):
    """Swap `key` between the first two components of `kind` that differ in it: one
    may not have it, at its default."""
    components = of_kind(content, kind)
    one = next(component for component in components if key in component)
    other = next(
        component for component in components if component.get(key) != one[key]
    )
    value = one.pop(key)
    if key in other:
        one[key] = other[key]
    other[key] = value


def set_on(content, kind, key, value):
    of_kind(content, kind)[0][key] = value


def add_to(content, kind, key):
    of_kind(content, kind)[0][key] += 1


def move_a_component(content):
    first, second = [
        timeline
        for timeline in content["timelines"].values()
        if timeline["kind"] == "Hierarchy"
    ]
    key = next(k for k, c in first["components"].items() if c.get("label") == "P")
    second["components"][key] = first["components"].pop(key)


def beats_in_order(content):
    return sorted(of_kind(content, "BEAT"), key=lambda beat: beat["time"])


def move_a_mark(content):
    # Onto the beat after it, so that one measure has a beat more, and one fewer.
    beats = beats_in_order(content)
    place = next(i for i, beat in enumerate(beats) if i and "measure" in beat)
    beats[place + 1]["measure"] = beats[place].pop("measure")


def set_a_number(content):
    beats_in_order(content)[0]["measure"]["number"] = 7


def force_a_display(content):
    beats_in_order(content)[0]["measure"]["force_display"] = True


def set_a_beat_unit(content):
    beats_in_order(content)[0]["beat_unit"]["units"] = "3"


def swap_ordinals(content):
    timelines = list(content["timelines"].values())
    timelines[1]["ordinal"], timelines[2]["ordinal"] = (
        timelines[2]["ordinal"],
        timelines[1]["ordinal"],
    )


def set_a_setting(key, value, kind="Hierarchy"):
    def change(content):
        timeline_of(content, kind)[key] = value

    return change


def rename_a_row(content):
    timeline_of(content, "Range")["rows"][1]["name"] = "another row"


def set_a_position(content):
    content["scores"][0]["beat_x"][0][1] = 99.5


def lose_the_score(content):
    del timeline_of(content, "Score")["score"]
    content["scores"] = []


def add_a_score(content):
    content["scores"].append(
        {**content["scores"][0], "id": "01912345-0000-7000-8000-000000000001"}
    )


def set_the_length(content):
    content["media"]["length"] = 1.5


def set_the_media_path(content):
    content["media"]["path"] = "../elsewhere/another.ogg"


def name_of(path):
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def put_the_media_elsewhere(content):
    content["media"]["path"] = f"../elsewhere/{name_of(content['media']['path'])}"


def put_a_pdf_elsewhere(content):
    timeline = timeline_of(content, "Pdf")
    timeline["path"] = f"../elsewhere/{name_of(timeline['path'])}"


def reverse_the_metadata(content):
    content["metadata"] = dict(reversed(list(content["metadata"].items())))


def set_the_app(content):
    content["app_name"] = "Another"


def set_the_time_unit(content):
    content["time_unit"] = "quarters"


def add_a_key(content):
    set_on(content, "MARKER", "added", 1)


def add_a_component(content):
    timeline = timeline_of(content, "Marker")
    another = copy.deepcopy(next(iter(timeline["components"].values())))
    timeline["components"]["01912345-0000-7000-8000-000000000002"] = another


def add_a_timeline(content):
    content["timelines"]["01912345-0000-7000-8000-000000000003"] = {
        **timeline_of(content, "Slider"),
        "ordinal": 99,
    }


def leave_a_mark_in_the_comment(content):
    first_with(content, "metadata")[1]["comments"] = "tag=p1 first theme"


def reorder_a_comment(content):
    first_with(content, "metadata")[1]["comments"] = "theme first"


def set_a_tag(content):
    first_with(content, "metadata")[1]["metadata"]["tags"] = ["another"]


def set_a_generator(content):
    first_with(content, "metadata")[1]["metadata"]["generated_by"] = "another"


class TestAWrongMigration:
    """The migration, changed in process, so that the copy is what it gives and both
    readings have the fault: only the old file's own JSON shows it."""

    @pytest.mark.parametrize(
        "change, place",
        [
            pytest.param(
                lambda c: swap(c, "HIERARCHY", "label"), "/label: ", id="labels"
            ),
            pytest.param(
                lambda c: swap(c, "HIERARCHY", "start"), "/start: ", id="times"
            ),
            pytest.param(
                lambda c: swap(c, "HIERARCHY", "color"), "/color: ", id="colours"
            ),
            pytest.param(
                lambda c: swap(c, "MARKER", "comments"), "/comments: ", id="comments"
            ),
            pytest.param(
                lambda c: add_to(c, "HIERARCHY", "level"), "/level: ", id="level"
            ),
            pytest.param(
                move_a_component,
                ": missing from the copy, was {",
                id="moved to another timeline",
            ),
            pytest.param(
                lambda c: swap(c, "RANGE", "row_id"), "/row_id: ", id="row_id"
            ),
            pytest.param(
                lambda c: set_on(c, "RANGE", "joined_right", None),
                "/joined_right: ",
                id="joined_right",
            ),
            pytest.param(move_a_mark, "/beats: ", id="a measure's beats"),
            pytest.param(set_a_number, "/measures/0/number: ", id="a measure's number"),
            pytest.param(force_a_display, "/force_display: ", id="force_display"),
            pytest.param(set_a_beat_unit, "/beat_unit/units: ", id="beat unit"),
            pytest.param(lambda c: add_to(c, "NOTE", "step"), "/step: ", id="step"),
            pytest.param(
                lambda c: add_to(c, "NOTE", "octave"), "/octave: ", id="octave"
            ),
            pytest.param(
                lambda c: set_on(c, "CLEF", "icon", "x"), "/icon: ", id="clef"
            ),
            pytest.param(lambda c: add_to(c, "SCORE_ANNOTATION", "x"), "/x: ", id="x"),
            pytest.param(
                lambda c: add_to(c, "PDF_MARKER", "page_number"),
                "/page_number: ",
                id="page",
            ),
            pytest.param(
                lambda c: set_on(c, "MARKER", "kind", "LINE"),
                "/kind: ",
                id="a component's kind",
            ),
            pytest.param(swap_ordinals, "/ordinal: ", id="the timelines' order"),
            pytest.param(
                set_a_setting("kind", "AudioWave", "Slider"), "/kind: ", id="kind"
            ),
            pytest.param(set_a_setting("name", "another"), "/name: ", id="name"),
            pytest.param(set_a_setting("height", 7), "/height: ", id="height"),
            pytest.param(
                set_a_setting("is_visible", False), "/is_visible: ", id="visible"
            ),
            pytest.param(
                set_a_setting("beat_pattern", "3", "Beat"),
                "/beat_pattern: ",
                id="pattern",
            ),
            pytest.param(
                set_a_setting("show_time_signatures", True, "Beat"),
                "/show_time_signatures: ",
                id="time signatures",
            ),
            pytest.param(
                set_a_setting("path", "../another.pdf", "Pdf"), "/path: ", id="PDF path"
            ),
            pytest.param(rename_a_row, "/rows/1/name: ", id="a row"),
            pytest.param(set_a_position, "/score/beat_x/0/1: ", id="beat_x"),
            pytest.param(lose_the_score, "/score: missing", id="no score"),
            pytest.param(
                add_a_score, ": only in the copy, is a svg-osmd", id="a score"
            ),
            pytest.param(set_the_length, "/media/length: ", id="media length"),
            pytest.param(set_the_media_path, "/media/path: ", id="media path"),
            pytest.param(
                put_the_media_elsewhere, "/media/path: ", id="the media's folder"
            ),
            pytest.param(
                put_a_pdf_elsewhere, f"/timelines/{PDFS}/path: ", id="a PDF's folder"
            ),
            pytest.param(
                reverse_the_metadata, "/metadata: in the order", id="metadata's order"
            ),
            pytest.param(set_the_app, "/app_name: ", id="app_name"),
            pytest.param(set_the_time_unit, "/time_unit: ", id="time_unit"),
            pytest.param(add_a_key, "/added: only in the copy", id="an added key"),
            pytest.param(
                add_a_component, ": only in the copy, is a marker", id="component"
            ),
            pytest.param(
                add_a_timeline, ": only in the copy, is a slider", id="timeline"
            ),
            pytest.param(leave_a_mark_in_the_comment, "/comments", id="a mark stays"),
            pytest.param(reorder_a_comment, "/comments/0: ", id="words in order"),
            pytest.param(set_a_tag, "/metadata/tags/0: ", id="a tag"),
            pytest.param(set_a_generator, "/metadata/generated_by/0: ", id="generator"),
        ],
    )
    def test_is_a_difference(self, folders_with, monkeypatch, capsys, change, place):
        folders = folders_with(old_file())
        monkeypatch.setattr(reader, "migrate", a_migration_that_does(change))

        assert check_migration.main(folders) == 1

        assert place in capsys.readouterr().out

    @needs_chords
    @pytest.mark.parametrize(
        "kind, key, value",
        [
            ("HARMONY", "step", 5),
            ("HARMONY", "accidental", 1),
            ("HARMONY", "quality", "minor"),
            ("HARMONY", "inversion", 1),
            ("HARMONY", "applied_to", 3),
            ("HARMONY", "level", 2),
            ("HARMONY", "display_mode", "custom"),
            ("HARMONY", "custom_text", "another"),
            ("HARMONY", "custom_text_font_type", "normal"),
            ("MODE", "step", 6),
            ("MODE", "accidental", 1),
            ("MODE", "type", "major"),
        ],
    )
    def test_a_field_of_a_chord_or_a_key_is_a_difference(
        self, folders_with, monkeypatch, capsys, kind, key, value
    ):
        def change(content):
            for component in of_kind(content, kind):
                component[key] = value

        folders = folders_with(old_file(harmonies=True))
        monkeypatch.setattr(reader, "migrate", a_migration_that_does(change))

        assert check_migration.main(folders) == 1

        assert f"/{key}: " in capsys.readouterr().out

    def test_a_timeline_kept_as_it_is_is_compared(
        self, folders_with, monkeypatch, capsys
    ):
        def change(content):
            timeline_of(content, "Lyrics")["some text"] = "another"

        content = old_file()
        with_a_timeline_of_a_kind_unknown(content)
        folders = folders_with(content)
        monkeypatch.setattr(reader, "migrate", a_migration_that_does(change))

        assert check_migration.main(folders) == 1

        assert "/some text: " in capsys.readouterr().out

    def test_a_component_kept_as_it_is_is_compared(
        self, folders_with, monkeypatch, capsys
    ):
        def change(content):
            kept = timeline_of(content, "Marker")["components"].values()
            next(one for one in kept if "formal_type" in one)["formal_type"] = "another"

        content = old_file()
        with_a_component_its_timeline_doesnt_hold(content)
        folders = folders_with(content)
        monkeypatch.setattr(reader, "migrate", a_migration_that_does(change))

        assert check_migration.main(folders) == 1

        assert "/formal_type: " in capsys.readouterr().out

    def test_a_score_named_by_a_timeline_without_an_svg_is_a_difference(
        self, folders_with, monkeypatch, capsys
    ):
        def change(content):
            first, second = [
                timeline
                for timeline in content["timelines"].values()
                if timeline["kind"] == "Score"
            ]
            named = first.get("score") or second.get("score")
            first["score"] = second["score"] = named

        content = old_file()
        content["timelines"]["400"] = {
            "kind": "Score",
            "height": 1,
            "is_visible": True,
            "name": "Not imported yet",
            "ordinal": 40,
            "svg_data": "",
            "components": {},
        }
        folders = folders_with(content)
        monkeypatch.setattr(reader, "migrate", a_migration_that_does(change))

        assert check_migration.main(folders) == 1

        assert "/timelines/400/score: only in the copy" in capsys.readouterr().out

    def test_two_timelines_that_swap_their_scores_are_a_difference(
        self, folders_with, monkeypatch, capsys
    ):
        def change(content):
            first, second = [
                timeline
                for timeline in content["timelines"].values()
                if timeline["kind"] == "Score"
            ]
            first["score"], second["score"] = second["score"], first["score"]

        content = old_file()
        content["timelines"]["400"] = {
            "kind": "Score",
            "height": 1,
            "is_visible": True,
            "name": "Another score",
            "ordinal": 40,
            "svg_data": "<svg/>",
            "components": {},
        }
        folders = folders_with(content)
        monkeypatch.setattr(reader, "migrate", a_migration_that_does(change))

        assert check_migration.main(folders) == 1

        assert f"/timelines/{SCORES}/score: missing" in capsys.readouterr().out

    def test_a_correct_migration_finds_none_in_the_same_file(
        self, folders_with, capsys
    ):
        assert check_migration.main(folders_with(old_file())) == 0


def components_of(content, key):
    return content["timelines"][key]["components"]


def first_of(content, key):
    return next(iter(components_of(content, key).values()))


def with_old_hierarchies(content):
    first_of(content, HIERARCHIES)["parent"] = "3"
    first_of(content, HIERARCHIES)["children"] = ["4"]
    first_of(content, HIERARCHIES)["formal_type"] = "sonata form"
    first_of(content, HIERARCHIES)["formal_function"] = "exposition"


def with_a_clef_icon(content):
    of_kind(content, "CLEF")[0]["icon"] = "clef-treble.svg"


def without_heights(content):
    del timeline_of(content, "Slider")["height"]
    timeline_of(content, "Marker")["height"] = None
    timeline_of(content, "Pdf")["height"] = 0


def with_display_positions(content):
    content["version"] = "0.1.1"
    for timeline in content["timelines"].values():
        timeline["display_position"] = timeline.pop("ordinal") - 1


def with_numbers_of_another_type(content):
    first_of(content, HIERARCHIES)["level"] = 1.0
    first_of(content, HIERARCHIES)["start"] = 0
    timeline_of(content, "Marker")["height"] = 30.0
    timeline_of(content, "Marker")["ordinal"] = 3.0


def with_metadata_of_every_type(content):
    content["media_metadata"].update(
        {
            "year": 1787,
            "good": True,
            "none": None,
            "ratio": 1.5,
            "list": ["a", 2, None],
            "object": {"z": 1, "a": 2},
            "nested": [["a"], {"b": 1}],
        }
    )


def with_a_media_length(value):
    def change(content):
        content["media_metadata"]["media length"] = value

    return change


def without_media_metadata(content):
    del content["media_metadata"]
    del content["app_name"]


def with_unknown_keys(content):
    content["a key of ours"] = {"a": 1}
    timeline_of(content, "Marker")["a key of ours"] = None
    of_kind(content, "MARKER")[0]["a key of ours"] = [1]


def with_a_timeline_of_a_kind_unknown(content):
    content["timelines"]["200"] = {
        "kind": "Lyrics",
        "ordinal": 20,
        "hash": "abc",
        "components_hash": "def",
        "some text": "e\u0301",
        "components": {"201": {"kind": "LINE", "hash": "abc", "text": "a"}},
    }


def with_a_component_its_timeline_doesnt_hold(content):
    components_of(content, MARKERS)["300"] = {
        "kind": "HIERARCHY",
        "hash": "abc",
        "start": 1.0,
        "pre_start": 1.0,
        "end": 2.0,
        "level": 1,
        "formal_type": "kept",
        "parent": "6",
        "comments": "tag=stays",
    }
    components_of(content, SCORES)["301"] = {"kind": "MARKER", "time": 1.0}


def with_ids_that_arent_integers(content):
    timelines = content["timelines"]
    timelines["a hierarchy"] = timelines.pop(HIERARCHIES)
    components = timelines["a hierarchy"]["components"]
    timelines["a hierarchy"]["components"] = {
        f"id {key}": component for key, component in components.items()
    }
    ranges = timelines[RANGES]["components"]
    ranges["one"], ranges["two"] = ranges.pop("43"), ranges.pop("44")
    ranges["one"]["joined_right"] = "two"


def with_a_join_as_an_integer(content):
    components_of(content, RANGES)["43"]["joined_right"] = 44


def with_lists_by_measure(counts, numbers, forced=()):
    def change(content):
        timeline = content["timelines"][BEATS]
        timeline["beats_in_measure"] = counts
        timeline["measure_numbers"] = numbers
        timeline["measures_to_force_display"] = list(forced)

    return change


def with_beat_units(content):
    beats = list(components_of(content, BEATS))
    components_of(content, BEATS)["900"] = {
        "kind": "BEAT_UNIT",
        "beat_id": beats[4],
        "denominator": 8,
        "units": "3",
        "assumed": False,
        "hash": "abc",
    }
    components_of(content, BEATS)["901"] = {
        "kind": "BEAT_UNIT",
        "beat_id": int(beats[0]),
        "assumed": True,
    }


def with_ids_and_beat_units(content):
    timeline = content["timelines"][BEATS]
    components = timeline["components"]
    first = next(iter(components))
    timeline["components"] = {f"id {k}": one for k, one in components.items()}
    timeline["components"]["a unit"] = {"kind": "BEAT_UNIT", "beat_id": f"id {first}"}


def with_time_signatures(value):
    def change(content):
        content["timelines"][BEATS]["show_time_signatures"] = value

    return change


def with_a_pattern(value):
    def change(content):
        content["timelines"][BEATS]["beat_pattern"] = value

    return change


def with_a_score_without_its_svg(svg, positions):
    def change(content):
        content["timelines"][SCORES]["svg_data"] = svg
        content["timelines"][SCORES]["viewer_beat_x"] = positions

    return change


def with_beat_positions(content):
    positions = {"10.0": 3.0, "2.0": 1, "2": 2.5}
    content["timelines"][SCORES]["viewer_beat_x"] = positions


def with_line_ends_in_the_svg(content):
    content["timelines"][SCORES]["svg_data"] = "<svg>\r\n<g/>\r\r\n</svg>\n"


def with_comment_marks(comment, metadata=None):
    def change(content):
        component = first_of(content, HIERARCHIES)
        component["comments"] = comment
        if metadata is not None:
            component["metadata"] = metadata

    return change


def with_text_in_another_form(content):
    decomposed = "Expo\u0301"
    first_of(content, HIERARCHIES)["label"] = decomposed
    first_of(content, HIERARCHIES)["comments"] = f"{decomposed} tag={decomposed}"
    timeline_of(content, "Marker")["name"] = decomposed
    content["media_metadata"][decomposed] = decomposed


def with_nulls(content):
    first_of(content, HIERARCHIES)["label"] = None
    first_of(content, HIERARCHIES)["pre_start"] = None
    timeline_of(content, "Marker")["is_visible"] = None
    of_kind(content, "NOTE")[0]["comments"] = None


def with_a_row_filled_in(content):
    timeline_of(content, "Range")["rows"].append({"id": "aBcDeF", "name": "No more"})


def with_a_link_for_media(content):
    content["media_path"] = "youtube.com/watch?v=abc"


def with_paths_of_windows(content):
    content["media_path"] = "C:\\Music\\sonata.ogg"
    content["file_path"] = "C:\\Music\\sonata.tla"
    timeline_of(content, "Pdf")["path"] = "C:\\Music\\scores\\sonata.pdf"


def with_paths(media, pdf=None, file_path=None):
    def change(content):
        content["media_path"] = media
        if pdf is not None:
            timeline_of(content, "Pdf")["path"] = pdf
        if file_path is None:
            content.pop("file_path")
        else:
            content["file_path"] = file_path

    return change


def a_beat_unit(**unit):
    def change(content):
        components = components_of(content, BEATS)
        components[str(900 + len(components))] = {"kind": "BEAT_UNIT", **unit}

    return change


def a_beat_at(time):
    def change(content):
        components_of(content, BEATS)["11"]["time"] = time

    return change


def without_a_time(content):
    del components_of(content, BEATS)["11"]["time"]


class TestWhatTheMigrationChangesOnPurpose:
    """Each isn't a difference: the migration is meant to do it."""

    @pytest.mark.parametrize(
        "change",
        [
            pytest.param(with_old_hierarchies, id="parent, children, formal"),
            pytest.param(with_a_clef_icon, id="a clef icon's .svg"),
            pytest.param(without_heights, id="no heights"),
            pytest.param(with_display_positions, id="display_position"),
            pytest.param(with_numbers_of_another_type, id="1.0 for 1"),
            pytest.param(with_metadata_of_every_type, id="metadata of every type"),
            pytest.param(with_a_media_length("12.5"), id="a length as text"),
            pytest.param(with_a_media_length("\u00a07\u3000"), id="spaces around it"),
            pytest.param(with_a_media_length(0), id="a length of 0"),
            pytest.param(with_a_media_length("long"), id="a length that isn't one"),
            pytest.param(without_media_metadata, id="no metadata, no app name"),
            pytest.param(with_unknown_keys, id="unknown keys"),
            pytest.param(with_a_timeline_of_a_kind_unknown, id="an unknown timeline"),
            pytest.param(
                with_a_component_its_timeline_doesnt_hold,
                id="a component its timeline doesn't hold",
            ),
            pytest.param(with_ids_that_arent_integers, id="ids that aren't integers"),
            pytest.param(with_a_join_as_an_integer, id="a join as an integer"),
            pytest.param(with_lists_by_measure([], []), id="no lists by measure"),
            pytest.param(with_lists_by_measure([4], [1]), id="fewer measures listed"),
            pytest.param(
                with_lists_by_measure([4, 4, 4, 4, 4], [1, 2, 3, 4, 5]),
                id="more measures listed",
            ),
            pytest.param(
                with_lists_by_measure([4, 4, 3, 1], [1, 2, 3]), id="fewer numbers"
            ),
            pytest.param(
                with_lists_by_measure([4, 4, 4], [1, 7, 8]), id="numbers that jump"
            ),
            pytest.param(
                with_lists_by_measure([4, 4, 4], [1, 2, 3], (1, 99)), id="force_display"
            ),
            pytest.param(with_lists_by_measure("x", [1]), id="lists TiLiA can't read"),
            pytest.param(with_beat_units, id="beat units"),
            pytest.param(with_ids_and_beat_units, id="ids and beat units"),
            pytest.param(with_time_signatures(True), id="time signatures shown"),
            pytest.param(with_time_signatures(False), id="time signatures hidden"),
            pytest.param(with_time_signatures(None), id="no time signatures"),
            pytest.param(with_a_pattern([4, 4, 3]), id="a pattern as a list"),
            pytest.param(with_a_pattern([]), id="an empty pattern"),
            pytest.param(with_a_pattern("4 4 3"), id="a pattern as text"),
            pytest.param(with_a_score_without_its_svg("", None), id="an empty score"),
            pytest.param(
                with_a_score_without_its_svg(None, {"1.0": 2.0}),
                id="beat positions without a score",
            ),
            pytest.param(with_beat_positions, id="beat positions"),
            pytest.param(with_line_ends_in_the_svg, id="an SVG's line ends"),
            pytest.param(with_comment_marks("a tag=x|b gen=g gen=g"), id="marks"),
            pytest.param(with_comment_marks("tag=x tag=x tag=y"), id="repeated tags"),
            pytest.param(with_comment_marks("tag= gen= TAG=x"), id="not marks"),
            pytest.param(with_comment_marks("src_start=1 tag=x"), id="other tokens"),
            pytest.param(
                with_comment_marks(
                    "tag=new gen=b", {"tags": ["old"], "generated_by": "a"}
                ),
                id="marks after a hand edit",
            ),
            pytest.param(
                with_comment_marks("tag=check", {"tags": "check"}),
                id="a mark that adds nothing",
            ),
            pytest.param(with_text_in_another_form, id="text not in NFC"),
            pytest.param(with_nulls, id="nulls"),
            pytest.param(with_a_row_filled_in, id="a row's defaults"),
            pytest.param(with_a_link_for_media, id="a link without a scheme"),
            pytest.param(with_paths_of_windows, id="Windows paths"),
            pytest.param(
                with_paths(
                    "/home/me/music/sonata.ogg",
                    "/home/me/scores/sonata.pdf",
                    "/home/me/sonata.tla",
                ),
                id="POSIX paths",
            ),
            pytest.param(
                with_paths(f"{HERE}/sonata.ogg", f"{HERE}/sonata.pdf"),
                id="no file_path: from the file's folder",
            ),
            pytest.param(
                with_paths(
                    f"{ELSEWHERE}/sonata.ogg",
                    f"{ELSEWHERE}/sonata.pdf",
                    f"{HERE}/sonata.tla",
                ),
                id="the other system's paths stay absolute",
            ),
            pytest.param(
                with_paths("D:/Music/sonata.ogg", "D:/sonata.pdf", "C:/Music/a.tla"),
                id="another drive",
            ),
            pytest.param(
                with_paths("audio\\sonata.ogg", "scores/sonata.pdf", "C:/a/b.tla"),
                id="relative by hand",
            ),
            pytest.param(
                with_paths("https://example.org/sonata.ogg", None, "C:/a/b.tla"),
                id="a URL",
            ),
            pytest.param(
                with_paths("https://www.youtube.com/watch?v=abc", None, "C:/a/b.tla"),
                id="a link",
            ),
            pytest.param(
                with_paths("//www.youtube.com/watch?v=abc", None, "C:/a/b.tla"),
                id="a link with two slashes",
            ),
            pytest.param(a_beat_at(-1.0), id="a beat before 0"),
            pytest.param(a_beat_at(9.952 + 3), id="a beat past the media's end"),
            pytest.param(a_beat_at(0.0), id="a beat at the time of another"),
            pytest.param(without_a_time, id="a beat without a time"),
            pytest.param(a_beat_unit(beat_id="no beat"), id="a unit on no beat"),
            pytest.param(
                lambda c: (a_beat_unit(beat_id="10")(c), a_beat_unit(beat_id=10)(c)),
                id="a unit on a beat that has one",
            ),
            pytest.param(
                a_beat_unit(beat_id="10", units="x"), id="units it can't read"
            ),
            pytest.param(a_beat_unit(beat_id="10", denominator=0), id="a denominator"),
        ],
    )
    def test_isnt_a_difference(self, folders_with, capsys, change):
        content = old_file()
        change(content)

        assert check_migration.main(folders_with(content)) == 0, capsys.readouterr().out

    @needs_chords
    def test_a_display_mode_renamed_isnt_a_difference(self, folders_with, capsys):
        content = old_file(harmonies=True)
        of_kind(content, "HARMONY")[0]["display_mode"] = "chord"

        assert check_migration.main(folders_with(content)) == 0, capsys.readouterr().out

    def test_a_beat_it_drops_is_listed_with_its_warning(self, folders_with, capsys):
        content = old_file()
        a_beat_at(0.0)(content)

        assert check_migration.main(folders_with(content)) == 0

        out = capsys.readouterr().out
        assert "dropped, as TiLiA drops it" in out
        assert (
            f"dropped, with its warning: /timelines/{BEATS}/components/11,"
            " a beat at the time of another" in out
        )
        # The beat, and the file's amplitude bars.
        assert "each with its warning, which isn't a difference: 2." in out

    def test_a_beat_unit_it_drops_is_listed_with_its_warning(
        self, folders_with, capsys
    ):
        content = old_file()
        a_beat_unit(beat_id="no beat")(content)

        assert check_migration.main(folders_with(content)) == 0

        out = capsys.readouterr().out
        assert "a beat unit that names" in out
        assert "dropped, with its warning: " in out
        assert "a beat unit naming 'no beat', which isn't a beat kept" in out

    def test_a_path_from_a_file_path_of_the_other_system_waits_on_a_decision(
        self, folders_with, capsys
    ):
        # Reading keeps the path absolute, and the writer writes it relative
        # (TimeLineAnnotator/project-management#530): as before, a difference
        # between the two, and only its file's name compared with the old file.
        content = old_file()
        with_paths(f"{HERE}/sonata.ogg", None, f"{ELSEWHERE}/sonata.tla")(content)

        assert check_migration.main(folders_with(content)) == 1

        out = capsys.readouterr().out
        assert "/media_path: " in out
        assert "/media/path: " not in out


MIGRATE = reader.migrate  # the migration itself, before a test changes it


def a_migration_without_its_warnings(*args, **kwargs):
    migrated = MIGRATE(*args, **kwargs)
    migrated.warnings[:] = [w for w in migrated.warnings if "dropped" not in w.message]
    return migrated


def a_migration_that_drops_beat_11(old, **kwargs):
    # A beat it shouldn't drop, with a warning that says it did.
    del old["timelines"][BEATS]["components"]["11"]
    migrated = MIGRATE(old, **kwargs)
    place = f"/timelines/{BEATS}/components/11"
    message = "a beat dropped, as TiLiA drops it when it opens the file"
    migrated.warnings.append(tla.ReadWarning(place=place, line=None, message=message))
    return migrated


class TestADrop:
    @pytest.mark.parametrize(
        "change, place",
        [
            (a_beat_at(0.0), f"/timelines/{BEATS}/components/11: missing"),
            (
                a_beat_unit(beat_id="no beat"),
                f"/timelines/{BEATS}/components/9",
            ),
            (
                lambda content: None,
                "/timelines/30/components: missing from the copy, 3 amplitude bars",
            ),
        ],
        ids=["a beat", "a beat unit", "amplitude bars"],
    )
    def test_without_its_warning_is_a_difference(
        self, folders_with, monkeypatch, capsys, change, place
    ):
        content = old_file()
        change(content)
        folders = folders_with(content)
        monkeypatch.setattr(reader, "migrate", a_migration_without_its_warnings)

        assert check_migration.main(folders) == 1

        out = capsys.readouterr().out
        assert place in out
        assert "without its warning" in out

    @pytest.mark.parametrize("time", [None, 9.952 + 1], ids=["any", "within 2 s"])
    def test_of_a_beat_it_should_keep_is_a_difference_with_a_warning(
        self, folders_with, monkeypatch, capsys, time
    ):
        content = old_file()
        if time is not None:
            # Past the media's end, by less than TiLiA's 2 s: kept.
            a_beat_at(time)(content)
        folders = folders_with(content)
        monkeypatch.setattr(reader, "migrate", a_migration_that_drops_beat_11)

        assert check_migration.main(folders) == 1

        out = capsys.readouterr().out
        assert f"/timelines/{BEATS}/components/11: missing from the copy, was" in out


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(
            path.name,
            marks=[needs_chords] if b'"HARMONY' in path.read_bytes().upper() else [],
        )
        for path in sorted(OLD.glob("*.tla"))
    ],
)
def test_every_old_file_of_the_tests_has_no_difference(tmp_path, name, capsys):
    folders = tmp_path / "source", tmp_path / "copy"
    for folder in folders:
        folder.mkdir()
        shutil.copy(OLD / name, folder / name)

    assert check_migration.main([str(f) for f in folders]) == 0, capsys.readouterr().out


class TestACorpus:
    def test_a_source_without_a_tla_file_is_refused(self, tmp_path, capsys):
        folders = tmp_path / "source", tmp_path / "copy"
        for folder in folders:
            folder.mkdir()

        assert check_migration.main([str(f) for f in folders]) == 2

        assert "no .tla file in SOURCE" in capsys.readouterr().err

    def test_a_source_without_a_tla_file_writes_nothing(self, tmp_path, capsys):
        source, copy_of = tmp_path / "source", tmp_path / "copy"
        source.mkdir()
        (source / ".hid.tla").write_bytes(b"{}")
        (source / "notes.txt").write_text("notes")
        copy_of.mkdir()
        shutil.copy(OLD / "0.0.96.tla", copy_of / "old.tla")
        before = contents(tmp_path)

        assert check_migration.main([str(source), str(copy_of)]) == 2

        assert "skipped: 1 hidden, 1 not .tla" in capsys.readouterr().err
        assert contents(tmp_path) == before

    def test_what_isnt_in_it_is_left_alone_and_counted(self, source, copied, capsys):
        for folder in (source, copied):
            (folder / ".hid.tla").write_bytes(b"{ not json")
            (folder / "notes.txt").write_text("notes")
            (folder / "sub" / "cover.png").write_bytes(b"\x89PNG")
            (folder / ".hidden").mkdir()
            (folder / ".hidden" / "other.tla").write_bytes(b"{ not json")
        (copied / ".only.tla").write_bytes(b"{ not json")

        assert check_migration.main([str(source), str(copied)]) == 0

        out = capsys.readouterr().out
        assert "SOURCE: 4 .tla files, skipped: 2 hidden, 2 not .tla" in out
        assert "COPY: 4 .tla files, skipped: 3 hidden, 2 not .tla" in out
        assert "4 files, 0 with a difference." in out
        assert (copied / ".hid.tla").read_bytes() == b"{ not json"


def reindent(path):
    path.write_text(json.dumps(json.loads(path.read_bytes()), indent=4), "utf-8")


class TestAFileInTheCurrentFormat:
    def test_isnt_written(self, source, copied, capsys):
        file = copied / CURRENT
        before = file.read_bytes(), file.stat().st_mtime_ns

        assert check_migration.main([str(source), str(copied)]) == 0

        assert (file.read_bytes(), file.stat().st_mtime_ns) == before

    def test_in_another_layout_is_said_and_isnt_a_difference(
        self, source, copied, capsys
    ):
        for folder in (source, copied):
            reindent(folder / CURRENT)
        file = copied / CURRENT
        before = file.read_bytes(), file.stat().st_mtime_ns

        assert check_migration.main([str(source), str(copied)]) == 0

        out = capsys.readouterr().out
        assert f"{CURRENT} (from {tla.FORMAT_VERSION}): no difference" in out
        assert "not in the writer's layout" in out
        assert "the copy isn't what the original migrates to" not in out
        assert "a second read and write changed its bytes" not in out
        assert (file.read_bytes(), file.stat().st_mtime_ns) == before

    def test_in_the_writers_layout_isnt_said_to_be_otherwise(
        self, source, copied, capsys
    ):
        assert check_migration.main([str(source), str(copied)]) == 0

        assert "not in the writer's layout" not in capsys.readouterr().out

    def test_its_content_is_compared(self, source, copied, capsys):
        edit(copied / CURRENT, lambda content: content.update(app_name="Another"))

        assert check_migration.main([str(source), str(copied)]) == 1

        out = capsys.readouterr().out
        assert "/app_name: " in out
        assert f"{S4} (from 0.6.0): no difference" in out

    def test_a_second_write_that_changes_it_is_a_difference(
        self, source, copied, monkeypatch, capsys
    ):
        write = tla.write
        writes = {}

        def drifting(path, doc, **kwargs):
            done = write(path, doc, **kwargs)
            writes[path] = writes.get(path, 0) + 1
            if writes[path] == 2:
                Path(path).write_bytes(Path(path).read_bytes() + b"\n")
            return done

        monkeypatch.setattr(check_migration.tla, "write", drifting)

        assert check_migration.main([str(source), str(copied)]) == 1

        out = capsys.readouterr().out
        assert f"{CURRENT} (from {tla.FORMAT_VERSION}): differences: 1" in out
        assert "a second read and write changed its bytes" in out

    def test_nothing_stays_beside_it_when_the_write_fails(
        self, source, copied, monkeypatch, capsys
    ):
        write = tla.write

        def failing(path, doc, **kwargs):
            write(path, doc, **kwargs)
            if ".check" in str(path):
                raise RuntimeError("a write that fails")

        monkeypatch.setattr(check_migration.tla, "write", failing)
        before = contents(copied).keys()

        assert check_migration.main([str(source), str(copied)]) == 1

        assert "RuntimeError: a write that fails" in capsys.readouterr().out
        assert contents(copied).keys() == before


class TestChordsAndKeys:
    @pytest.mark.parametrize(
        "rules, music21, says",
        [
            (True, True, "music21 is installed: chords and keys were checked."),
            (True, False, "music21 isn't installed (the `harmony` extra): chords and"),
            (
                False,
                True,
                "music21 is installed, and this core doesn't check the rules",
            ),
            (False, False, "music21 isn't installed (the `harmony` extra), and this"),
        ],
    )
    def test_the_first_line_says_whether_they_were_checked(
        self, source, copied, monkeypatch, capsys, rules, music21, says
    ):
        if rules:
            monkeypatch.setattr(
                check_migration.tla, "BrokenRules", ValueError, raising=False
            )
        else:
            monkeypatch.delattr(check_migration.tla, "BrokenRules", raising=False)
        monkeypatch.setattr(check_migration, "harmony_available", lambda: music21)

        check_migration.main([str(source), str(copied)])

        first = capsys.readouterr().out.splitlines()[0]
        assert first.startswith(says)
        assert ("weren't checked" in first) == (not (rules and music21))


class TestTheReport:
    def test_prints_a_files_warnings_and_they_arent_differences(
        self, source, copied, capsys
    ):
        assert check_migration.main([str(source), str(copied)]) == 0

        out = capsys.readouterr().out
        assert 'warning: line 65: formal_function "chorus" dropped' in out
        assert "Warnings, which aren't differences: 7." in out

    def test_cuts_a_long_list_of_warnings_short(self, folders_with, capsys):
        content = old_file()
        for index in range(30):
            components_of(content, HIERARCHIES)[f"{1000 + index}"] = {
                "start": 0.0,
                "end": 1.0,
                "level": 5 + index,
                "kind": "HIERARCHY",
                "formal_type": "dropped",
            }

        assert check_migration.main(folders_with(content)) == 0

        out = capsys.readouterr().out
        assert out.count("  warning: ") == check_migration.SHOWN_PER_FILE
        assert "more\n" in out

    def test_prints_a_label_a_console_cant_show(self, source, copied):
        # As it has to: by the console's own rule, printing it would stop the report.
        tla.migrate_folder(copied, apply=True)
        edit(
            copied / S4,
            lambda content: first_with(content, "label")[1].update(
                label="\u4e2d\u6587"
            ),
        )

        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(source), str(copied)],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "ascii"},
        )

        assert result.returncode == 1, result.stdout + result.stderr
        assert "Traceback" not in result.stderr
        assert "\\u4e2d\\u6587" in result.stdout
        assert "4 files, 1 with a difference." in result.stdout


class TestALink:
    def test_into_source_is_refused(self, source, copied, capsys):
        (copied / S4).unlink()
        try:
            os.symlink(source / S4, copied / S4)
        except OSError as error:
            pytest.skip(f"can't make a link here: {error}")
        original = contents(source)

        assert check_migration.main([str(source), str(copied)]) == 2

        assert "a link into SOURCE" in capsys.readouterr().err
        assert contents(source) == original

    def test_into_source_is_refused_where_it_cant_be_made(
        self, source, copied, monkeypatch, capsys
    ):
        # Windows needs a privilege to make one: this is what one would look like.
        realpath = os.path.realpath
        link = os.fspath(copied / S4)

        def as_if_a_link(path, **kwargs):
            return realpath(source / S4 if os.fspath(path) == link else path, **kwargs)

        monkeypatch.setattr(os.path, "realpath", as_if_a_link)
        original = contents(source)

        assert check_migration.main([str(source), str(copied)]) == 2

        assert "a link into SOURCE" in capsys.readouterr().err
        assert contents(source) == original

    def test_a_hard_link_leaves_the_source_as_it_was(self, source, copied, capsys):
        # The writer replaces it, so that it no longer shares the file.
        (copied / S4).unlink()
        try:
            os.link(source / S4, copied / S4)
        except OSError as error:
            pytest.skip(f"can't make a hard link here: {error}")
        original = contents(source)

        assert check_migration.main([str(source), str(copied)]) == 0

        assert contents(source) == original
        assert tla.read(copied / S4).format_version == tla.FORMAT_VERSION


class TestAFolderThatIsntACopy:
    def test_a_file_only_in_the_source_is_a_difference(self, source, copied, capsys):
        (copied / S4).unlink()
        before = contents(copied)

        assert check_migration.main([str(source), str(copied)]) == 1

        assert f"{S4}: only in SOURCE" in capsys.readouterr().out
        assert contents(copied) == before

    def test_a_file_only_in_the_copy_is_a_difference(self, source, copied, capsys):
        shutil.copy(OLD / "0.0.96.tla", copied / "more.tla")
        before = contents(copied)

        assert check_migration.main([str(source), str(copied)]) == 1

        assert "more.tla: only in COPY" in capsys.readouterr().out
        assert contents(copied) == before

    @pytest.mark.parametrize("copy_is", ["the same", "inside", "around"])
    def test_a_folder_that_overlaps_is_refused(
        self, source, copied, copy_is, capsys, tmp_path
    ):
        given = {"the same": source, "inside": source / "sub", "around": tmp_path}
        (tmp_path / "another.tla").write_bytes((OLD / "0.0.96.tla").read_bytes())
        before = contents(tmp_path)

        assert check_migration.main([str(source), str(given[copy_is])]) == 2

        assert "overlap" in capsys.readouterr().err
        assert contents(tmp_path) == before

    @pytest.mark.parametrize("which", [0, 1])
    def test_what_isnt_a_folder_is_refused(self, source, copied, which, capsys):
        folders = [str(source), str(copied)]
        folders[which] = str(source / "nothing")

        assert check_migration.main(folders) == 2

        assert "not a folder" in capsys.readouterr().err

    def test_a_migrated_source_and_an_old_copy_are_refused(
        self, source, copied, capsys
    ):
        # The arguments the wrong way round, once the copy has been migrated with
        # `tilia migrate`: the original would be migrated next.
        tla.migrate_folder(copied, apply=True)
        original = contents(source)

        assert check_migration.main([str(copied), str(source)]) == 2

        assert "the wrong way round" in capsys.readouterr().err
        assert contents(source) == original


class TestAFileThatCantBeRead:
    def test_is_a_difference_and_the_others_are_still_checked(
        self, source, copied, capsys
    ):
        for folder in (source, copied):
            (folder / "broken.tla").write_bytes(b"{ not json")

        assert check_migration.main([str(source), str(copied)]) == 1

        out = capsys.readouterr().out
        assert "broken.tla: differences: 1" in out
        assert "unreadable: can't read" in out
        assert f"{S4} (from 0.6.0): no difference" in out
        assert "5 files, 1 with a difference." in out

    def test_an_error_in_the_core_is_a_difference_and_the_others_go_on(
        self, source, copied, monkeypatch, capsys
    ):
        read = tla.read

        def failing(path):
            if Path(path).name == S4:
                raise RuntimeError("an error in the core")
            return read(path)

        monkeypatch.setattr(check_migration.tla, "read", failing)

        assert check_migration.main([str(source), str(copied)]) == 1

        out = capsys.readouterr().out
        assert "RuntimeError: an error in the core" in out
        assert f"{CURRENT} (from {tla.FORMAT_VERSION}): no difference" in out


def test_differences_counts_lists_of_other_lengths_and_types():
    before = {"a": [1, 2], "b": 1}
    after = {"a": [1], "b": 1.0}

    found = list(check_migration.differences(before, after))

    assert found == [
        "/a: 2 items in the original, 1 here",
        "/b: 1 in the original, 1.0 in the copy",
    ]


def test_a_long_value_is_shortened_in_a_report():
    assert len(check_migration.short("x" * 500)) < 200
