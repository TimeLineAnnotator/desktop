import os
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
from tilia_core import tla

from .common import are_tilia_data_equal


class AutoSaver:
    def __init__(
        self,
        get_app_state: Callable[[], dict],
        copy_document: Callable[[], tla.Document],
    ):
        self.get_app_state = get_app_state
        self.copy_document = copy_document
        self._last_autosave_data = None
        self._autosave_thread = Thread(target=self._auto_save_loop, daemon=True)

        if settings.get("auto-save", "interval_(seconds)"):
            self._autosave_thread.start()

    def _auto_save_loop(self) -> None:
        while True:
            time.sleep(settings.get("auto-save", "interval_(seconds)"))
            self.auto_save_once()

    def auto_save_once(self) -> None:
        """Autosaves, if anything changed since the last autosave. A failure is
        logged, once, and the next change tries again: the loop goes on, for the
        rest of the session."""
        try:
            if not self.needs_auto_save():
                return
            data = self.get_app_state()
            # Tried once for this state: a failure isn't tried again until the
            # state changes, so that it is logged once.
            self._last_autosave_data = data
            autosave(self.copy_document())
        except Exception:
            logger.exception("Autosave failed; the next change tries again.")

    def needs_auto_save(self):
        if not self._last_autosave_data:
            return True

        return not are_tilia_data_equal(self._last_autosave_data, self.get_app_state())


def autosave(document: tla.Document) -> Path:
    """Writes `document` through the core into the autosaves folder, and returns the
    path written. It must be a copy of the open one (`OpenDocument.copy_for_writing`):
    a write makes the document it is given follow the file written."""
    make_room_for_new_autosave()
    autosave_path = get_autosave_path()
    tla.write(autosave_path, document)
    logger.debug(f"Autosave: {autosave_path}")
    return autosave_path


def get_autosave_path():
    return Path(dirs.autosaves_path, get_autosave_filename())


def get_autosave_filename():
    title = get(Get.MEDIA_TITLE)
    date = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"{date}_{title}.{tilia.constants.FILE_EXTENSION}"


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
