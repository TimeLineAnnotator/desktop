from __future__ import annotations

import functools
import json
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import tilia.constants
import tilia.dirs
import tilia.errors
from tilia.exceptions import NoReplyToRequest
from tilia.file import tla_bridge
from tilia.file.file_manager import read_file
from tilia.media.loader import load_media
from tilia.requests import Get, Post, get, listen, long_operation, post, serve
from tilia.settings import settings
from tilia.timelines.collection.collection import Timelines
from tilia.timelines.slider.timeline import SliderTimeline
from tilia.ui import commands
from tilia.ui.format import format_media_time
from tilia.ui.strings import SCALE_TIMELINE_PROMPT
from tilia.undo_manager import PauseUndoManager
from tilia.utils import get_tilia_class_string
from tilia_core import tla

if TYPE_CHECKING:
    from tilia.clipboard import Clipboard
    from tilia.file.file_manager import FileManager
    from tilia.file.open_document import OpenDocument
    from tilia.media.player import Player
    from tilia.undo_manager import UndoManager


class App:
    def __init__(
        self,
        file_manager: FileManager,
        clipboard: Clipboard,
        undo_manager: UndoManager,
        player: Player,
    ):
        self.player: Player | None = None
        self.file_manager = file_manager
        self.clipboard = clipboard
        self.undo_manager = undo_manager
        self.player = player
        self.duration = 0.0
        self.should_scale_timelines = "prompt"
        self._setup_timelines()
        self.file_manager.file.timelines_hash = self.get_timelines_state()[1]
        self._setup_requests()
        self._setup_commands()
        # The file open, or being opened: a PDF timeline's relative path is the
        # file's.
        self.cur_file_path: Path | None = None

    def __str__(self):
        return get_tilia_class_string(self)

    def _setup_requests(self):
        LISTENS = {
            (Post.APP_CLEAR, self.on_clear),
            (Post.APP_MEDIA_LOAD, self.load_media),
            (Post.APP_STATE_RESTORE, self.on_restore_state),
            (Post.APP_STATE_RECOVER, self.recover_to_state),
            (Post.APP_SETUP_FILE, self.setup_file),
            (Post.APP_STATE_RECORD, self.on_record_state),
            (Post.PLAYER_DURATION_AVAILABLE, self.set_file_media_duration),
        }

        SERVES = {
            (Get.ID, self.get_id),
            (Get.APP_STATE, self.get_app_state),
            (Get.MEDIA_DURATION, lambda: self.duration),
            (Get.VERIFIED_PATH, self._verify_path_exists),
            (Get.IS_FILE_MODIFIED, self.is_file_modified),
        }

        for post_, callback in LISTENS:
            listen(self, post_, callback)

        for request, callback in SERVES:
            serve(self, request, callback)

    def _setup_timelines(self):
        self.timelines = Timelines(self)

    def _setup_commands(self):
        commands.register("file.open", self.on_open, text="&Open...", shortcut="Ctrl+O")
        commands.register(
            "tilia.close",
            self.on_close,
            text="Close TiLiA",
        )
        commands.register(
            "edit.undo", self.undo_manager.undo, text="&Undo", shortcut="Ctrl+Z"
        )
        commands.register(
            "edit.redo", self.undo_manager.redo, text="&Redo", shortcut="Ctrl+Shift+Z"
        )

        (
            commands.register(
                "folder.open.autosaves",
                tilia.dirs.open_autosaves_dir,
                "Open autosa&ves folder...",
            ),
        )

        commands.register(
            "file.export.img",
            functools.partial(self.on_export, export_type="img"),
            text="&Image",
        )

        commands.register(
            "file.export.json",
            functools.partial(self.on_export, export_type="json"),
            text="&JSON",
            shortcut="Ctrl+J",
        )

    def set_file_media_duration(
        self,
        duration: float,
        scale_timelines: Literal["yes", "no", "prompt", "keep"] | None = None,
    ) -> None:
        if scale_timelines:
            self.should_scale_timelines = scale_timelines
        # Post the new duration first so time_x_converter (and other
        # coordinate listeners) update before on_media_duration_changed
        # crops or scales components — otherwise the UI re-positions
        # cropped elements against the OLD media_duration and the
        # timeline appears to stop at the old end-time (#496).
        # is_confirmation tells file_manager this duration belongs to
        # media we already associated with the current file (#453's
        # "keep" mode, within normal jitter), not a user-driven change,
        # so it shouldn't be treated as an unsaved edit.
        post(
            Post.FILE_MEDIA_DURATION_CHANGED,
            duration,
            is_confirmation=self._is_duration_confirmation(duration),
        )
        self.on_media_duration_changed(duration)

    def _is_duration_confirmation(self, duration: float) -> bool:
        return (
            self.should_scale_timelines == "keep"
            and abs(duration - self.duration)
            < tilia.constants.DURATION_JITTER_TOLERANCE
        )

    def is_file_modified(self) -> bool:
        return self.file_manager.is_file_modified(self.get_app_state())

    def on_open(self, path: Path | str | None = None) -> bool:
        if isinstance(path, str):
            path = Path(path)

        if self.is_file_modified():
            success, should_save = get(Get.FROM_USER_SHOULD_SAVE_CHANGES)
            if not success:
                return False

            if should_save:
                commands.execute("file.save")

        if not path:
            success, path = get(Get.FROM_USER_TILIA_FILE_PATH)
            if not success:
                return False
        return self._do_open(Path(path))

    @long_operation("Loading file...")
    def _do_open(self, path: Path) -> bool:
        # Read first, then clear, so that a file that isn't opened leaves the one
        # open as it was.
        file = read_file(path)
        if file is None:
            return False

        open_before = _OpenBefore(self)
        self.cur_file_path = Path(file.file_path)
        self.on_clear()

        success = self.on_file_load(file)
        if not success:
            open_before.give_back()
            return False

        file.timelines, file.timelines_hash = self.get_timelines_state()
        # Where the media was found: the file keeps the path it stores.
        file.media_path = get(Get.MEDIA_PATH)
        self.file_manager.file = file
        # The undo baseline must be recorded only now: until the line above,
        # file_manager holds the blank file from on_clear(), and undoing back
        # to a baseline taken from it would wipe the loaded metadata (#666).
        self.reset_undo_manager()
        post(Post.APP_FILE_LOADED, file)
        self.update_recent_files()

        return True

    def update_recent_files(self):
        try:
            geometry, window_state = get(Get.WINDOW_GEOMETRY), get(Get.WINDOW_STATE)
        except NoReplyToRequest:
            geometry, window_state = None, None

        settings.update_recent_files(
            self.file_manager.get_file_path(), geometry, window_state
        )

    def on_export(
        self,
        path: Path | str | None = None,
        export_type: Literal["json", "img"] = "json",
    ) -> None:
        if isinstance(path, str):
            path = Path(path)

        if not path:
            success, path = get(
                Get.FROM_USER_EXPORT_PATH, get(Get.MEDIA_TITLE), export_type
            )
            if not success:
                return

        match export_type:
            case "json":
                with open(path.__str__(), "w") as f:
                    json.dump(self.get_export_data(), f, indent=2)
            case "img":
                try:
                    get(Get.MAIN_WINDOW).on_export(path.__str__())
                except NoReplyToRequest:
                    return

    def on_close(self) -> None:
        success, confirm_save = self.file_manager.ask_save_changes_if_modified()
        if not success:
            return
        if confirm_save:
            if not self.file_manager.on_save_request():
                return

        post(Post.UI_EXIT, 0)

    def load_media(
        self,
        path: str,
        record: bool = True,
        scale_timelines: Literal["yes", "no", "prompt", "keep"] = "prompt",
        initial_duration: float | None = None,
    ) -> bool:
        """
        Returns True if the media was loaded successfully, False otherwise.
        """
        self.should_scale_timelines = scale_timelines
        if not path:
            self.player.unload_media()
            self.set_file_media_duration(0.0)
            return True

        return self._do_load_media(path, record, initial_duration)

    @long_operation("Loading media...")
    def _do_load_media(
        self,
        path: str,
        record: bool,
        initial_duration: float | None,
    ) -> bool:
        success, player = load_media(
            self.player, path, initial_duration=initial_duration
        )
        self.player = player

        if success and record:
            post(Post.PLAYER_CANCEL_LOOP)
            post(Post.APP_STATE_RECORD, "media load")

        return success

    def _restore_app_state(self, state: dict) -> None:
        with PauseUndoManager():
            self.restore_player_state(
                state["media_path"], state["media_metadata"].get("media length", 0)
            )
            self.file_manager.set_media_metadata(state["media_metadata"])
            self.timelines.restore_state(state["timelines"])

    def on_restore_state(self, state: dict) -> None:
        backup = self.get_app_state()
        try:
            self._restore_app_state(state)
        except Exception:
            self.recover_to_state(backup)
            tilia.errors.display(tilia.errors.UNDO_FAILED, traceback.format_exc())

    def recover_to_state(self, state: dict) -> None:
        """
        Clears the app and attempts to restore the given state.
        Unlike `on_restore_state` this will crash if an error occurs during
        the restoration.
        This is meant to be used after an exception occurred, so if the
        restoration fails, we are likely in an invalid state and
        therefore crashing is the best option.
        """
        self.on_clear()
        self._restore_app_state(state)

    def on_record_state(self, action, no_repeat=False, repeat_identifier=""):
        self.undo_manager.record(
            self.get_app_state(),
            action,
            no_repeat=no_repeat,
            repeat_identifier=repeat_identifier,
        )

    def get_id(self, id: str | None = None) -> str:
        """
        Returns an ID string: `id` as text if it is free, a new one otherwise.
        IDs are unique across timeline component and timelines.
        Other IDs might contain duplicates.
        """
        if id is None:
            return tla.new_id()

        id = str(id)

        timeline_ids = {c.id for c in self.timelines}
        component_lists = [
            tl.components for tl in self.timelines if tl.components is not None
        ]
        component_ids = {
            c.id for component_list in component_lists for c in component_list
        }

        if id in timeline_ids | component_ids:
            return tla.new_id()

        return id

    def on_media_duration_changed(self, duration: float):
        # "keep" leaves the timelines untouched: they already match this
        # media (e.g. we just opened a file), so a duration report that
        # differs only by jitter — YouTube returns it asynchronously, see
        # tilia.constants.DURATION_JITTER_TOLERANCE — must neither prompt to scale
        # nor crop end components (#453). Only the duration itself is
        # updated, below. A difference at or above the tolerance is treated
        # as a genuine media change instead, falling back to "prompt" for
        # this report only -- should_scale_timelines itself is untouched,
        # so a later, smaller jitter report is still handled as "keep".
        effective_mode = self.should_scale_timelines
        if effective_mode == "keep" and not self._is_duration_confirmation(duration):
            effective_mode = "prompt"

        if (
            not self.timelines.is_blank
            and duration != self.duration
            and effective_mode != "keep"
        ):
            crop_or_scale = ""
            if effective_mode == "prompt":
                if self.prompt_scale_timelines(self.duration, duration):
                    crop_or_scale = "scale"
                else:
                    if duration < self.duration:
                        if self.prompt_crop_timelines():
                            crop_or_scale = "crop"
                        else:
                            crop_or_scale = "scale"
            elif effective_mode == "yes":
                crop_or_scale = "scale"
            elif duration < self.duration:  # effective_mode == 'no'
                crop_or_scale = "crop"

            if crop_or_scale == "scale":
                self.timelines.scale_timeline_components(duration / self.duration)
            elif crop_or_scale == "crop":
                self.timelines.crop_timeline_components(duration)

        self.duration = duration

    @staticmethod
    def prompt_scale_timelines(prev_duration: float, new_duration: float) -> bool:
        return get(
            Get.FROM_USER_YES_OR_NO,
            "Scale timelines",
            SCALE_TIMELINE_PROMPT.format(
                format_media_time(prev_duration), format_media_time(new_duration)
            ),
        )

    @staticmethod
    def prompt_crop_timelines() -> bool:
        crop_prompt = (
            "New media is smaller, "
            "so components may get deleted or cropped. "
            "Are you sure you don't want to scale existing timelines?"
        )
        return get(Get.FROM_USER_YES_OR_NO, "Crop timelines", crop_prompt)

    @staticmethod
    def _found_media(media: tla.Media) -> str:
        """Where the core found the media: a YouTube link as the file stores it, or
        a local file's path. "" when it found none."""
        if media.kind == "youtube":
            return media.stored
        if media.path is not None:
            return media.path.as_posix()
        return ""

    def _setup_file_media(self, media: tla.Media, duration: float | None):
        if duration:
            self.set_file_media_duration(duration)

        if media.kind == "none":
            # if no path is provided, we don't want to display an error
            # as user has set the duration manually
            return

        new_path = self._found_media(media)
        if not new_path:
            tilia.errors.display(tilia.errors.MEDIA_NOT_FOUND, media.stored)
            confirm = get(Get.FROM_USER_RETRY_MEDIA_PATH)
            if confirm:
                success, new_path = get(Get.FROM_USER_MEDIA_PATH)
                if success:
                    self.load_media(new_path, initial_duration=duration)
                    return

            post(Post.PLAYER_URL_CHANGED, "")
            return

        # Media that belongs to a file we just opened: the timelines were
        # saved to match it, so neither prompt to rescale nor crop when the
        # player reports its duration. "no" is not enough here — it still
        # crops when the reported duration comes back shorter, and YouTube
        # returns that duration asynchronously, often off by a few ms from
        # the stored value, which would silently delete end components (#453).
        self.load_media(new_path, initial_duration=duration, scale_timelines="keep")

    def on_file_load(self, file: OpenDocument) -> bool:
        document = file.document
        try:
            if document.media_path or document.media_length:
                self._setup_file_media(
                    tla.media(file.file_path, document), document.media_length
                )

            # As the reader keeps them: none is checked (FR-060).
            self.timelines.deserialize_timelines(tla_bridge.state_of(document))
            self._ensure_slider_timeline()
        except Exception:
            tilia.errors.display(
                tilia.errors.LOAD_FILE_ERROR, file.file_path, traceback.format_exc()
            )
            return False

        return True

    def _verify_path_exists(self, path: str) -> str:
        """The file a PDF timeline's path names, as the core finds it: a relative
        path from the folder of the file open. "" when it names none."""
        if not path:
            return path
        if self.cur_file_path is None:
            return path if Path(path).is_absolute() and Path(path).exists() else ""
        found = tla.stored_file(self.cur_file_path, path)
        return found.as_posix() if found is not None else ""

    def on_clear(self) -> None:
        self.timelines.clear()
        self.file_manager.new()
        self.file_manager.file.timelines_hash = self.get_timelines_state()[1]
        if self.player:
            self.player.clear()
            self.set_file_media_duration(0.0)
        self.undo_manager.clear()
        post(Post.REQUEST_CLEAR_UI)

    def reset_undo_manager(self):
        self.undo_manager.clear()
        self.undo_manager.record(self.get_app_state(), "file start")

    def restore_player_state(self, media_path: str, duration: float) -> None:
        if self.player.media_path == media_path:
            # Media has not changed. We need to restore
            # the duration as it was set to 0 while
            # clearing the app
            if duration:
                self.set_file_media_duration(duration)
            return

        self.load_media(media_path, record=False, initial_duration=duration)

    def get_timelines_state(self):
        return self.timelines.serialize_timelines()

    def get_app_state(self) -> dict:
        timelines_state, timelines_hash = self.timelines.serialize_timelines()
        params = {
            "media_metadata": dict(self.file_manager.file.media_metadata),
            "timelines": timelines_state,
            "timelines_hash": timelines_hash,
            "media_path": get(Get.MEDIA_PATH),
            "file_path": self.file_manager.get_file_path(),
            "version": tilia.constants.VERSION,
            "app_name": tilia.constants.APP_NAME,
        }
        return params

    def get_export_data(self):
        return {
            "timelines": self.timelines.get_export_data(),
            "media_metadata": dict(self.file_manager.file.media_metadata),
            "media_path": get(Get.MEDIA_PATH),
        }

    def _ensure_slider_timeline(self) -> None:
        # creates a slider timeline if none was loaded
        if not get(Get.TIMELINE_COLLECTION).has_timeline_of_type(SliderTimeline):
            self.timelines.create_timeline(SliderTimeline)
            self.file_manager.set_timelines(*self.get_timelines_state())

    def setup_file(self) -> None:
        self._ensure_slider_timeline()
        self.reset_undo_manager()


class _OpenBefore:
    """The file open before another is opened, to give back if the other fails to
    load part-way, once the app has been cleared: its state, its file with what
    tells whether it is modified, and its undo history."""

    def __init__(self, app: App):
        self.app = app
        self.state = app.get_app_state()
        self.file = app.file_manager.keep_file()
        self.file_path = app.cur_file_path
        undo = app.undo_manager
        self.undo = undo.stack, undo.current_state_index, undo.last_repeat_id

    def give_back(self) -> None:
        app = self.app
        # What the other file left half loaded goes first, so that restoring this
        # one finds no timelines: it then asks nothing about scaling them.
        app.on_clear()
        app._restore_app_state(self.state)
        app.file_manager.give_back_file(self.file)
        app.cur_file_path = self.file_path
        undo = app.undo_manager
        undo.stack, undo.current_state_index, undo.last_repeat_id = self.undo
