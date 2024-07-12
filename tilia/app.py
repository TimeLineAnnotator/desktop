from __future__ import annotations
import itertools
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import tilia.errors
import tilia.constants
import tilia.dirs
from tilia.file.tilia_file import TiliaFile
from tilia.media.loader import MediaLoader
from tilia.utils import get_tilia_class_string
from tilia.requests import get, post, serve, listen, Get, Post
from tilia.timelines.collection.collection import Timelines
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.undo_manager import PauseUndoManager

if TYPE_CHECKING:
    from tilia.media.player import Player
    from tilia.file.file_manager import FileManager
    from tilia.clipboard import Clipboard
    from tilia.undo_manager import UndoManager

logger = logging.getLogger(__name__)


class App:
    def __init__(
        self,
        file_manager: FileManager,
        clipboard: Clipboard,
        undo_manager: UndoManager,
    ):
        self._id_counter = itertools.count()
        self.player: Player | None = None
        self.file_manager = file_manager
        self.clipboard = clipboard
        self.undo_manager = undo_manager
        self.duration = 0.0
        self._setup_timelines()
        self._setup_requests()

    def __str__(self):
        return get_tilia_class_string(self)

    def _setup_requests(self):
        LISTENS = {
            (Post.APP_CLEAR, self.on_clear),
            (Post.APP_CLOSE, self.on_close),
            (Post.APP_FILE_LOAD, self.on_file_load),
            (Post.APP_MEDIA_LOAD, self.load_media),
            (Post.APP_STATE_RESTORE, self.on_restore_state),
            (Post.APP_SETUP_FILE, self.setup_file),
            (Post.APP_RECORD_STATE, self.on_record_state),
            (Post.PLAYER_AVAILABLE, self.on_player_available),
            (Post.PLAYER_DURATION_AVAILABLE, self.on_player_duration_available),
            # Listening on tilia.dirs would need to be top-level.
            # That sounds like a bad idea, so we're listening here.
            (Post.AUTOSAVES_FOLDER_OPEN, tilia.dirs.open_autosaves_dir),
        }

        SERVES = {
            (Get.ID, self.get_id),
            (Get.APP_STATE, self.get_app_state),
            (Get.MEDIA_DURATION, lambda: self.duration),
        }

        for post, callback in LISTENS:
            listen(self, post, callback)

        for request, callback in SERVES:
            serve(self, request, callback)

    def _setup_timelines(self):
        self.timelines = Timelines(self)

    def on_player_available(self, player: Player):
        self.player = player

    def on_player_duration_available(self, duration: float):
        self.duration = duration
        post(Post.FILE_MEDIA_DURATION_CHANGED, duration)

    def on_close(self) -> None:
        success, confirm_save = self.file_manager.ask_save_changes_if_modified()
        if not success:
            return
        if confirm_save:
            if not self.file_manager.on_save_request():
                return

        post(Post.UI_EXIT, 0)

    def load_media(self, path: str) -> None:
        if not path:
            self.player.unload_media()
            return

        player = MediaLoader(self.player).load(path)
        if player:
            self.player = player
            post(Post.APP_RECORD_STATE, "media load")

    def on_restore_state(self, state: dict) -> None:
        logging.disable(logging.CRITICAL)
        with PauseUndoManager():
            self.timelines.restore_state(state["timelines"])
            self.file_manager.set_media_metadata(state["media_metadata"])
            self.restore_player_state(state["media_path"])
        logging.disable(logging.NOTSET)

    def on_record_state(self, action, no_repeat=False, repeat_identifier=""):
        self.undo_manager.record(
            self.get_app_state(),
            action,
            no_repeat=no_repeat,
            repeat_identifier=repeat_identifier,
        )

    def get_id(self) -> int:
        """
        Returns an id unique to the current file.
        """
        return next(self._id_counter)

    def set_media_duration(self, duration):
        post(Post.FILE_MEDIA_DURATION_CHANGED, duration)
        self.duration = duration

    @staticmethod
    def _check_if_media_exists(path: str) -> bool:
        return re.match(tilia.constants.YOUTUBE_URL_REGEX, path) or Path(path).exists()

    def _setup_file_media(self, path: str, duration: float | None):
        if duration:
            self.set_media_duration(duration)

        if not self._check_if_media_exists(path):
            tilia.errors.display(tilia.errors.MEDIA_NOT_FOUND, path)
            post(Post.PLAYER_URL_CHANGED, "")
            return

        self.load_media(path)

    def on_file_load(self, file: TiliaFile) -> None:
        media_path = file.media_path
        media_duration = file.media_metadata.get("media length", None)

        if file.media_path or media_duration:
            self._setup_file_media(media_path, media_duration)

        self.timelines.deserialize_timelines(file.timelines)
        self.setup_file()

    def on_clear(self) -> None:
        self.timelines.clear()
        self.file_manager.new()
        if self.player:
            self.player.clear()
        self.undo_manager.clear()
        post(Post.REQUEST_CLEAR_UI)

    def reset_undo_manager(self):
        self.undo_manager.clear()
        self.undo_manager.record(self.get_app_state(), "file start")

    def restore_player_state(self, media_path: str) -> None:
        if self.player.media_path == media_path:
            return

        self.load_media(media_path)

    def get_timelines_state(self):
        return self.timelines.serialize_timelines()

    def get_app_state(self) -> dict:
        logging.disable(logging.CRITICAL)
        params = {
            "media_metadata": dict(self.file_manager.file.media_metadata),
            "timelines": self.get_timelines_state(),
            "media_path": get(Get.MEDIA_PATH),
            "file_path": self.file_manager.get_file_path(),
            "version": tilia.constants.VERSION,
            "app_name": tilia.constants.APP_NAME,
        }
        logging.disable(logging.NOTSET)
        return params

    def setup_file(self):
        # creates a slider timeline if none was loaded
        if not get(Get.TIMELINE_COLLECTION).has_timeline_of_kind(
            TimelineKind.SLIDER_TIMELINE
        ):
            self.timelines.create_timeline(TimelineKind.SLIDER_TIMELINE)
            self.file_manager.set_timelines(self.get_timelines_state())

        self.reset_undo_manager()
