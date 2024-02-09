from __future__ import annotations
import itertools
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import tilia.errors
import tilia.constants
from tilia import settings
from tilia.file.tilia_file import TiliaFile
from tilia.media.loader import MediaLoader
from tilia.ui import actions
from tilia.ui.actions import TiliaAction
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
        self.player = None
        self.file_manager = file_manager
        self.clipboard = clipboard
        self.undo_manager = undo_manager
        self._setup_timelines()
        self._setup_requests()

    def __str__(self):
        return get_tilia_class_string(self)

    def _setup_requests(self):
        self.SUBSCRIPTIONS = [
            (Post.APP_CLEAR, self.on_clear),
            (Post.UI_CLOSE, self.on_close),
            (Post.APP_FILE_LOAD, self.on_file_load),
            (Post.APP_MEDIA_LOAD, self.load_media),
            (Post.APP_STATE_RESTORE, self.on_restore_state),
            (Post.APP_SETUP_BLANK_FILE, self.setup_blank_file),
            (Post.APP_RECORD_STATE, self.on_record_state),
            (Post.PLAYER_AVAILABLE, self.on_player_available),
            # listening on tilia.settings would cause circular import
            (Post.WINDOW_SETTINGS_OPEN, settings.open_settings_on_os),
        ]

        for event, callback in self.SUBSCRIPTIONS:
            listen(self, event, callback)

        serve(self, Get.FILE_SAVE_PARAMETERS, self.get_app_state)
        serve(self, Get.ID, self.get_id)
        serve(self, Get.APP_STATE, self.get_app_state)

    def _setup_timelines(self):
        self.timelines = Timelines(self)

    def on_player_available(self, player: Player):
        self.player = player

    def on_close(self) -> None:
        success, confirm_save = self.file_manager.ask_save_changes_if_modified()
        if not success:
            return
        if confirm_save:
            actions.trigger(TiliaAction.FILE_SAVE)

        sys.exit()

    def load_media(self, path: str) -> None:
        self.player = MediaLoader(self.player).load(path)

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

    def _setup_file_media(self, path: str, duration: float | None):
        if not Path(path).exists():
            tilia.errors.display(tilia.errors.MEDIA_NOT_FOUND, path)
            post(Post.PLAYER_URL_CHANGED, "")
            if duration:
                post(Post.PLAYER_DURATION_CHANGED, duration)
                self.player.duration = duration
            return

        self.load_media(path)

    def on_file_load(self, file: TiliaFile) -> None:
        if file.media_path:
            self._setup_file_media(
                file.media_path, file.media_metadata.get("media length", None)
            )

        self.timelines.deserialize_timelines(file.timelines)
        self.setup_blank_file()

        # reset undo manager
        self.reset_undo_manager()

    def on_clear(self) -> None:
        self.timelines.clear()
        self.file_manager.new()
        self.player.clear()
        self.undo_manager.clear()
        post(Post.REQUEST_CLEAR_UI)

    def reset_undo_manager(self):
        self.undo_manager.clear()
        self.undo_manager.record(self.get_app_state(), "load file")

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

    def setup_blank_file(self):
        # creates a slider timeline if none was loaded
        if get(Get.TIMELINE_COLLECTION).is_empty:
            self.timelines.create_timeline(TimelineKind.SLIDER_TIMELINE)
            self.file_manager.set_timelines(self.get_timelines_state())
