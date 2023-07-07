from __future__ import annotations
import itertools
import logging
import sys
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from tilia import settings, globals_, dirs
from tilia.exceptions import UserCancel
from tilia.file.tilia_file import TiliaFile
from tilia.media.loader import MediaLoader
from tilia.repr import default_str
from tilia.requests import get, post, serve, listen, Get, Post
from tilia.timelines.collection import Timelines
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.media.player import Player
    from tilia.file.file_manager import FileManager
    from tilia.clipboard import Clipboard
    from tilia.undo_manager import UndoManager

logger = logging.getLogger(__name__)


class MediaType(Enum):
    AUDIO = "audio"
    VIDEO = "video"


class App:
    def __init__(
            self,
            player: Player,
            file_manager: FileManager,
            clipboard: Clipboard,
            undo_manager: UndoManager,
    ):
        logger.info("TiLia starting...")

        self.player = player
        self.file_manager = file_manager
        self.clipboard = clipboard
        self.undo_manager = undo_manager
        self._setup_timeline_collection()

        self.SUBSCRIPTIONS = [
            (Post.REQUEST_CLEAR_APP, self.clear_app),
            (Post.REQUEST_CLOSE_APP, self.on_request_to_close),
            (Post.REQUEST_OPEN_SETTINGS, settings.open_settings_on_os),
            # listening on tilia.settings would cause circular import
            (Post.REQUEST_LOAD_FILE, self.load_file),
            (Post.REQUEST_LOAD_MEDIA, self.on_request_to_load_media),
            (Post.REQUEST_SET_MEDIA_LENGTH, self.on_request_to_set_media_length),
            (Post.REQUEST_RECORD_STATE, self.on_request_to_record_state),
            (Post.REQUEST_RESTORE_APP_STATE, self.on_request_to_restore_state),
            (Post.REQUEST_SETUP_BLANK_FILE, self.setup_blank_file),
        ]

        self._id_counter = itertools.count()

        self._setup_subscriptions()
        self._setup_requests()

        logger.info("App started.")

    def __str__(self):
        return default_str(self)

    def _setup_subscriptions(self):
        for event, callback in self.SUBSCRIPTIONS:
            listen(self, event, callback)

    def _setup_requests(self):
        serve(self, Get.FILE_SAVE_PARAMETERS, self.get_app_state)
        serve(self, Get.ID, self.get_id)
        serve(self, Get.APP_STATE, self.get_app_state)

    def _setup_timeline_collection(self):
        self.timeline_collection = Timelines(self)

    def on_request_to_close(self) -> None:
        try:
            if self.file_manager.ask_save_changes_if_modified():
                self.file_manager.on_save_request()
        except UserCancel:
            return
        try:
            dirs.delete_temp_dir()
        except FileNotFoundError:
            # temp dir already deleted
            pass

        sys.exit()

    def on_request_to_set_media_length(self, length: int) -> None:
        if self.player.media_loaded:
            post(
                Post.REQUEST_DISPLAY_ERROR,
                title="Change media length",
                message="Can't change media length when a media file is loaded.",
            )
            return

        self.set_media_length(length)

    def set_media_length(self, length: int) -> None:
        self.player.media_length = length
        self.file_manager.set_media_duration(length)

    def on_request_to_load_media(self, path: str) -> None:
        self.player = MediaLoader(self.player).load(Path(path))
        self.file_manager.set_media_path(path)

    def on_request_to_restore_state(self, state: dict) -> None:
        logging.disable(logging.CRITICAL)
        self.timeline_collection.restore_state(state["timelines"])
        self.file_manager.set_media_metadata(state["media_metadata"])
        self.file_manager.set_media_path(state["media_path"])
        self.restore_player_state(state["media_path"])
        logging.disable(logging.NOTSET)

    def on_request_to_record_state(
            self, action: Action, no_repeat=False, repeat_identifier=""
    ):
        self.undo_manager.record(
            self.get_app_state(),
            action,
            no_repeat=no_repeat,
            repeat_identifier=repeat_identifier,
        )

    def get_id(self) -> str:
        """
        Returns id that is unique to the current file.
        """
        return str(next(self._id_counter))

    def load_file(self, file: TiliaFile) -> None:
        logger.info("Loading file...")

        # load media
        if file.media_path:
            try:
                self.on_request_to_load_media(file.media_path)
            except FileNotFoundError:
                post(
                    Post.REQUEST_DISPLAY_ERROR,
                    title="Media load error",
                    message=f"{file.media_path} was not found. Load another media via File > Load media...",
                )
                self.file_manager.set_media_path("")
                if media_length := file.media_metadata["media length"]:
                    self.set_media_length(media_length)

        if media_length := file.media_metadata["media length"]:
            self.set_media_length(media_length)

        self.timeline_collection.deserialize_timelines(file.timelines)
        self.setup_blank_file()

        # reset undo manager
        self.reset_undo_manager()

        logger.info("Loaded file.")

    def clear_app(self) -> None:
        logger.info("Clearing app..")
        self.timeline_collection.clear()
        self.file_manager.new()
        self.player.clear()
        self.undo_manager.clear()
        logger.info("App cleared.")
        post(Post.REQUEST_CLEAR_UI)

    def reset_undo_manager(self):
        self.undo_manager.clear()
        self.undo_manager.record(self.get_app_state(), Action.FILE_LOAD)

    def restore_player_state(self, media_path: str) -> None:
        if self.player.media_path == media_path:
            return
        else:
            self.on_request_to_load_media(media_path)

    def get_timelines_state(self):
        return self.timeline_collection.serialize_timelines()

    def get_app_state(self) -> dict:
        logging.disable(logging.CRITICAL)
        params = {
            "media_metadata": dict(self.file_manager.file.media_metadata),
            "timelines": self.get_timelines_state(),
            "media_path": get(Get.MEDIA_PATH),
            "file_path": self.file_manager.get_file_path(),
            "version": globals_.VERSION,
            "app_name": globals_.APP_NAME,
        }
        logging.disable(logging.NOTSET)
        return params

    def setup_blank_file(self):
        # creates a slider timeline if none was loaded
        if not get(Get.TIMELINES):
            self.timeline_collection.create_timeline(TimelineKind.SLIDER_TIMELINE)
            self.file_manager.set_timelines(self.get_timelines_state())
