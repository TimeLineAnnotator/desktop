from __future__ import annotations

import functools
import json
import math
import re
import traceback
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import tilia.constants
import tilia.dirs
import tilia.errors
from tilia.exceptions import NoReplyToRequest
from tilia.file import autosave, tla_bridge
from tilia.file.file_manager import read_file
from tilia.log import logger
from tilia.media.loader import load_media
from tilia.requests import Get, Post, get, listen, long_operation, post, serve
from tilia.settings import settings
from tilia.timelines.collection.collection import Timelines
from tilia.timelines.edit_gate import EditGate, changed_components
from tilia.timelines.pdf.timeline import PdfTimeline
from tilia.timelines.slider.timeline import SliderTimeline
from tilia.ui import commands
from tilia.ui.format import format_media_time
from tilia.ui.strings import SCALE_TIMELINE_PROMPT
from tilia.undo_manager import PauseUndoManager
from tilia.utils import get_tilia_class_string
from tilia_core import rules, tla

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
        # The check at the end of each action (FR-062, FR-070).
        self.edit_gate = EditGate()
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
            (Post.APP_EDIT_DONE, self.on_edit_done),
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
        if not self._do_open(Path(path)):
            return False
        self._show_problems(self.file_manager.file)
        return True

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
            open_before.give_back(path.name)
            return False

        file.timelines, file.timelines_hash = self.get_timelines_state()
        # Where the media was found: the file keeps the path it stores.
        file.media_path = get(Get.MEDIA_PATH)
        self.file_manager.file = file
        # What the document reflects: the state the timelines just built give, with
        # TiLiA's own digests, so that nothing TiLiA filled in reaches the file.
        file.synced = self.get_app_state()
        # The undo baseline must be recorded only now: until the line above,
        # file_manager holds the blank file from on_clear(), and undoing back
        # to a baseline taken from it would wipe the loaded metadata (#666).
        self.reset_undo_manager()
        post(Post.APP_FILE_LOADED, file)
        self.update_recent_files()

        return True

    @staticmethod
    def _show_problems(file: OpenDocument) -> None:
        """The warnings the file opened with, one line each, once it is open
        (FR-061). Nothing for a file with none.

        A warning about a timeline no longer in the document, which the person chose
        to discard, isn't listed: it won't be saved
        (TimeLineAnnotator/project-management#597, point 8)."""
        document = file.document
        warnings = [
            warning
            for warning in document.warnings
            if warning.timeline_id is None or warning.timeline_id in document.timelines
        ]
        if not warnings:
            return
        # The state the timelines just built give: what TiLiA shows.
        timelines = file.synced["timelines"]
        lines = [problem_line(warning, timelines) for warning in warnings]
        name = Path(file.file_path).name
        try:
            get(Get.FROM_USER_SHOW_PROBLEMS, name, lines)
        except NoReplyToRequest:
            # No interface shows them: the file is open all the same.
            logger.warning("'%s' has problems:\n%s", name, "\n".join(lines))

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
            return
        # Once for each undo or redo step: a single sync over several isn't always
        # exact. The document gets back what it held in `state`, which undo
        # recorded and the state alone can't tell.
        self.sync_document(by_person=False, back_to=state)
        # Undo and redo aren't checked: they go back to states accepted.
        self.edit_gate.accepted = state

    def recover_to_state(self, state: dict) -> None:
        """
        Clears the app and attempts to restore the given state.
        Unlike `on_restore_state` this will crash if an error occurs during
        the restoration.
        This is meant to be used after an exception occurred, so if the
        restoration fails, we are likely in an invalid state and
        therefore crashing is the best option.
        The file open stays the one it was, with its document: clearing alone
        would start a new one.
        """
        kept = self.file_manager.keep_file()
        self.on_clear()
        self.file_manager.give_back_file(kept)
        self._restore_app_state(state)
        self.sync_document(by_person=False)
        self.edit_gate.accepted = state

    def on_record_state(self, action, no_repeat=False, repeat_identifier=""):
        if not self.undo_manager.is_recording:
            # An undo or a redo restoring a state, which syncs once it has, or a part
            # of an action that pauses undo: the action is checked when it ends.
            return
        state = self.get_app_state()
        if not self._end_action(state):
            return
        self.undo_manager.record(
            state,
            action,
            no_repeat=no_repeat,
            repeat_identifier=repeat_identifier,
        )
        self._remember(state)

    def on_edit_done(self) -> None:
        """The end of a command on the command line, which records nothing."""
        self._end_action(self.get_app_state())

    def _end_action(self, state: dict) -> bool:
        """Whether the core's rules accept what a person's action leaves, `state`
        (FR-062, FR-070). Accepted, the document follows it, and keeps the problems
        a component still has that the action fixed in part. Refused, the timelines
        go back to the state last accepted, and the rule's reason is shown."""
        verdict = self.edit_gate.check(
            state,
            media_length=self._media_length_for_rules(state),
            page_counts=self._page_counts(),
            numbered=self._numbered_beats(),
        )
        if verdict.reason is not None:
            self._refuse(verdict.reason)
            return False
        file = self.file_manager.file
        # A person's action, which the document follows at once.
        file.sync(state)
        if verdict.kept:
            file.keep_read_problems(component_id for _, component_id in verdict.kept)
        self.edit_gate.accepted = state
        return True

    def _refuse(self, reason: str) -> None:
        """Takes the timelines back to the state last accepted, as an undo would,
        and says why. Only the timelines: what else the state holds, such as the
        file's fields, the gate doesn't check, and stays as it is."""
        accepted = self.edit_gate.accepted
        try:
            with PauseUndoManager():
                self.timelines.restore_state(accepted["timelines"])
        except Exception:
            logger.exception("Taking the timelines back to the state accepted.")
            self.recover_to_state(accepted)
        tilia.errors.display(tilia.errors.EDIT_REFUSED, reason)
        post(Post.APP_EDIT_REFUSED, reason)

    def _media_length_for_rules(self, state: dict) -> float:
        """The media length the document has once it follows `state`, as a write
        checks times with it: `math.inf` when it is unknown, or isn't one."""
        file = self.file_manager.file
        length = state["media_metadata"].get("media length")
        synced = file.synced
        if synced is not None and length == synced["media_metadata"].get(
            "media length"
        ):
            # Unchanged, or the player's report for the media the file has: the
            # document keeps its own (FR-034).
            length = file.document.media_length
        if not length or not rules.media_length(length):
            return math.inf
        return length

    def _numbered_beats(self) -> dict[str, frozenset[str]]:
        """By a beat timeline's id, the beats whose marks the document stores a
        number on, which the bridge keeps and rewrites (`tla_bridge`'s
        `_set_measure_number`)."""
        return {
            timeline.id: frozenset(
                beat_id
                for beat_id, beat in timeline.components.items()
                if isinstance(beat.attrs.get("measure"), dict)
                and "number" in beat.attrs["measure"]
            )
            for timeline in self.file_manager.file.document.timelines.values()
            if timeline.kind == "beat"
        }

    def _page_counts(self) -> dict[str, float]:
        """Each PDF timeline's page count, by its id: `math.inf` when its PDF wasn't
        found, as the upper bound can't be known then."""
        return {
            timeline.id: timeline.page_total if timeline.is_pdf_valid else math.inf
            for timeline in self.timelines
            if isinstance(timeline, PdfTimeline)
        }

    def sync_document(
        self, *, by_person: bool = True, back_to: dict | None = None
    ) -> None:
        """Makes the document of the file open follow TiLiA's state."""
        self.file_manager.file.sync(
            self.get_app_state(), by_person=by_person, back_to=back_to
        )

    def _remember(self, state: dict) -> None:
        """Keeps, for `state`, which undo has just recorded, what the document holds
        that the state can't tell, for as long as undo keeps the state."""
        file = self.file_manager.file
        file.remember(state)
        file.forget_all_but(entry["state"] for entry in self.undo_manager.stack)

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
            if crop_or_scale:
                self._accept_scale_or_crop()

        self.duration = duration

    def _accept_scale_or_crop(self) -> None:
        """A scale or a crop to the media's new length, as the person answered,
        isn't checked as an edit of the components it moves: TiLiA leaves none past
        the new end (FR-034). The document follows it at once, and the problems those
        components came with stay ones they came with, so that a save doesn't refuse
        them. Undo is left as it was: whether it can go back past the answer is
        TimeLineAnnotator/project-management#642's."""
        if not self.undo_manager.is_recording:
            # An undo restoring a state, which syncs once it has.
            return
        accepted = self.edit_gate.accepted
        state = self.get_app_state()
        file = self.file_manager.file
        file.sync(state)
        if accepted is not None:
            file.keep_read_problems(changed_components(accepted, state))
        self.edit_gate.accepted = state

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
        path from the folder the open file's paths are relative to, kept from its
        read or last save, as its saves and its media take it, so that a Save As
        or a link to the file changed since doesn't move it. That is the folder of
        the document's origin, which a save moves and `cur_file_path`, the file
        opened, doesn't. While a file loads, its document isn't the open one yet,
        and the folder is that of the file just read. "" when it names none."""
        if not path:
            return path
        document = self.file_manager.file.document
        if document is not None and document.origin is not None:
            found = tla.stored_file(document.origin, path, doc=document)
        elif self.cur_file_path is None:
            return path if Path(path).is_absolute() and Path(path).exists() else ""
        else:
            found = tla.stored_file(self.cur_file_path, path, doc=document)
        return found.as_posix() if found is not None else ""

    def on_clear(self) -> None:
        self.timelines.clear()
        self.file_manager.new()
        self.file_manager.file.timelines_hash = self.get_timelines_state()[1]
        if self.player:
            self.player.clear()
            self.set_file_media_duration(0.0)
        self.undo_manager.clear()
        self.edit_gate.accepted = self.get_app_state()
        post(Post.REQUEST_CLEAR_UI)

    def reset_undo_manager(self):
        self.undo_manager.clear()
        state = self.get_app_state()
        self.undo_manager.record(state, "file start")
        self._remember(state)
        # What the file opened with, or a new one, is what the next action is
        # compared with: the problems a file came with aren't the action's.
        self.edit_gate.accepted = state

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
        return {
            "media_metadata": dict(self.file_manager.file.media_metadata),
            "timelines": timelines_state,
            "timelines_hash": timelines_hash,
            "media_path": get(Get.MEDIA_PATH),
        }

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


# What `str.splitlines` breaks a line at.
_LINE_BREAK = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")


def problem_line(
    warning: tla.ReadWarning, timelines: Mapping[str, Mapping[str, Any]]
) -> str:
    """A warning a file opened with, in TiLiA's terms: the name of the timeline it
    concerns and the time of its component, as TiLiA shows them, then the reason
    (FR-061). `timelines` is the state's. The reason alone where TiLiA shows
    neither: a warning without ids, or with ids of nothing TiLiA shows.

    A timeline TiLiA shows without its component, such as a beat without a time,
    gives its name alone, and a timeline without a name gives none
    (TimeLineAnnotator/project-management#597, points 2 and 3).

    One warning, one line: a line break in the timeline's name or in the reason,
    which can quote a value as JSON keeps it, is a space."""
    where: list[str] = []
    timeline = timelines.get(warning.timeline_id) if warning.timeline_id else None
    if timeline is not None:
        if timeline.get("name"):
            where.append(timeline["name"])
        components = timeline.get("components", {})
        component = (
            components.get(warning.component_id) if warning.component_id else None
        )
        if component is not None:
            where.extend(_shown_time(component))
    line = f"{', '.join(where)}: {warning.message}" if where else warning.message
    return _LINE_BREAK.sub(" ", line)


def _shown_time(component: Mapping[str, Any]) -> list[str]:
    """A component's time as TiLiA shows it, a span for a segment; none for a
    component without one, such as a staff."""
    start, end = component.get("start"), component.get("end")
    if start is not None and end is not None:
        return [f"{format_media_time(start)}–{format_media_time(end)}"]
    if component.get("time") is not None:
        return [format_media_time(component["time"])]
    return []


class _OpenBefore:
    """The file open before another is opened, to give back if the other fails to
    load part-way, once the app has been cleared: its state, its file with what
    tells whether it is modified, and its undo history; and, before the clearing, an
    autosave copy of its unsaved changes, if it has any."""

    def __init__(self, app: App):
        self.app = app
        self.state = app.get_app_state()
        self.file = app.file_manager.keep_file()
        self.file_path = app.cur_file_path
        self.duration = app.duration
        self.should_scale_timelines = app.should_scale_timelines
        undo = app.undo_manager
        self.undo = undo.stack, undo.current_state_index, undo.last_repeat_id
        self.accepted = app.edit_gate.accepted
        # Before the clearing: unsaved changes are copied to an autosave, where
        # they are kept if the file can't be given back (FR-012).
        self.autosave_path: Path | None = (
            self._autosave() if app.file_manager.is_file_modified(self.state) else None
        )

    def _autosave(self) -> Path | None:
        """Writes an autosave copy of the file, as the autosaver does, and returns its
        path. None if it can't be written: that is logged, and the other file is
        loaded all the same (TimeLineAnnotator/project-management#603, a)."""
        file = self.app.file_manager.file
        try:
            # What TiLiA shows, as a save writes it: a change nothing recorded, such
            # as a late report of the media's length, isn't in the document yet.
            file.sync(self.state)
            return autosave.autosave(file.copy_for_writing())
        except Exception:
            logger.exception("Autosave of the file open before another failed.")
            return None

    def give_back(self, name: str) -> None:
        """Gives the file back once the file `name` has failed to load part-way."""
        app = self.app
        # What the other file left half loaded goes first, so that restoring this
        # one finds no timelines: it then asks nothing about scaling them.
        try:
            app.on_clear()
        except Exception:
            logger.exception("Clearing what a file that failed to load left.")
        try:
            self._restore()
        except Exception:
            logger.exception("Restoring the file open before, once.")
            try:
                app.on_clear()
                self._restore()
            except Exception:
                # It can't come back. TiLiA keeps the new file the clearing gave,
                # which a save doesn't write over the file open before. The message
                # names the copy that holds its unsaved changes; without one, the
                # command's failure says so.
                app.cur_file_path = None
                if self.autosave_path is None:
                    raise
                logger.exception("Restoring the file open before, again.")
                tilia.errors.display(
                    tilia.errors.OPEN_FILE_NOT_GIVEN_BACK, name, self.autosave_path
                )
                return
        app.file_manager.give_back_file(self.file)
        app.cur_file_path = self.file_path
        undo = app.undo_manager
        undo.stack, undo.current_state_index, undo.last_repeat_id = self.undo
        app.edit_gate.accepted = self.accepted

    def _restore(self) -> None:
        app = self.app
        # Its media's length first, while there are no timelines to scale: a media
        # loaded again reports it only later, and then reports the same.
        app.set_file_media_duration(self.duration)
        app._restore_app_state(self.state)
        app.should_scale_timelines = self.should_scale_timelines
