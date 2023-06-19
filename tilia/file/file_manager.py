from __future__ import annotations
import logging
from pathlib import Path
import json

from tilia.exceptions import TiliaFileWriteError, UserCancel, MediaMetadataFieldNotFound
from tilia.file.common import compare_tilia_data, write_tilia_file_to_disk
from tilia.requests import listen, Post, Get, serve, get, post
from tilia.file.tilia_file import TiliaFile
from tilia.file.media_metadata import MediaMetadata

logger = logging.getLogger(__name__)


class FileManager:
    FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION = [
        "media_metadata",
        "timelines",
        "media_path",
    ]

    def __init__(self):
        serve(self, Get.MEDIA_METADATA, lambda: self.file.media_metadata)
        serve(self, Get.MEDIA_TITLE, lambda: self.file.media_metadata["title"])
        listen(self, Post.PLAYER_MEDIA_LOADED, self.on_media_loaded)
        listen(self, Post.REQUEST_SAVE, self.on_save_request)
        listen(self, Post.REQUEST_SAVE_AS, self.on_save_as_request)
        listen(self, Post.REQUEST_SAVE_TO_PATH, self.on_save_to_path_request)
        listen(self, Post.REQUEST_FILE_OPEN, self.on_request_open_file)
        listen(self, Post.REQUEST_FILE_NEW, self.on_request_new_file)
        listen(
            self,
            Post.REQUEST_SET_MEDIA_METADATA_FIELD,
            self.on_set_media_metadata_field,
        )
        listen(
            self,
            Post.REQUEST_ADD_MEDIA_METADATA_FIELD,
            self.on_add_media_metadata_field,
        )
        listen(
            self,
            Post.REQUEST_REMOVE_MEDIA_METADATA_FIELD,
            self.on_remove_media_metadata_field,
        )

        self.file = TiliaFile()

    def on_save_request(self):
        """Saves tilia file to current file path."""
        try:
            app_state = get(Get.APP_STATE)
            self.save(app_state, app_state["file_path"])
        except TiliaFileWriteError:
            post(Post.REQUEST_DISPLAY_ERROR, "Error when saving file.")

    def on_save_as_request(self):
        """Prompts user for a path, and saves tilia file to it."""
        try:
            path = get(Get.SAVE_PATH_FROM_USER, get(Get.MEDIA_TITLE))
        except UserCancel:
            return

        try:
            self.save(get(Get.APP_STATE), path)
        except TiliaFileWriteError:
            post(Post.REQUEST_DISPLAY_ERROR, "Error when saving file.")

    def on_save_to_path_request(self, path: Path):
        """Saves tilia file to specified path."""
        try:
            self.save(get(Get.APP_STATE), path)
        except TiliaFileWriteError:
            post(Post.REQUEST_DISPLAY_ERROR, "Error when saving file.")

    def on_request_open_file(self):
        logger.info("Processing open file request.")
        try:
            self.ask_save_changes_if_modified() and self.on_save_request()
        except UserCancel:
            return
        logger.debug("Getting path of file to open.")
        try:
            file_path = get(Get.TILIA_FILE_PATH_FROM_USER)
            logger.debug(f"Got path {file_path}")
        except UserCancel:
            return

        post(Post.REQUEST_CLEAR_APP)

        self.open(file_path)

    def on_request_new_file(self):
        logger.debug("Processing new file request.")
        try:
            self.ask_save_changes_if_modified() and self.on_save_request()
        except UserCancel:
            return

        post(Post.REQUEST_CLEAR_APP)
        post(Post.REQUEST_SETUP_BLANK_FILE)

    def on_set_media_metadata_field(self, field_name: str, value: str) -> None:
        """Sets the value of a sinle media metadata field."""
        if field_name not in self.file.media_metadata:
            raise MediaMetadataFieldNotFound(f"Field {field_name} not found.")

        self.file.media_metadata[field_name] = value

    def on_add_media_metadata_field(self, field: str, index: int) -> None:
        """Add a field to media metadata at index"""
        new_metadata = {}
        for i, (key, value) in enumerate(self.file.media_metadata.items()):
            # adds new field when iteration is at index
            if i == index:
                new_metadata[field] = value

            new_metadata[key] = value

        self.file.media_metadata = new_metadata

    def on_remove_media_metadata_field(self, field: str) -> None:
        """Remove a field from media metadata"""
        try:
            self.file.media_metadata.pop(field)
        except KeyError:
            raise MediaMetadataFieldNotFound(f"Field {field} not found.")

    def save(self, data: dict, path: Path | str):
        logger.info("Saving file...")
        write_tilia_file_to_disk(TiliaFile(**data), str(path))

        logger.info("File saved.")
        self.file = TiliaFile(**data)

    def open(self, file_path: str | Path):
        logger.info(f"Opening file path {file_path}.")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["file_path"] = file_path
        self.file = TiliaFile(**data)
        post(Post.REQUEST_LOAD_FILE, self.file)

    def new(self):
        self.file = TiliaFile()

    def is_file_modified(self, current_data: dict) -> bool:
        return not compare_tilia_data(current_data, self.file.__dict__)
        # can't use dataclasses.asdict() here
        # because it doesn't work with OrderedDict, which is media_metadata's type

    def on_media_loaded(self, path: str | Path, length: float, *_) -> None:
        logger.debug(f"Updating media metadata 'media path' to '{path}'")
        self.file.media_path = str(path)
        logger.debug(f"Updating media metadata 'media length' to '{length}'")
        self.file.media_metadata["media length"] = length

    def set_media_metadata(self, value: MediaMetadata):
        self.file.media_metadata = value

    def set_media_path(self, value: Path | str):
        self.file.media_path = str(value)

    def set_media_duration(self, value: float):
        self.file.media_metadata["media length"] = value

    def set_timelines(self, value: dict):
        self.file.timelines = value

    def update_file(self, data: dict):
        """Directly updates the file manager's file, bypassing opening."""
        self.file = TiliaFile(**data)

    def get_file_path(self):
        return self.file.file_path

    def ask_save_changes_if_modified(self) -> bool:
        logger.debug("Checking if save is necessary...")
        if not self.is_file_modified(get(Get.APP_STATE)):
            logger.debug("File was not modified. Save is not necessary.")
            return False

        logger.debug("Changes were made. Asking if user wants to save file...")
        response = get(Get.SHOULD_SAVE_CHANGES_FROM_USER)
        if response:
            logger.debug("User chose to save file.")
            return True
        elif response is False:
            logger.debug("User chose not to save file.")
            return False
        elif response is None:
            raise UserCancel()
