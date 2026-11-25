import json
import os
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.utils import get_blank_file_data
from tilia.file import file_manager
from tilia.requests import Get, Post, get, post
from tilia.ui.path import ensure_tla_extension
from tilia_core import tla


@pytest.mark.parametrize(
    "path, expected",
    [
        ("file.txt", "file.txt.tla"),
        ("file", "file.tla"),
        ("file.tla", "file.tla"),
    ],
)
def test_ensure_tla_extension(path, expected):
    result = ensure_tla_extension(Path(path))
    assert str(result) == expected


def test_save(cli, tmp_path):
    path = tmp_path / "test.tla"
    cli.parse_and_run(f'save "{str(path.resolve())}"')
    assert os.listdir(tmp_path) == [path.name]


def test_the_help_says_the_file_open_is_checked(cli, capsys):
    # TimeLineAnnotator/project-management#646, a.
    cli.parse_and_run("save --help")

    assert (
        "Examples:\n"
        "  # Save (prompts for overwrite if the file exists)\n"
        "  save /path/to/file.tla\n"
        "\n"
        "  # Save (overwrites without prompting)\n"
        "  save /path/to/file.tla --overwrite\n"
        "\n"
        "Saving to the file that is open checks it against the file on disk first,\n"
        "with or without --overwrite, as Save does in TiLiA's window.\n"
    ) in capsys.readouterr().out


def test_save_parent_is_file_fails(cli, tmp_path, tilia_errors):
    parent = tmp_path / "parent"
    parent.touch()
    save_path = tmp_path / "parent" / "file.tla"
    cli.parse_and_run(f'save "{str(save_path.resolve())}"')
    tilia_errors.assert_error()
    assert not save_path.exists()


def test_save_parent_doesnt_exist_fails(cli, tmp_path, tilia_errors):
    save_path = tmp_path / "parent" / "file.tla"
    cli.parse_and_run(f'save "{str(save_path.resolve())}"')
    tilia_errors.assert_error()
    assert not save_path.exists()


def test_save_overwrite_flag(cli, tmp_path):
    path = tmp_path / "file.tla"
    path.write_text("content")
    cli.parse_and_run(f'save "{str(path.resolve())}" --overwrite')
    assert path.read_text() != "content"


def test_save_overwrite_yes(cli, monkeypatch, tmp_path):
    path = tmp_path / "file.tla"
    path.write_text("content")
    monkeypatch.setattr("sys.stdin", StringIO("yes\n"))
    cli.parse_and_run(f'save "{str(path.resolve())}"')
    assert path.read_text() != "content"


def test_save_overwrite_no(cli, monkeypatch, tmp_path):
    path = tmp_path / "file.tla"
    path.write_text("content")
    monkeypatch.setattr("sys.stdin", StringIO("no\n"))
    cli.parse_and_run(f'save "{str(path.resolve())}"')
    assert path.read_text() == "content"


def test_save_invalid_save_path(cli, tmp_path, tilia_errors):
    path = tmp_path / "invalid" / "file.tla"
    cli.parse_and_run(f'save "{str(path.resolve())}"')
    tilia_errors.assert_error()


CHANGED = (
    "'file.tla' has changed on disk since you opened it. Saving will overwrite those"
    " changes. [Overwrite/Save As…/Cancel]: "
)
OLD = (
    "'old.tla' was made with TiLiA 0.7.0. Saving writes TiLiA's new file format,"
    " which TiLiA 0.7 and earlier can't open. [Save/Save As…/Cancel]: "
)


def changed_by_another_program(path: Path) -> bytes:
    doc = tla.read(path)
    doc.metadata["composer"] = "Another program"
    tla.write(path, doc)
    return path.read_bytes()


class TestTheCheckBeforeSaving:
    """`save` over the file open makes the check before saving, and asks in the
    terminal: the message, then the buttons as choices (FR-095;
    contracts/controls.md)."""

    @pytest.fixture
    def saved(self, cli, tmp_path) -> Path:
        """A file TiLiA's command line saved, open, with an edit not saved yet."""
        path = tmp_path / "file.tla"
        cli.parse_and_run(f'save "{path.resolve()}"')
        cli.parse_and_run("metadata set notes mine")
        return path

    @staticmethod
    def answering(monkeypatch, *answers: str) -> None:
        monkeypatch.setattr("sys.stdin", StringIO("".join(f"{a}\n" for a in answers)))

    def test_cancel_writes_nothing(self, cli, saved, monkeypatch, capsys):
        theirs = changed_by_another_program(saved)
        self.answering(monkeypatch, "cancel")

        cli.parse_and_run(f'save "{saved.resolve()}" --overwrite')

        assert CHANGED in capsys.readouterr().out
        assert saved.read_bytes() == theirs

    @pytest.mark.parametrize("answer", ["overwrite", "Overwrite", "OVERWRITE"])
    def test_overwrite_writes(self, cli, saved, monkeypatch, capsys, answer):
        changed_by_another_program(saved)
        self.answering(monkeypatch, answer)

        cli.parse_and_run(f'save "{saved.resolve()}" --overwrite')

        assert CHANGED in capsys.readouterr().out
        assert tla.read(saved).metadata.get("notes") == "mine"
        assert tla.read(saved).metadata["composer"] != "Another program"

    def test_asks_again_until_an_answer_is_a_button(
        self, cli, saved, monkeypatch, capsys
    ):
        theirs = changed_by_another_program(saved)
        self.answering(monkeypatch, "y", "", "cancel")

        cli.parse_and_run(f'save "{saved.resolve()}" --overwrite')

        assert capsys.readouterr().out.count(CHANGED) == 3
        assert saved.read_bytes() == theirs

    def test_the_end_of_the_input_is_cancel(self, cli, saved, monkeypatch, capsys):
        theirs = changed_by_another_program(saved)
        self.answering(monkeypatch)

        cli.parse_and_run(f'save "{saved.resolve()}" --overwrite')

        assert CHANGED in capsys.readouterr().out
        assert saved.read_bytes() == theirs

    @pytest.mark.parametrize("flag", ["", " --overwrite"], ids=["", "overwrite"])
    def test_the_file_open_goes_straight_to_the_check(
        self, cli, saved, monkeypatch, capsys, flag
    ):
        # As Save does in TiLiA's window: no "already exists" question, with or
        # without --overwrite (TimeLineAnnotator/project-management#632, b).
        theirs = changed_by_another_program(saved)
        self.answering(monkeypatch, "cancel")

        cli.parse_and_run(f'save "{saved.resolve()}"{flag}')

        out = capsys.readouterr().out
        assert "already exists" not in out
        assert CHANGED in out
        assert saved.read_bytes() == theirs

    @pytest.mark.parametrize("flag", ["", " --overwrite"], ids=["", "overwrite"])
    def test_the_file_open_unchanged_on_disk_is_saved_without_a_question(
        self, cli, saved, monkeypatch, capsys, flag
    ):
        self.answering(monkeypatch)

        cli.parse_and_run(f'save "{saved.resolve()}"{flag}')

        out = capsys.readouterr().out
        assert "already exists" not in out
        assert "changed on disk" not in out
        assert tla.read(saved).metadata.get("notes") == "mine"

    @pytest.mark.parametrize("overwrite", ["yes", "no"])
    def test_another_path_asks_today_s_question(
        self, cli, saved, tmp_path, monkeypatch, capsys, overwrite
    ):
        other = tmp_path / "other.tla"
        other.write_text("content")
        self.answering(monkeypatch, overwrite)

        cli.parse_and_run(f'save "{other.resolve()}"')

        assert f"File {other.resolve()} already exists. Overwrite?" in (
            capsys.readouterr().out
        )
        if overwrite == "yes":
            assert tla.read(other).metadata.get("notes") == "mine"
        else:
            assert other.read_text() == "content"

    def test_an_empty_answer_asks_again(self, cli, saved, monkeypatch, capsys):
        # The command line has no default button
        # (TimeLineAnnotator/project-management#631, b).
        theirs = changed_by_another_program(saved)
        self.answering(monkeypatch, "", "cancel")

        cli.parse_and_run(f'save "{saved.resolve()}"')

        assert capsys.readouterr().out.count(CHANGED) == 2
        assert saved.read_bytes() == theirs

    def test_a_file_unchanged_on_disk_asks_nothing(
        self, cli, saved, monkeypatch, capsys
    ):
        saved.write_bytes(saved.read_bytes().replace(b"\n", b"\r\n"))
        self.answering(monkeypatch)

        cli.parse_and_run(f'save "{saved.resolve()}" --overwrite')

        assert "changed on disk" not in capsys.readouterr().out
        assert tla.read(saved).metadata.get("notes") == "mine"

    def test_the_file_open_spelled_in_another_case(
        self, cli, saved, monkeypatch, capsys
    ):
        # On a file system that ignores case, as macOS's and Windows' do by
        # default, another spelling of the file open is the file open: it is
        # checked, not saved as.
        spelled = saved.with_stem(saved.stem.upper())  # FILE.tla
        if not spelled.exists():
            pytest.skip("this file system tells case apart")
        # As on macOS: normcase leaves case alone, and realpath keeps the case it is
        # given.
        monkeypatch.setattr(
            file_manager,
            "os",
            SimpleNamespace(
                path=SimpleNamespace(
                    normcase=lambda path: path,
                    realpath=os.path.abspath,
                    samefile=os.path.samefile,
                    lexists=os.path.lexists,
                )
            ),
        )
        theirs = changed_by_another_program(saved)
        self.answering(monkeypatch, "cancel")

        # What `save "<spelled>" --overwrite` posts where Path.resolve keeps the
        # case it is given, as on macOS; on Windows it gives the case on disk.
        post(Post.REQUEST_SAVE_TO_PATH, str(spelled))

        assert "has changed on disk since you opened it" in capsys.readouterr().out
        assert saved.read_bytes() == theirs

    def test_another_path_is_saved_as(self, cli, saved, tmp_path, monkeypatch, capsys):
        changed_by_another_program(saved)
        other = tmp_path / "other.tla"
        self.answering(monkeypatch)

        cli.parse_and_run(f'save "{other.resolve()}"')

        assert "changed on disk" not in capsys.readouterr().out
        assert tla.read(other).metadata.get("notes") == "mine"

    def test_an_old_file_asks_first(self, cli, tmp_path, monkeypatch, capsys):
        data = get_blank_file_data()
        data["version"] = "0.7.0"
        path = tmp_path / "old.tla"
        path.write_text(json.dumps(data), encoding="utf-8")
        cli.parse_and_run(f'open "{path.resolve()}"')
        self.answering(monkeypatch, "save")

        cli.parse_and_run(f'save "{path.resolve()}" --overwrite')

        assert OLD in capsys.readouterr().out
        assert tla.read(path).format_version == tla.FORMAT_VERSION


PATH_PROMPT = "Path to save the file [leave empty to cancel]: "


def answering(monkeypatch, *answers: str) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("".join(f"{a}\n" for a in answers)))


def notes_in(path: Path) -> str | None:
    return tla.read(path).metadata.get("notes")


def assert_open(tilia, path: Path) -> None:
    assert Path(tilia.file_manager.file.file_path).resolve() == path.resolve()


class TestSaveAs:
    """Save As… in a question before saving asks for a path in the terminal, and
    takes it as `save <path>` does (TimeLineAnnotator/project-management#618, a)."""

    @pytest.fixture
    def saved(self, cli, tmp_path) -> Path:
        """A file TiLiA's command line saved, open, with an edit not saved yet, and
        changed on disk since by another program."""
        path = tmp_path / "file.tla"
        cli.parse_and_run(f'save "{path.resolve()}"')
        cli.parse_and_run("metadata set notes mine")
        changed_by_another_program(path)
        return path

    def save_as(self, cli, saved, monkeypatch, *answers: str) -> bytes:
        """Saves over `saved`, answering Save As…, then `answers`; the bytes the other
        program left in `saved`."""
        theirs = saved.read_bytes()
        answering(monkeypatch, "save as", *answers)
        cli.parse_and_run(f'save "{saved.resolve()}" --overwrite')
        return theirs

    def test_asks_for_a_path_and_saves_there(
        self, cli, tilia, saved, tmp_path, monkeypatch, capsys
    ):
        other = tmp_path / "other.tla"

        theirs = self.save_as(cli, saved, monkeypatch, str(other))

        assert PATH_PROMPT in capsys.readouterr().out
        assert saved.read_bytes() == theirs
        assert notes_in(other) == "mine"
        assert_open(tilia, other)
        assert not tilia.is_file_modified()

    @pytest.mark.parametrize(
        "answers", [[""], ["   "], []], ids=["empty", "blank", "end"]
    )
    def test_an_empty_answer_is_cancel(
        self, cli, tilia, saved, monkeypatch, answers, tilia_errors
    ):
        theirs = self.save_as(cli, saved, monkeypatch, *answers)

        assert saved.read_bytes() == theirs
        assert os.listdir(saved.parent) == [saved.name]
        assert_open(tilia, saved)
        assert tilia.is_file_modified()
        tilia_errors.assert_no_error()

    def test_tla_is_added_when_missing(self, cli, saved, tmp_path, monkeypatch):
        self.save_as(cli, saved, monkeypatch, str(tmp_path / "other"))

        assert notes_in(tmp_path / "other.tla") == "mine"
        assert not (tmp_path / "other").exists()

    @pytest.mark.parametrize("overwrite", ["yes", "no"])
    def test_an_existing_file_asks_today_s_question(
        self, cli, saved, tmp_path, monkeypatch, capsys, overwrite
    ):
        other = tmp_path / "other.tla"
        other.write_text("content")

        self.save_as(cli, saved, monkeypatch, str(other), overwrite)

        assert f"File {other} already exists. Overwrite? [Yes/no]: " in (
            capsys.readouterr().out
        )
        if overwrite == "yes":
            assert notes_in(other) == "mine"
        else:
            assert other.read_text() == "content"

    def test_the_end_of_the_input_at_today_s_question_is_cancel(
        self, cli, tilia, saved, tmp_path, monkeypatch, tilia_errors
    ):
        other = tmp_path / "other.tla"
        other.write_text("content")

        # The input ends before an answer to "File … already exists. Overwrite?".
        theirs = self.save_as(cli, saved, monkeypatch, str(other))

        assert other.read_text() == "content"
        assert saved.read_bytes() == theirs
        assert_open(tilia, saved)
        assert tilia.is_file_modified()
        tilia_errors.assert_no_error()

    def test_a_path_it_can_t_save_to_says_why(
        self, cli, tilia, saved, tmp_path, monkeypatch, tilia_errors
    ):
        other = tmp_path / "missing" / "other.tla"

        theirs = self.save_as(cli, saved, monkeypatch, str(other))

        # validate_save_path's reason, as `save <path>` gives it.
        assert "Parent directory" in tilia_errors.errors[-1]["message"]
        assert saved.read_bytes() == theirs
        assert not other.parent.exists()
        assert tilia.is_file_modified()

    @pytest.mark.parametrize("exists", [False, True])
    def test_a_new_path_expects_no_file(
        self, cli, saved, tmp_path, monkeypatch, exists
    ):
        # FR-028: a path confirmed overwriting is written without the check.
        other = tmp_path / "other.tla"
        if exists:
            other.write_text("content")
        write, expects = tla.write, []

        def spy(path, doc, **kwargs):
            expects.append(kwargs.get("expect"))
            return write(path, doc, **kwargs)

        monkeypatch.setattr(tla, "write", spy)
        self.save_as(cli, saved, monkeypatch, str(other), "yes")

        # The first write, over the file open, found it changed.
        assert expects[1:] == [None if exists else tla.ABSENT]
        assert notes_in(other) == "mine"

    def test_an_old_file_s_question_too(
        self, cli, tilia, tmp_path, monkeypatch, capsys
    ):
        data = get_blank_file_data()
        data["version"] = "0.7.0"
        path = tmp_path / "old.tla"
        path.write_text(json.dumps(data), encoding="utf-8")
        before = path.read_bytes()
        cli.parse_and_run(f'open "{path.resolve()}"')
        other = tmp_path / "new.tla"
        answering(monkeypatch, "save as", str(other))

        cli.parse_and_run(f'save "{path.resolve()}" --overwrite')

        out = capsys.readouterr().out
        assert OLD in out and PATH_PROMPT in out
        assert path.read_bytes() == before
        assert tla.read(other).format_version == tla.FORMAT_VERSION
        assert_open(tilia, other)


class TestOpenWithUnsavedChangesOfAFileNeverSaved:
    """`open`, with unsaved changes of a file never saved, answered "yes" to saving
    them, asks for a path as Save As… does
    (TimeLineAnnotator/project-management#618, a)."""

    @pytest.fixture
    def other(self, cli, tmp_path) -> Path:
        """A file to open, while the file open is a new one with an edit."""
        path = tmp_path / "other.tla"
        cli.parse_and_run(f'save "{path.resolve()}"')
        cli.parse_and_run("clear --force")
        cli.parse_and_run("metadata set notes mine")
        return path

    def test_saves_there_then_opens(
        self, cli, tilia, other, tmp_path, monkeypatch, capsys
    ):
        saved = tmp_path / "saved.tla"
        answering(monkeypatch, "yes", str(saved))

        cli.parse_and_run(f'open "{other.resolve()}"')

        assert PATH_PROMPT in capsys.readouterr().out
        assert notes_in(saved) == "mine"
        assert_open(tilia, other)

    def test_an_empty_answer_keeps_the_file_and_its_changes(
        self, cli, tilia, other, tmp_path, monkeypatch
    ):
        answering(monkeypatch, "yes", "")

        cli.parse_and_run(f'open "{other.resolve()}"')

        assert sorted(os.listdir(tmp_path)) == ["other.tla"]
        assert tilia.file_manager.file.file_path == ""
        assert get(Get.MEDIA_METADATA)["notes"] == "mine"
        assert tilia.is_file_modified()
