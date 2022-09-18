"""
Contains classes that relate to file and state management:
    - AutoSaver (not reimplemented yet);
    - MediaMetadata;
    - TiliaFile (centralizes informations that pertain to the .tla file).

"""
import logging
import os
import time
from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from threading import Thread

from tilia import globals_
from tilia.misc_enums import SingleOrMultiple

logger = logging.getLogger(__name__)


class AutoSaver:
    MAX_SAVED_FILES = 500
    SAVE_INTERVAL = 300
    AUTOSAVE_DIR = os.path.join(os.path.dirname(__file__), "../autosaves")

    def __init__(self):
        self.last_autosave_dict = dict()
        self.exception_list = []
        self._thread = Thread(target=self._auto_save_loop, args=(self.exception_list,))
        self._thread.start()

    def _auto_save_loop(self, exception_list: list) -> None:
        while True:
            try:
                time.sleep(self.SAVE_INTERVAL)
                if self.needs_auto_save():
                    self.make_room_for_new_autosave()
                    path = self.get_current_autosave_path()
                    do_file_save(path, auto_save=True)
            except Exception as excp:
                exception_list.append(excp)
                self._raise_save_loop_exception(excp)

    @staticmethod
    def _raise_save_loop_exception(excp: Exception):
        raise excp

    def needs_auto_save(self):
        if not globals_.MODIFIED:
            return False

        if (autosave_dict := create_save_dict()) != self.last_autosave_dict:
            self.last_autosave_dict = autosave_dict
            return True
        else:
            return False

    @staticmethod
    def get_file_name():
        if globals_.METADATA.title:
            title = globals_.METADATA.title + f"{globals_.FILE_EXTENSION}"
        else:
            title = f"Untitled - {globals_.FILE_EXTENSION}"
        date = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return f"{date}_{title}"

    def get_current_autosave_path(self):
        return os.path.join(self.AUTOSAVE_DIR, self.get_file_name())

    def make_room_for_new_autosave(self) -> None:
        if (
            remaining_autosaves := len(self.get_autosaves_paths())
            - self.MAX_SAVED_FILES
        ) >= 0:
            self.delete_older_autosaves(remaining_autosaves + 1)

    def get_autosaves_paths(self) -> list[str]:
        return [
            os.path.join(self.AUTOSAVE_DIR, file)
            for file in os.listdir(self.AUTOSAVE_DIR)
        ]

    def delete_older_autosaves(self, amount: int):
        paths_by_creation_date = sorted(
            self.get_autosaves_paths(),
            key=lambda x: os.path.getctime(x),
        )
        for path in paths_by_creation_date[:amount]:
            os.remove(path)


@dataclass
class MediaMetadata:
    title: str = "Untitled"
    composer: str = ""
    tonality: str = ""
    time_signature: str = ""
    performer: str = ""
    performance_year: str = ""
    arranger: str = ""
    composition_year: str = ""
    recording_year: str = ""
    form: str = ""
    instrumentation: str = ""
    genre: str = ""
    lyrics: str = ""
    audio_length: str = ""
    notes: str = ""

    def clear(self):
        for attr in self.__dict__:
            setattr(self, attr, "")


@dataclass
class TiliaFile:
    file_path: str = ""
    media_path: str = ""
    media_metadata: MediaMetadata = None
    timelines: dict = None
    app_name: str = globals_.APP_NAME
    version: str = globals_.VERSION