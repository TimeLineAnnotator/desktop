from __future__ import annotations
from pathlib import Path
import json

from tilia.exceptions import (
    TiliaFileWriteError,
    MediaMetadataFieldNotFound,
)
import tilia.exceptions
from tilia.file.common import are_tilia_data_equal, write_tilia_file_to_disk
from tilia.requests import listen, Post, Get, serve, get, post
from tilia.file.tilia_file import TiliaFile
from tilia.file.media_metadata import MediaMetadata
from tilia.settings import settings
import tilia.errors


class FileManager:
    FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION = [
        "media_metadata",
        "timelines",
        "media_path",
    ]

    def __init__(self):
        self._setup_requests()
        self.file = TiliaFile()

    def _setup_requests(self):
        LISTENS = {
            (Post.PLAYER_URL_CHANGED, self.on_player_url_changed),
            (Post.FILE_MEDIA_DURATION_CHANGED, self.on_player_duration_changed),
            (Post.FILE_SAVE, self.on_save_request),
            (Post.FILE_SAVE_AS, self.on_save_as_request),
            (Post.REQUEST_SAVE_TO_PATH, self.on_save_to_path_request),
            (Post.FILE_OPEN, self.on_request_open_file),
            (Post.FILE_OPEN_PATH, self.on_request_open_file_path),
            (Post.REQUEST_FILE_NEW, self.on_request_new_file),
            (
                Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH,
                self.on_import_media_metadata_request,
            ),
            (Post.MEDIA_METADATA_FIELD_SET, self.on_set_media_metadata_field),
            (Post.METADATA_UPDATE_FIELDS, self.on_update_media_metadata_fields),
        }

        SERVES = {
            (Get.MEDIA_METADATA, lambda: self.file.media_metadata),
            (
                Get.MEDIA_METADATA_REQUIRED_FIELDS,
                self.get_media_metadata_required_fields,
            ),
            (Get.MEDIA_TITLE, lambda: self.file.media_metadata["title"]),
        }

        for post, callback in LISTENS:
            listen(self, post, callback)

        for request, callback in SERVES:
            serve(self, request, callback)

    def on_save_request(self):
        """Saves tilia file to current file path."""
        app_state = get(Get.APP_STATE)
        if not app_state["file_path"]:
            # in case file has not been saved before
            return self.on_save_as_request()

        try:
            self.save(app_state, app_state["file_path"])
        except Exception as exc:
            tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, repr(exc))

        return True

    def on_save_as_request(self):
        """Prompts user for a path, and saves tilia file to it."""
        path, _ = get(Get.FROM_USER_SAVE_PATH_TILIA, get(Get.MEDIA_TITLE) + ".tla")
        if not path:
            return False

        try:
            self.save(get(Get.APP_STATE), path)
        except TiliaFileWriteError:
            tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, "Write Error.")

        return True

    def on_save_to_path_request(self, path: Path):
        """Saves tilia file to specified path."""
        try:
            self.save(get(Get.APP_STATE), path)
        except TiliaFileWriteError:
            tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, "Write Error")

    def on_close_modified_file(self):
        success, should_save = self.ask_save_changes_if_modified()
        if not success:
            return False
        if should_save:
            was_saved = self.on_save_request()
            if not was_saved:  # user might cancel save dialog
                return False  # we shouldn't proceed in that case

        return True

    def on_request_open_file(self):
        if not self.on_close_modified_file():
            return

        success, path = get(Get.FROM_USER_TILIA_FILE_PATH)
        if not success:
            return

        post(Post.APP_CLEAR)

        self.open(path)

    def on_request_open_file_path(self, path: str | Path):
        if not self.on_close_modified_file():
            return

        post(Post.APP_CLEAR)

        try:
            self.open(path)
        except FileNotFoundError:
            tilia.errors.display(tilia.errors.FILE_NOT_FOUND, path)
            settings.remove_from_recent_files(path)
            post(Post.APP_SETUP_FILE)

    def on_request_new_file(self):
        if not self.on_close_modified_file():
            return

        post(Post.APP_CLEAR)
        post(Post.APP_SETUP_FILE)

    def on_set_media_metadata_field(self, field_name: str, value: str) -> None:
        """Sets the value of a single media metadata field."""
        if field_name not in self.file.media_metadata:
            raise MediaMetadataFieldNotFound(f"Field {field_name} not found.")

        self.file.media_metadata[field_name] = value

    def on_update_media_metadata_fields(self, fields: list) -> None:
        new_metadata = {}
        for field in fields:
            value = self.file.media_metadata.get(
                field, self.file.media_metadata.get(field.lower(), "")
            )
            new_metadata[field] = value

        self.set_media_metadata(MediaMetadata.from_dict(new_metadata))

    def on_import_media_metadata_request(self, path: Path | str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.decoder.JSONDecodeError as err:
            tilia.errors.display(
                tilia.errors.MEDIA_METADATA_IMPORT_JSON_FAILED, path, repr(err)
            )
            return
        except FileNotFoundError:
            tilia.errors.display(tilia.errors.MEDIA_METADATA_IMPORT_FILE_FAILED, path)
            return

        self.set_media_metadata(MediaMetadata.from_dict(data))

    @staticmethod
    def get_media_metadata_required_fields():
        return list(MediaMetadata.REQUIRED_FIELDS)  # REQUIRED_FIELDS is a dict

    def save(self, data: dict, path: Path | str):
        write_tilia_file_to_disk(TiliaFile(**data), str(path))
        data["file_path"] = str(path.resolve()) if isinstance(path, Path) else path
        self.file = TiliaFile(**data)
        try:
            settings.update_recent_files(
                path, get(Get.WINDOW_GEOMETRY), get(Get.WINDOW_STATE)
            )
        except tilia.exceptions.NoReplyToRequest:
            settings.update_recent_files(path, None, None)

    def open(self, file_path: str | Path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["file_path"] = file_path
        self.file = TiliaFile(**data)
        post(Post.APP_FILE_LOAD, self.file)

    def new(self):
        self.file = TiliaFile()

    def is_file_modified(self, current_data: dict) -> bool:
        return not are_tilia_data_equal(current_data, self.file.__dict__)
        # can't use dataclasses.asdict() here because
        # it doesn't work with OrderedDict, which is media_metadata's type

    def on_player_url_changed(self, path: str | Path) -> None:
        self.file.media_path = str(path)

    def on_player_duration_changed(self, duration: float):
        self.file.media_metadata["media length"] = duration

    def set_media_metadata(self, value: MediaMetadata):
        self.file.media_metadata = value

    def set_media_duration(self, value: float):
        self.file.media_metadata["media length"] = value

    def set_timelines(self, value: dict):
        self.file.timelines = value

    def update_file(self, data: dict):
        """Directly updates the file manager's file, bypassing opening."""
        self.file = TiliaFile(**data)

    def get_file_path(self):
        return self.file.file_path

    def ask_save_changes_if_modified(self):
        if not self.is_file_modified(get(Get.APP_STATE)):
            return True, False

        return get(Get.FROM_USER_SHOULD_SAVE_CHANGES)
