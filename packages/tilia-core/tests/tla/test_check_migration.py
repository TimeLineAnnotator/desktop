"""`scripts/check_migration.py`, on a small folder made here (SC-002)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tilia_core import tla
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
        "file, lose, missing",
        [
            (S4, lose_a_label, "'label "),
            (S4, lose_a_time, "'time "),
            (S4, lose_a_colour, "'colour "),
            (COMMENTS, lose_a_comment, "'comment "),
            (COMMENTS, lose_a_mark, "'mark tag=p1"),
            (S4, lose_a_metadata_entry, "'metadata title "),
            (S4, remove_component, "'component hierarchy"),
            (S4, remove_timeline, "'timeline hierarchy"),
            (SCORE, lose_a_score, "'score SVG "),
        ],
    )
    def test_is_a_difference(
        self, source, copied, monkeypatch, file, lose, missing, capsys
    ):
        for other in {S4, COMMENTS, SCORE} - {file}:
            (source / other).unlink()
            (copied / other).unlink()
        monkeypatch.setattr(reader, "migrate", a_migration_that_does(lose))

        assert check_migration.main([str(source), str(copied)]) == 1

        out = capsys.readouterr().out
        assert f"missing from the copy: {missing}" in out


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
