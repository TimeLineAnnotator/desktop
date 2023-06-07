import os
import time
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import Callable
import logging

from tilia import settings, globals_, dirs
from .common import compare_tilia_data, write_tilia_file_to_disk
from .tilia_file import TiliaFile
from tilia.requests import get, Get

logger = logging.getLogger(__name__)


class AutoSaver:
    def __init__(self, get_app_state: Callable[[], dict]):
        self.get_app_state = get_app_state
        self._last_autosave_data = None
        self._autosave_exception_list = []
        self._autosave_thread = Thread(
            target=self._auto_save_loop,
            args=(self._autosave_exception_list,),
            daemon=True,
        )

        if settings.get("auto-save", "interval"):
            self._autosave_thread.start()

    def _auto_save_loop(self, *_) -> None:
        while True:
            try:
                time.sleep(settings.get("auto-save", "interval"))
                logger.debug("Checking if autosave is necessary...")
                if self.needs_auto_save():
                    data = self.get_app_state()
                    autosave(data)
                    self._last_autosave_data = data
                else:
                    logger.debug("Autosave is not necessary.")
            except Exception as excp:
                self._autosave_exception_list.append(excp)
                _raise_save_loop_exception(excp)

    def needs_auto_save(self):
        if not self._last_autosave_data:
            return True

        return not compare_tilia_data(self._last_autosave_data, self.get_app_state())


def _raise_save_loop_exception(excp: Exception):
    raise excp


def autosave(data: dict):
    logger.debug("Autosaving file...")
    make_room_for_new_autosave()
    write_tilia_file_to_disk(TiliaFile(**data), get_autosave_path())
    logger.debug("Autosaved file.")


def get_autosave_path():
    return Path(dirs.autosaves_path, get_autosave_filename())


def get_autosave_filename():
    title = get(Get.MEDIA_TITLE)
    date = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"{date}_{title}.{globals_.FILE_EXTENSION}"


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
        - settings.get("auto-save", "max_saved_files")
    ) >= 0:
        delete_older_autosaves(remaining_autosaves + 1)
