"""The check before saving (FR-006, FR-025–FR-028, FR-063; SC-004; user story 3).

A save over the file open states the fingerprint the file was read or last written
with. A file changed, deleted, recreated or moved on disk since then is written over
only when the user chooses to; a file whose content didn't change, such as one
rewritten with other line endings or another key order, brings no question. The
first save of an old file asks once. The questions are `contracts/messages.md`'s,
rows 5–8, word for word.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.mock import PatchPost, Serve
from tests.utils import get_blank_file_data
from tilia.requests import Get, Post, get, post
from tilia.ui import commands
from tilia.ui.dialogs.basic import ChoiceMessageBox
from tilia.ui.format import format_media_time
from tilia_core import tla

FILES = Path(__file__).parents[2] / "packages" / "tilia-core" / "tests" / "tla"
EMPTY = FILES / "golden" / "empty.tla"
EVERY_KIND = FILES / "golden" / "every-kind.tla"

# contracts/messages.md, rows 5–8: the title, the message, the buttons.
CHANGED = (
    "File changed on disk",
    "'{}' has changed on disk since you opened it. Saving will overwrite those"
    " changes.",
    ["Overwrite", "Save As…", "Cancel"],
)
MOVED = (
    "File moved or deleted",
    "'{}' has been moved or deleted since you opened it.",
    ["Save", "Save As…", "Cancel"],
)
IN_USE = (
    "Save file",
    "'{}' is in use by another program, such as a sync client or a virus scanner."
    " Nothing was written.",
    ["Retry", "Cancel"],
)
OLD = (
    "Save in the new format",
    "'{}' was made with TiLiA {}. Saving writes TiLiA's new file format, which"
    " TiLiA 0.7 and earlier can't open.",
    ["Save", "Save As…", "Cancel"],
)
SAVE_AS = "Save As…"
CANCEL = "Cancel"


def question(row, *args) -> tuple[str, str, list[str]]:
    title, message, buttons = row
    return title, message.format(*args), buttons


class Answers(Serve):
    """Answers the questions before saving with `answers`, in order, keeping each
    question asked and what was on disk at `watched` when it was (None for no file).
    A question beyond the answers fails the test."""

    def __init__(self, *answers: str | None, watched: Path | None = None):
        super().__init__(Get.FROM_USER_CHOICE, None)
        self.answers = list(answers)
        self.watched = watched
        self.asked: list[tuple[str, str, list[str]]] = []
        self.on_disk: list[bytes | None] = []

    def _callback(self, title, message, buttons):
        self.asked.append((title, message, list(buttons)))
        if self.watched is not None:
            self.on_disk.append(
                self.watched.read_bytes() if self.watched.exists() else None
            )
        assert self.answers, f"asked one question more than expected: {title}"
        return self.answers.pop(0)


def open_file(path: Path) -> bool:
    """Opens `path`, as the File menu does, declining to look for media that isn't
    there and closing the warnings it opens with."""
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, False),
        Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
        Serve(Get.FROM_USER_SHOW_PROBLEMS, None),
    ):
        return commands.execute("file.open", path)


def save() -> bool:
    return commands.execute("file.save")


def save_as(path: Path) -> bool:
    return commands.execute("file.save_as", str(path))


def edit(notes: str = "mine") -> None:
    """An edit in TiLiA, unsaved."""
    post(Post.MEDIA_METADATA_FIELD_SET, "notes", notes)


def notes_in(path: Path) -> str | None:
    return tla.read(path).metadata.get("notes")


def a_file(folder: Path, name: str = "file.tla", composer: str | None = None) -> Path:
    """A file the core wrote into `folder`."""
    doc = tla.read(EMPTY)
    if composer is not None:
        doc.metadata["composer"] = composer
    path = folder / name
    tla.write(path, doc)
    return path


def an_old_file(folder: Path, name: str = "old.tla") -> Path:
    """A file as TiLiA 0.7 saved it."""
    data = get_blank_file_data()
    data["version"] = "0.7.0"
    data["media_metadata"]["media length"] = 100.0
    path = folder / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# What another program does to the file open, and which question it brings.
def changed(path: Path) -> None:
    doc = tla.read(path)
    doc.metadata["composer"] = "Another program"
    tla.write(path, doc)


def deleted(path: Path) -> None:
    path.unlink()


def recreated(path: Path) -> None:
    path.unlink()
    a_file(path.parent, path.name, composer="Another program")


def moved(path: Path) -> None:
    elsewhere = path.parent / "elsewhere"
    elsewhere.mkdir()
    path.rename(elsewhere / path.name)


CHANGES = [(changed, CHANGED), (deleted, MOVED), (recreated, CHANGED), (moved, MOVED)]
CHANGE_IDS = [change.__name__ for change, _ in CHANGES]


@pytest.fixture
def opened(qtui, tilia, tls, tmp_path) -> Path:
    """A file the core wrote, open in TiLiA, with an edit not saved yet."""
    path = a_file(tmp_path)
    assert open_file(path)
    edit()
    assert tilia.is_file_modified()
    return path


def on_disk(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def assert_open(tilia, path: Path) -> None:
    """`path` is the file open."""
    assert Path(tilia.file_manager.file.file_path).resolve() == path.resolve()


class TestAFileChangedOnDisk:
    """User story 3's scenarios 1, 2 and 4, for each change another program can
    make, with each answer."""

    @pytest.mark.parametrize("change, row", CHANGES, ids=CHANGE_IDS)
    def test_is_written_over_only_when_the_user_chooses_to(
        self, opened, tilia, change, row
    ):
        change(opened)
        theirs = on_disk(opened)
        write = row[2][0]  # Overwrite, or Save for a file gone

        with Answers(write, watched=opened) as answers:
            assert save()

        # Asked, with nothing written until the user chose.
        assert answers.asked == [question(row, "file.tla")]
        assert answers.on_disk == [theirs]
        assert notes_in(opened) == "mine"
        assert_open(tilia, opened)
        assert not tilia.is_file_modified()

    @pytest.mark.parametrize("change, row", CHANGES, ids=CHANGE_IDS)
    def test_cancel_writes_nothing_and_keeps_the_changes(
        self, opened, tilia, change, row
    ):
        change(opened)
        theirs = on_disk(opened)

        with (
            Answers(CANCEL) as answers,
            PatchPost("tilia.file.file_manager", Post.FILE_SAVED) as file_saved,
        ):
            assert not save()

        assert answers.asked == [question(row, "file.tla")]
        assert on_disk(opened) == theirs
        assert tilia.is_file_modified()
        assert_open(tilia, opened)
        file_saved.assert_not_called()

    @pytest.mark.parametrize("change, row", CHANGES, ids=CHANGE_IDS)
    def test_save_as_writes_elsewhere(self, opened, tilia, tmp_path, change, row):
        change(opened)
        theirs = on_disk(opened)
        other = tmp_path / "other.tla"

        with (
            Answers(SAVE_AS) as answers,
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, str(other))),
        ):
            assert save()

        assert answers.asked == [question(row, "file.tla")]
        assert on_disk(opened) == theirs
        assert notes_in(other) == "mine"
        assert_open(tilia, other)
        assert not tilia.is_file_modified()

    def test_save_as_cancelled_in_the_dialog_writes_nothing(self, opened, tilia):
        changed(opened)
        theirs = on_disk(opened)

        with Answers(SAVE_AS), Serve(Get.FROM_USER_SAVE_PATH_TILIA, (False, "")):
            assert not save()

        assert on_disk(opened) == theirs
        assert tilia.is_file_modified()

    def test_closing_the_question_is_cancel(self, opened, tilia):
        changed(opened)
        theirs = on_disk(opened)

        with Answers(None):
            assert not save()

        assert on_disk(opened) == theirs
        assert tilia.is_file_modified()

    @pytest.mark.parametrize("change, row", CHANGES, ids=CHANGE_IDS)
    def test_a_second_save_doesn_t_ask(self, opened, change, row):
        change(opened)
        with Answers(row[2][0]):
            assert save()
        edit("mine, again")

        with Answers() as answers:
            assert save()

        assert not answers.asked
        assert notes_in(opened) == "mine, again"


class TestAFileWhoseContentDidntChange:
    """User story 3's scenarios 3 and 5: the question is asked on content, never on
    bytes or dates (T1, rule 1)."""

    def test_other_line_endings_bring_no_question(self, opened):
        opened.write_bytes(opened.read_bytes().replace(b"\n", b"\r\n"))

        with Answers() as answers:
            assert save()

        assert not answers.asked
        assert notes_in(opened) == "mine"

    def test_another_key_order_brings_no_question(self, opened):
        content = json.loads(opened.read_text(encoding="utf-8"))
        opened.write_text(
            json.dumps(dict(reversed(list(content.items()))), indent=4),
            encoding="utf-8",
        )

        with Answers() as answers:
            assert save()

        assert not answers.asked
        assert notes_in(opened) == "mine"

    def test_a_newer_date_brings_no_question(self, opened):
        os.utime(opened, (2_000_000_000, 2_000_000_000))

        with Answers() as answers:
            assert save()

        assert not answers.asked

    def test_a_successful_save_then_another_doesn_t_ask(self, opened):
        with Answers() as answers:
            assert save()
            edit("mine, again")
            assert save()

        assert not answers.asked
        assert notes_in(opened) == "mine, again"


class TestAFileHeldOpen:
    """User story 3's scenario 6: another program holds the file open (WP3's
    `FileInUse`, which the core raises on Windows after a short retry)."""

    @staticmethod
    def held_open(monkeypatch, times: int, unchecked_only: bool = False) -> None:
        """The next `times` writes find the file held open; with `unchecked_only`,
        the next `times` writes that check nothing."""
        write = tla.write
        held = [times]

        def held_write(path, doc, **kwargs):
            if held[0] and not (unchecked_only and kwargs.get("expect") is not None):
                held[0] -= 1
                raise tla.FileInUse(path)
            return write(path, doc, **kwargs)

        monkeypatch.setattr(tla, "write", held_write)

    def test_writes_nothing_and_says_so(self, opened, tilia, monkeypatch):
        before = opened.read_bytes()
        self.held_open(monkeypatch, 1)

        with Answers(CANCEL) as answers:
            assert not save()

        assert answers.asked == [question(IN_USE, "file.tla")]
        assert opened.read_bytes() == before
        assert tilia.is_file_modified()

    def test_retry_writes_once_it_is_free(self, opened, tilia, monkeypatch):
        self.held_open(monkeypatch, 2)

        with Answers("Retry", "Retry") as answers:
            assert save()

        assert answers.asked == [question(IN_USE, "file.tla")] * 2
        assert notes_in(opened) == "mine"
        assert not tilia.is_file_modified()

    def test_retry_after_overwrite_still_overwrites(self, opened, monkeypatch):
        changed(opened)
        self.held_open(monkeypatch, 1, unchecked_only=True)

        # The first write finds the file changed; the second, without the check,
        # finds it held open.
        with Answers("Overwrite", "Retry") as answers:
            assert save()

        assert [asked[0] for asked in answers.asked] == [CHANGED[0], IN_USE[0]]
        assert notes_in(opened) == "mine"


class TestWhatEachWriteExpects:
    """FR-025 and FR-028: a save over the file open states the fingerprint it was
    read or last written with; Save As expects no file at a new path, and checks
    nothing at a path the save dialog confirmed overwriting."""

    @staticmethod
    def expected(monkeypatch) -> list:
        """What each write states it expects."""
        write = tla.write
        expects = []

        def spy(path, doc, **kwargs):
            expects.append(kwargs.get("expect"))
            return write(path, doc, **kwargs)

        monkeypatch.setattr(tla, "write", spy)
        return expects

    def test_a_save_states_the_fingerprint_read(self, opened, tilia, monkeypatch):
        read = tla.fingerprint(opened)
        expects = self.expected(monkeypatch)

        assert save()

        assert expects == [read]
        assert tilia.file_manager.file.document.fingerprint == tla.fingerprint(opened)

    def test_the_next_save_states_the_fingerprint_written(self, opened, monkeypatch):
        assert save()
        written = tla.fingerprint(opened)
        edit("mine, again")
        expects = self.expected(monkeypatch)

        assert save()

        assert expects == [written]

    def test_save_as_to_a_new_path_expects_no_file(self, opened, tmp_path, monkeypatch):
        expects = self.expected(monkeypatch)

        assert save_as(tmp_path / "new.tla")

        assert expects == [tla.ABSENT]

    def test_save_as_over_a_file_confirmed_checks_nothing(
        self, opened, tmp_path, monkeypatch
    ):
        other = a_file(tmp_path, "other.tla", composer="Another program")
        expects = self.expected(monkeypatch)

        with Answers() as answers:
            assert save_as(other)

        assert expects == [None]
        assert not answers.asked
        assert notes_in(other) == "mine"

    def test_save_as_over_the_file_open_checks_nothing(self, opened, monkeypatch):
        # The save dialog confirmed overwriting it (FR-028).
        changed(opened)
        expects = self.expected(monkeypatch)

        with Answers() as answers:
            assert save_as(opened)

        assert expects == [None]
        assert not answers.asked
        assert notes_in(opened) == "mine"

    def test_a_file_that_appears_before_save_as_writes_is_kept(
        self, opened, tmp_path, tilia, tilia_errors, monkeypatch
    ):
        other = tmp_path / "new.tla"
        write = tla.write

        def appearing(path, doc, **kwargs):
            # Another program writes a file there after the save dialog.
            write(path, tla.read(EMPTY))
            return write(path, doc, **kwargs)

        monkeypatch.setattr(tla, "write", appearing)
        with Answers() as answers:
            assert not save_as(other)

        assert not answers.asked
        assert notes_in(other) is None  # the other program's file
        assert tilia.is_file_modified()
        assert_open(tilia, opened)
        assert tilia_errors.errors[-1]["title"] == "Save file"


class TestAnOldFile:
    """FR-006: the first save of an old file asks once (row 8)."""

    @pytest.fixture
    def old(self, qtui, tilia, tls, tmp_path) -> Path:
        path = an_old_file(tmp_path)
        assert open_file(path)
        return path

    def test_its_first_save_asks_once(self, old, tilia):
        before = old.read_bytes()

        with Answers("Save", watched=old) as answers:
            assert save()
        edit()
        with Answers() as again:
            assert save()

        assert answers.asked == [question(OLD, "old.tla", "0.7.0")]
        assert answers.on_disk == [before]
        assert not again.asked
        assert tla.read(old).format_version == tla.FORMAT_VERSION
        assert notes_in(old) == "mine"

    def test_cancel_writes_nothing(self, old, tilia):
        before = old.read_bytes()

        with Answers(CANCEL):
            assert not save()

        assert old.read_bytes() == before

    def test_save_as_writes_elsewhere_and_doesn_t_ask_again(self, old, tilia, tmp_path):
        before = old.read_bytes()
        other = tmp_path / "new.tla"

        with (
            Answers(SAVE_AS) as answers,
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, str(other))),
        ):
            assert save()
        edit()
        with Answers() as again:
            assert save()

        assert answers.asked == [question(OLD, "old.tla", "0.7.0")]
        assert not again.asked
        assert old.read_bytes() == before
        assert notes_in(other) == "mine"

    def test_save_as_elsewhere_doesn_t_ask(self, old, tmp_path):
        before = old.read_bytes()
        other = tmp_path / "new.tla"

        with Answers() as answers:
            assert save_as(other)
            edit()
            assert save()

        assert not answers.asked
        assert old.read_bytes() == before
        assert notes_in(other) == "mine"

    def test_save_as_over_it_asks(self, old):
        with Answers("Save") as answers:
            assert save_as(old)

        assert answers.asked == [question(OLD, "old.tla", "0.7.0")]
        assert tla.read(old).format_version == tla.FORMAT_VERSION

    def test_a_cancelled_save_asks_again(self, old):
        with Answers(CANCEL):
            assert not save()

        with Answers("Save") as answers:
            assert save()

        assert answers.asked == [question(OLD, "old.tla", "0.7.0")]

    @pytest.mark.parametrize("answer", ["Overwrite", CANCEL])
    def test_changed_between_read_and_save(self, old, answer):
        data = json.loads(old.read_text(encoding="utf-8"))
        data["media_metadata"]["composer"] = "Another program"
        old.write_text(json.dumps(data), encoding="utf-8")
        theirs = old.read_bytes()

        with Answers("Save", answer) as answers:
            assert save() == (answer == "Overwrite")

        assert answers.asked == [
            question(OLD, "old.tla", "0.7.0"),
            question(CHANGED, "old.tla"),
        ]
        if answer == "Overwrite":
            assert tla.read(old).format_version == tla.FORMAT_VERSION
        else:
            assert old.read_bytes() == theirs


# What asks to save changes first.
def open_another(tmp_path) -> None:
    other = a_file(tmp_path, "other.tla", composer="Other")
    assert not commands.execute("file.open", other)


def new_file(tmp_path) -> None:
    commands.execute("file.new")


def close(tmp_path) -> None:
    with PatchPost("tilia.app", Post.UI_EXIT) as exit_:
        commands.execute("tilia.close")
    exit_.assert_not_called()


ASKING = [open_another, new_file, close]
ASKING_IDS = [action.__name__ for action in ASKING]


class TestWhatAskedToSave:
    """Opening another file, a new file and closing TiLiA ask to save changes; a
    save cancelled, or one that fails, stops them, so the changes are kept
    (user story 3's scenario 2)."""

    @pytest.mark.parametrize("action", ASKING, ids=ASKING_IDS)
    def test_cancel_keeps_the_file_and_its_changes(
        self, opened, tilia, tmp_path, action
    ):
        changed(opened)
        theirs = opened.read_bytes()

        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            Answers(CANCEL) as answers,
        ):
            action(tmp_path)

        assert answers.asked == [question(CHANGED, "file.tla")]
        assert opened.read_bytes() == theirs
        assert_open(tilia, opened)
        assert get(Get.MEDIA_METADATA)["notes"] == "mine"
        assert tilia.is_file_modified()

    @pytest.mark.parametrize("action", ASKING, ids=ASKING_IDS)
    def test_a_failed_save_keeps_the_file_and_its_changes(
        self, opened, tilia, tmp_path, tilia_errors, action
    ):
        before = opened.read_bytes()
        os.chmod(opened, stat.S_IREAD)
        try:
            with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)), Answers():
                action(tmp_path)
        finally:
            os.chmod(opened, stat.S_IREAD | stat.S_IWRITE)

        assert opened.read_bytes() == before
        assert_open(tilia, opened)
        assert get(Get.MEDIA_METADATA)["notes"] == "mine"
        assert tilia_errors.errors[-1]["title"] == "Save file"


class TestARefusedSave:
    """FR-027 and FR-063: a save the core refuses writes nothing, and TiLiA says
    why."""

    def test_broken_rules_are_listed_one_per_line(
        self, qtui, tilia, tls, tmp_path, tilia_errors, monkeypatch
    ):
        path = tmp_path / "file.tla"
        tla.write(path, tla.read(EVERY_KIND))
        assert open_file(path)
        before = path.read_bytes()
        cadences = "019b76da-a805-7003-b62f-e431bbc11c02"
        hc = "019b76da-a828-7f55-9c48-91621b3d0c60"  # at 7 s
        problems = [
            tla.ReadWarning(
                f"/timelines/{cadences}/components/{hc}",
                12,
                "Time can't be past the end. Got '700'",
                cadences,
                hc,
            ),
            tla.ReadWarning("", None, "harmonies can't be checked"),
        ]

        def refused(path, doc, **kwargs):
            raise tla.BrokenRules(path, problems)

        monkeypatch.setattr(tla, "write", refused)
        assert not save()

        assert path.read_bytes() == before
        assert tilia_errors.errors[-1] == {
            "title": "Save file",
            "message": "Error when saving file.\n"
            f"Cadences, {format_media_time(7)}: Time can't be past the end."
            " Got '700'\n"
            "harmonies can't be checked",
        }

    def test_a_read_only_file_is_left_as_it_was(self, opened, tilia, tilia_errors):
        before = opened.read_bytes()
        os.chmod(opened, stat.S_IREAD)
        try:
            with Answers() as answers:
                assert not save()
        finally:
            os.chmod(opened, stat.S_IREAD | stat.S_IWRITE)

        assert not answers.asked
        assert opened.read_bytes() == before
        assert tilia.is_file_modified()
        assert tilia_errors.errors[-1]["title"] == "Save file"

    def test_a_failed_save_to_a_path_posts_no_file_saved(
        self, qtui, tilia, tmp_path, tilia_errors
    ):
        path = tmp_path / "missing folder" / "file.tla"

        with PatchPost("tilia.file.file_manager", Post.FILE_SAVED) as file_saved:
            post(Post.REQUEST_SAVE_TO_PATH, str(path))

        file_saved.assert_not_called()
        assert not path.exists()
        assert tilia_errors.errors[-1]["title"] == "Save file"

    def test_a_save_to_a_path_posts_file_saved(self, qtui, tilia, tmp_path):
        path = tmp_path / "file.tla"

        with PatchPost("tilia.file.file_manager", Post.FILE_SAVED) as file_saved:
            post(Post.REQUEST_SAVE_TO_PATH, str(path))

        file_saved.assert_called_once()
        assert path.exists()


class TestTheQuestion:
    """`Get.FROM_USER_CHOICE`, in TiLiA's window: a question with buttons of its
    own words, which replies with the one chosen."""

    @staticmethod
    def answering(text: str | None, shown: list):
        def exec_(box):
            shown.append(
                (
                    box.windowTitle(),
                    box.text(),
                    sorted(button.text() for button in box.buttons()),
                    box.escapeButton().text() if box.escapeButton() else None,
                )
            )
            if text is not None:
                next(b for b in box.buttons() if b.text() == text).click()
            return 0

        return exec_

    @pytest.mark.parametrize("answer", ["Overwrite", "Save As…", "Cancel"])
    def test_replies_with_the_button_chosen(self, qtui, answer):
        shown = []
        with patch.object(ChoiceMessageBox, "exec", self.answering(answer, shown)):
            reply = get(Get.FROM_USER_CHOICE, *question(CHANGED, "file.tla"))

        assert reply == answer
        assert shown == [
            (
                "File changed on disk",
                question(CHANGED, "file.tla")[1],
                sorted(CHANGED[2]),
                "Cancel",  # Escape and closing the question choose it
            )
        ]

    def test_closed_without_a_button_replies_none(self, qtui):
        shown = []
        with patch.object(ChoiceMessageBox, "exec", self.answering(None, shown)):
            reply = get(Get.FROM_USER_CHOICE, *question(IN_USE, "file.tla"))

        assert reply is None
