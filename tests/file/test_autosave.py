import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

import tilia.file.autosave as autosave_module
from tilia import dirs
from tilia.file.autosave import (
    autosave,
    get_autosave_filename,
    is_in_autosaves_folder,
)
from tilia.requests import Post, post
from tilia.settings import settings

DATE = "2026-11-19_101010_"
EXTENSION = ".tla"
MAX_NAME_LENGTH = 255
# What the date and the extension leave for the title.
TITLE_ROOM = MAX_NAME_LENGTH - len(DATE) - len(EXTENSION)
UNSAFE_CHARACTERS = ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]
CONTROL_CHARACTERS = ["\n", "\r", "\t", "\x00", "\x1f", "\x7f"]
# A character beyond U+FFFF, which takes two UTF-16 units.
NOTE = "\U0001f3b5"


class AtTenPastTen(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 11, 19, 10, 10, 10)


@pytest.fixture(autouse=True)
def at_ten_past_ten(monkeypatch):
    monkeypatch.setattr(autosave_module, "datetime", AtTenPastTen)


@pytest.fixture
def autosaves_folder(tmp_path, monkeypatch):
    """The tests don't set up TiLiA's folders, so the autosaves folder would
    be the working directory, where making room for an autosave deletes the
    oldest files. A folder two levels inside tmp_path, so that a test can see
    a file written next to it."""
    folder = tmp_path / "TiLiA" / "autosaves"
    folder.mkdir(parents=True)
    monkeypatch.setattr(dirs, "autosaves_path", folder)
    return folder


def set_title(title: str):
    post(Post.MEDIA_METADATA_FIELD_SET, "title", title)


def files_under(folder: Path) -> list[str]:
    return sorted(
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    )


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


class TestAutosaveFilename:
    def test_a_character_a_file_name_cant_hold_becomes_an_underscore(self):
        set_title("Symphony No. 5: I. Allegro")
        assert get_autosave_filename() == (
            "2026-11-19_101010_Symphony No. 5_ I. Allegro.tla"
        )

    @pytest.mark.parametrize("character", UNSAFE_CHARACTERS)
    def test_each_character_windows_refuses(self, character):
        set_title(f"a{character}b{character}")
        assert get_autosave_filename() == f"{DATE}a_b_{EXTENSION}"

    @pytest.mark.parametrize("character", CONTROL_CHARACTERS)
    def test_a_control_character(self, character):
        set_title(f"Allegro{character}con brio")
        assert get_autosave_filename() == f"{DATE}Allegro_con brio{EXTENSION}"

    @pytest.mark.parametrize(
        "title",
        [
            "Symphony No. 5 — I. Allegro con brio (1808) [live], take #2",
            "Ça & ça; 100% 'ok'! {a+b=c} ~@$^`",
            "Op. 67.",
            "Allegro ",
            NOTE + " Allegro",
            "",
        ],
    )
    def test_a_title_with_none_of_those_characters_keeps_its_name(self, title):
        set_title(title)
        assert get_autosave_filename() == f"{DATE}{title}{EXTENSION}"

    def test_a_title_that_fits_exactly_is_not_cut(self):
        title = "a" * TITLE_ROOM
        set_title(title)
        assert get_autosave_filename() == f"{DATE}{title}{EXTENSION}"

    def test_a_long_title_is_cut_to_fit(self):
        set_title("a" * 300)
        name = get_autosave_filename()
        assert name == f"{DATE}{'a' * TITLE_ROOM}{EXTENSION}"
        assert len(name) == MAX_NAME_LENGTH

    def test_a_long_title_is_cut_after_its_characters_are_replaced(self):
        set_title(":" * 300)
        assert get_autosave_filename() == f"{DATE}{'_' * TITLE_ROOM}{EXTENSION}"

    @pytest.mark.parametrize("end", ["..", "  ", ". ", " ."])
    def test_a_cut_leaves_no_dot_or_space_at_the_end_of_the_title(self, end):
        kept = "a" * (TITLE_ROOM - len(end))
        set_title(kept + end + "b" * 100)
        assert get_autosave_filename() == f"{DATE}{kept}{EXTENSION}"

    def test_a_cut_doesnt_split_a_character_that_takes_two_utf16_units(self):
        # Windows counts a name's length in UTF-16 units. Here only one is
        # left for the note, which takes two.
        kept = "a" * (TITLE_ROOM - 1)
        set_title(kept + NOTE + "b" * 100)
        name = get_autosave_filename()
        assert name == f"{DATE}{kept}{EXTENSION}"
        assert utf16_length(name) <= MAX_NAME_LENGTH

    def test_a_long_title_of_characters_that_take_two_utf16_units(self):
        set_title(NOTE * 300)
        name = get_autosave_filename()
        assert name == DATE + NOTE * (TITLE_ROOM // 2) + EXTENSION
        assert utf16_length(name) <= MAX_NAME_LENGTH


class TestAutosave:
    @pytest.mark.parametrize(
        "title, name",
        [
            (
                "Symphony No. 5: I. Allegro",
                "2026-11-19_101010_Symphony No. 5_ I. Allegro.tla",
            ),
            (
                "Symphony No. 5/I. Allegro",
                "2026-11-19_101010_Symphony No. 5_I. Allegro.tla",
            ),
            ("/../../x", "2026-11-19_101010__.._.._x.tla"),
            ("..\\..\\x", "2026-11-19_101010_.._.._x.tla"),
            ("..", "2026-11-19_101010_...tla"),
        ],
    )
    def test_a_title_with_a_character_a_file_name_cant_hold(
        self, tilia, tmp_path, autosaves_folder, title, name
    ):
        set_title(title)

        autosave(tilia.get_app_state())

        # Written in the autosaves folder, and nothing anywhere else.
        assert files_under(tmp_path) == [f"TiLiA/autosaves/{name}"]
        written = json.loads((autosaves_folder / name).read_text(encoding="utf-8"))
        assert written["media_metadata"]["title"] == title

    def test_isnt_written_if_its_name_isnt_in_the_autosaves_folder(
        self, tilia, tmp_path, autosaves_folder, monkeypatch
    ):
        older = autosaves_folder / "2026-11-18_101010_Older.tla"
        older.write_text("{}")
        settings.set("auto-save", "max_stored_files", 1)
        monkeypatch.setattr(
            autosave_module, "get_autosave_filename", lambda: "../Elsewhere.tla"
        )

        with patch.object(autosave_module, "logger") as logger:
            autosave(tilia.get_app_state())

        # Nothing written, and no older autosave deleted to make room.
        assert files_under(tmp_path) == ["TiLiA/autosaves/2026-11-18_101010_Older.tla"]
        logger.error.assert_called_once()


class TestIsInAutosavesFolder:
    def test_a_name_in_the_folder(self, autosaves_folder):
        assert is_in_autosaves_folder(autosaves_folder / "2026-11-19_101010_x.tla")

    @pytest.mark.parametrize(
        "name", ["..", ".", "../x.tla", "y/x.tla", "y/../../x.tla", "../autosaves"]
    )
    def test_a_name_that_isnt_in_the_folder(self, autosaves_folder, name):
        assert not is_in_autosaves_folder(autosaves_folder / name)

    def test_a_path_elsewhere(self, tmp_path, autosaves_folder):
        assert not is_in_autosaves_folder(tmp_path / "x.tla")
