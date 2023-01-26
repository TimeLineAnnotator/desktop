from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, OrderedDict

from tilia import globals_, dirs
from tilia import settings
from tilia.repr import default_str

if TYPE_CHECKING:
    from tilia._tilia import TiLiA

import dataclasses
import json
import time
from datetime import datetime
from threading import Thread

from tilia.events import subscribe, Event
from tilia.exceptions import UserCancelledSaveError, UserCancelledOpenError
from tilia.files import TiliaFile

from tilia.timelines.hash_timelines import hash_timeline_collection_data
from tilia.timelines.timeline_kinds import TimelineKind

logger = logging.getLogger(__name__)


class FileManager:
    JSON_CONFIG = {"indent": 2}

    FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION = [
        "media_metadata",
        "timelines",
        "media_path",
    ]

    def __init__(self, app: TiLiA, file: TiliaFile = None):
        subscribe(self, Event.PLAYER_MEDIA_LOADED, self.on_media_loaded)
        subscribe(self, Event.FILE_REQUEST_TO_SAVE, self.save)
        subscribe(self, Event.FILE_REQUEST_TO_OPEN, self.open)

        self._app = app

        self._file = file if file else TiliaFile()

        self._last_autosave_data = None
        self._autosave_exception_list = []
        self._autosave_thread = Thread(
            target=self._auto_save_loop,
            args=(self._autosave_exception_list,),
            daemon=True,
        )
        if settings.get("auto-save", "interval"):
            self._autosave_thread.start()

    def __str__(self):
        return default_str(self)

    def was_file_modified(self):

        current_tilia_data = self.get_save_parameters()

        # necessary tweak when there's only a slider timeline in file
        if len(current_tilia_data["timelines"]) == 1:
            tl = list(current_tilia_data["timelines"].values())[0]
            if tl["kind"] == TimelineKind.SLIDER_TIMELINE.name:
                current_tilia_data["timelines"] = {}

        return not compare_tilia_data(
            current_tilia_data, dataclasses.asdict(self._file)
        )

    def _update_file(self, **kwargs) -> None:
        for keyword, value in kwargs.items():
            logger.debug(f"Updating file paramenter '{keyword}' to '{value}'")
            setattr(self._file, keyword, value)

    def save(self, save_as: bool) -> None:
        logger.info(f"Saving file...")
        self._file.file_path = self.get_file_path(save_as)
        self._update_file(**self.get_save_parameters())

        logger.debug(f"Using path '{self._file.file_path}'")
        with open(self._file.file_path, "w", encoding="utf-8") as file:
            json.dump(dataclasses.asdict(self._file), file, **self.JSON_CONFIG)

        logger.info(f"File saved.")

    def autosave(self):
        logger.debug("Autosaving file...")

        try:
            save_params = self.get_save_parameters()
        except AttributeError:
            return

        with open(self.get_autosave_path(), "w", encoding="utf-8") as file:
            json.dump(save_params, file, **self.JSON_CONFIG)

        self._last_autosave_data = save_params

        logger.debug("Autosaved file.")

    def needs_auto_save(self):
        if not self._last_autosave_data:
            return True

        return not compare_tilia_data(
            self._last_autosave_data, self.get_save_parameters()
        )

    def _auto_save_loop(self, *_) -> None:
        while True:
            try:
                time.sleep(settings.get("auto-save", "interval"))
                logger.debug(f"Checking if autosave is necessary...")
                if self.needs_auto_save():
                    make_room_for_new_autosave()
                    self.autosave()
                else:
                    logger.debug(f"Autosave is not necessary.")
            except Exception as excp:
                self._autosave_exception_list.append(excp)
                _raise_save_loop_exception(excp)

    def get_autosave_path(self):
        return Path(dirs.autosaves_path, self.get_autosave_filename())

    def get_autosave_filename(self):
        if self._file.media_metadata["title"]:
            title = self._file.media_metadata["title"] + "." + globals_.FILE_EXTENSION
        else:
            title = "Untitled" + "." + globals_.FILE_EXTENSION

        date = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return f"{date}_{title}"

    def new(self):
        logger.debug(f"Processing new file request.")

        self.ask_save_if_necessary()
        self._app.clear_app()
        self._file = TiliaFile()

        logger.info(f"New file created.")

    def open(self):
        logger.debug(f"Processing open file request.")
        self.ask_save_if_necessary()
        logger.debug(f"Getting path of file to open.")
        try:
            file_path = self._app.ui.get_file_open_path()
            logger.debug(f"Got path {file_path}")
        except UserCancelledOpenError:
            return

        self._app.clear_app()

        self.open_file_by_path(file_path)

    def open_file_by_path(self, file_path: str):
        logger.debug(f"Opening file path {file_path}.")

        with open(file_path, "r", encoding="utf-8") as file:
            file_dict = json.load(file)

        file_dict["file_path"] = file_path
        self._file = TiliaFile(**file_dict)
        self._app.load_file(self._file)

    def ask_save_if_necessary(self) -> None:
        logger.debug(f"Checking if save is necessary...")
        if not self.was_file_modified():
            logger.debug(f"File was not modified. Save is not necessary.")
            return

        logger.debug(f"Save is necessary. Asking if user wants to save file...")
        response = self._app.ui.ask_save_changes()

        if response:
            logger.debug("User chose to save file.")
            self.save(save_as=False)
        elif response is False:
            logger.debug("User chose not to save file.")
            pass
        elif response is None:
            logger.debug("User cancelled dialog.")
            raise UserCancelledOpenError()

    def get_save_parameters(self) -> dict:
        return {
            "media_metadata": dict(self._app.media_metadata),
            "timelines": self._app.get_timelines_as_dict(),
            "media_path": self._app.media_path,
            "file_path": self._file.file_path,
        }

    def restore_state(self, media_metadata: OrderedDict, media_path: str) -> None:
        self._file.media_metadata = media_metadata
        self._file.media_path = media_path

    def on_media_loaded(self, media_path: str, *_) -> None:
        logger.debug(f"Updating file media_path to '{media_path}'")
        self._file.media_path = media_path

    def get_file_path(self, save_as: bool) -> str:
        if not self._file.file_path or save_as:
            return self._app.ui.get_file_save_path(self.get_default_filename())
        else:
            return self._file.file_path

    def get_default_filename(self) -> str:
        return f"{self._app.media_title} {datetime.now().strftime('%d-%m-%Y %H%M%S')}"

    def clear(self) -> None:
        logger.debug(f"Clearing file manager...")
        self._file = TiliaFile()


def _raise_save_loop_exception(excp: Exception):
    raise excp


def compare_tilia_data(data1: dict, data2: dict) -> bool:
    """Returns True if data1 is equivalent to data2, False otherwise."""

    ATTRS_TO_CHECK = ["media_metadata", "timelines", "media_path"]

    for attr in ATTRS_TO_CHECK:
        if attr == "timelines":
            if hash_timeline_collection_data(
                data1["timelines"]
            ) != hash_timeline_collection_data(data2["timelines"]):
                return False
        elif data1[attr] != data2[attr]:
            return False
    return True


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
