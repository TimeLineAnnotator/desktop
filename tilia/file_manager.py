from __future__ import annotations

import dataclasses
import json
from datetime import datetime

from tilia.events import subscribe, Event
from tilia.exceptions import UserCancelledSaveError, UserCancelledOpenError
from tilia.files import TiliaFile
from tilia.main import TiLiA, logger
from tilia.timelines.hash_timelines import hash_timeline_collection_data
from tilia.timelines.timeline_kinds import TimelineKind


class FileManager:
    JSON_CONFIG = {"indent": 2}

    FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION = ['media_metadata', 'timelines', 'media_path']

    def __init__(self, app: TiLiA, file: TiliaFile = None):
        subscribe(self, Event.PLAYER_MEDIA_LOADED, self.on_media_loaded)
        subscribe(self, Event.FILE_REQUEST_TO_SAVE, self.save)
        subscribe(self, Event.FILE_REQUEST_TO_OPEN, self.open)

        self._app = app

        self._file = file if file else TiliaFile()

    @property
    def is_file_modified(self):

        current_file_data = self._get_save_parameters()

        if len(current_file_data['timelines']) == 1:
            tl = list(current_file_data['timelines'].values())[0]
            if tl['kind'] == TimelineKind.SLIDER_TIMELINE.name:
                current_file_data['timelines'] = {}

        for attr in FileManager.FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION:
            if attr == 'timelines':
                saved_file_hash = hash_timeline_collection_data(self._file.timelines)
                current_file_hash = hash_timeline_collection_data(current_file_data['timelines'])
                if saved_file_hash != current_file_hash:
                    return True
            elif current_file_data[attr] != getattr(self._file, attr):
                return True
        return False

    def _update_file(self, **kwargs) -> None:
        for keyword, value in kwargs.items():
            logger.debug(f"Updating _file paramenter '{keyword}' to '{value}'")
            setattr(self._file, keyword, value)

    def save(self, save_as: bool) -> None:
        logger.info(f"Saving _file...")
        self._file.file_path = self.get_file_path(save_as)
        try:
            save_params = self._get_save_parameters()
        except UserCancelledSaveError:
            return

        self._update_file(**save_params)

        logger.debug(f"Using path '{self._file.file_path}'")
        with open(self._file.file_path, "w", encoding="utf-8") as file:
            json.dump(dataclasses.asdict(self._file), file, **self.JSON_CONFIG)

        logger.info(f"File saved.")

    def new(self):
        logger.debug(f"Processing new _file request.")
        try:
            self.ask_save_if_necessary()
        except UserCancelledOpenError:
            return

        self._app.clear_app()

        self._file = TiliaFile()

        logger.info(f"New _file created.")

    def open(self):
        logger.debug(f"Processing open _file request.")
        self.ask_save_if_necessary()
        logger.debug(f"Getting path of _file to open.")
        try:
            file_path = self._app.ui.get_file_open_path()
            logger.debug(f"Got path {file_path}")
        except UserCancelledOpenError:
            return

        self._app.clear_app()

        self._open_file_by_path(file_path)

    def _open_file_by_path(self, file_path: str):
        logger.debug(f"Opening _file path {file_path}.")

        with open(file_path, "r", encoding="utf-8") as file:
            file_dict = json.load(file)

        self._file = TiliaFile(**file_dict)
        self._app.load_file(self._file)

    def ask_save_if_necessary(self) -> None:
        if not self.is_file_modified:
            return

        response = self._app.ui.ask_save_changes()

        if response:
            logger.debug("User chose to save _file before opening.")
            self.save(save_as=False)
        elif response is False:
            logger.debug("User chose not to save _file before opening.")
            pass
        elif response is None:
            logger.debug("User cancelled _file open.")
            raise UserCancelledOpenError()

    def _get_save_parameters(self) -> dict:
        return {
            "media_metadata": dict(self._app.media_metadata),
            "timelines": self._app.get_timelines_as_dict(),
            "media_path": self._app.get_media_path(),
            "file_path": self._file.file_path,
        }

    def on_media_loaded(self, media_path: str, *_) -> None:
        logger.debug(f"Updating _file media_path to '{media_path}'")
        self._file.media_path = media_path

    def get_file_path(self, save_as: bool) -> str:
        if not self._file.file_path or save_as:
            return self._app.ui.get_file_save_path(self.get_default_filename())
        else:
            return self._file.file_path

    def get_default_filename(self) -> str:
        return f"{self._app.get_media_title()} {datetime.now().strftime('%d-%m-%Y %H%M%S')}"

    def clear(self) -> None:
        logger.debug(f"Clearing _file manager...")
        self._file = TiliaFile()