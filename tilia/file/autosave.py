import os
import re
import time
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import Callable

import tilia.constants
from tilia import dirs
from tilia.log import logger
from tilia.requests import Get, get
from tilia.settings import settings

from .common import are_tilia_data_equal, write_tilia_file_to_disk
from .tilia_file import TiliaFile


class AutoSaver:
    def __init__(self, get_app_state: Callable[[], dict]):
        self.get_app_state = get_app_state
        self._last_autosave_data = None
        self._autosave_exception_list: list[Exception] = []
        self._autosave_thread = Thread(
            target=self._auto_save_loop,
            args=(self._autosave_exception_list,),
            daemon=True,
        )

        if settings.get("auto-save", "interval_(seconds)"):
            self._autosave_thread.start()

    def _auto_save_loop(self, *_) -> None:
        while True:
            try:
                time.sleep(settings.get("auto-save", "interval_(seconds)"))
                if self.needs_auto_save():
                    data = self.get_app_state()
                    autosave(data)
                    self._last_autosave_data = data
            except Exception as excp:
                self._autosave_exception_list.append(excp)
                _raise_save_loop_exception(excp)

    def needs_auto_save(self):
        if not self._last_autosave_data:
            return True

        return not are_tilia_data_equal(self._last_autosave_data, self.get_app_state())


def _raise_save_loop_exception(excp: Exception):
    raise excp


def autosave(data: dict):
    autosave_path = get_autosave_path()
    if not is_in_autosaves_folder(autosave_path):
        logger.error(
            f"Autosave failed: {autosave_path} is not in the autosaves folder."
        )
        return
    make_room_for_new_autosave()
    write_tilia_file_to_disk(TiliaFile(**data), autosave_path)
    logger.debug(f"Autosave: {autosave_path}")


def get_autosave_path():
    return Path(dirs.autosaves_path, get_autosave_filename())


def is_in_autosaves_folder(path: Path) -> bool:
    """Whether `path` names a file directly inside the autosaves folder, once
    both are resolved."""
    return Path(path).resolve().parent == Path(dirs.autosaves_path).resolve()


# The characters Windows refuses in a file name, and control characters. The
# list is the same on every system, so that a title gives the same name on all.
UNSAFE_FILENAME_CHARACTERS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
# The longest file name most file systems accept, counted as Windows counts it:
# in UTF-16 units, two for a character beyond U+FFFF.
MAX_FILENAME_LENGTH = 255


def get_autosave_filename() -> str:
    """The date and the file's title. A character a file name can't hold
    becomes "_", and a title too long for the name is cut to fit."""
    title = UNSAFE_FILENAME_CHARACTERS.sub("_", str(get(Get.MEDIA_TITLE)))
    date = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    start = f"{date}_"
    end = f".{tilia.constants.FILE_EXTENSION}"
    room = MAX_FILENAME_LENGTH - _utf16_length(start) - _utf16_length(end)
    return start + _cut_to_length(title, room) + end


def _utf16_length(text: str) -> int:
    return sum(2 if ord(character) > 0xFFFF else 1 for character in text)


def _cut_to_length(text: str, length: int) -> str:
    """`text` if it takes `length` UTF-16 units or fewer. Otherwise, as many of
    its characters as fit, a character beyond U+FFFF whole or not at all, and
    without the dots and spaces the cut leaves at its end."""
    used = 0
    for index, character in enumerate(text):
        used += _utf16_length(character)
        if used > length:
            return text[:index].rstrip(". ")
    return text


def get_autosaves_paths() -> list[str]:
    return [
        str(Path(dirs.autosaves_path, file)) for file in os.listdir(dirs.autosaves_path)
    ]


def delete_older_autosaves(amount: int):
    paths_by_creation_date = sorted(
        get_autosaves_paths(),
        key=lambda x: os.path.getctime(x),
    )
    for path in paths_by_creation_date[:amount]:
        os.remove(path)


def make_room_for_new_autosave() -> None:
    if (
        remaining_autosaves := len(get_autosaves_paths())
        - settings.get("auto-save", "max_stored_files")
    ) >= 0:
        delete_older_autosaves(remaining_autosaves + 1)
