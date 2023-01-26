from __future__ import annotations

import dataclasses
import itertools
import logging
import os
import sys
from collections import OrderedDict
from enum import Enum
from pathlib import Path

from tilia import settings, local_dev_code, events, media_exporter, globals_
from tilia.clipboard import Clipboard
from tilia.events import subscribe
from tilia.events import Event as Evt
from tilia.exceptions import UserCancelledSaveError
from tilia.file_manager import FileManager
from tilia.files import create_new_media_metadata, TiliaFile
from tilia.player import player
from tilia.repr import default_str
from tilia.timelines.collection import TimelineCollection
from tilia.timelines.create import create_timeline
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind, IMPLEMENTED_TIMELINE_KINDS
from tilia.ui.timelines.collection import TimelineUICollection
from tilia.undo_manager import UndoManager

logger = logging.getLogger(__name__)


class MediaType(Enum):
    AUDIO = "audio"
    VIDEO = "video"


class TiLiA:
    def __init__(self, ui):
        logger.info("TiLia starting...")

        self.SUBSCRIPTIONS = [
            (Evt.REQUEST_LOAD_MEDIA, self.on_request_to_load_media),
            (Evt.REQUEST_ADD_TIMELINE, self.on_add_timeline),
            (Evt.REQUEST_NEW_FILE, self.on_request_new_file),
            (Evt.REQUEST_CLOSE_APP, self.on_request_to_close),
            (Evt.REQUEST_RECORD_STATE, self.on_request_to_record_state),
            (Evt.REQUEST_RESTORE_APP_STATE, self.on_request_to_restore_state),
            (Evt.METADATA_FIELD_EDITED, self.on_metadata_field_edited),
            (Evt.METADATA_NEW_FIELDS, self.on_metadata_new_fields),
            (Evt.REQUEST_EXPORT_AUDIO_SEGMENT, self.on_request_to_export_audio_segment),
        ]

        self._id_counter = itertools.count()

        self._setup_ui(ui)
        self._setup_collections()
        self._setup_components()
        self._setup_subscriptions()
        self.media_type = None
        self._setup_file()

        logger.info("TiLiA started.")

        if settings.get("dev", "dev_mode"):
            local_dev_code.func(self)

    def __str__(self):
        return default_str(self)

    def _setup_ui(self, ui):
        self.ui = ui
        self.ui.app = self

    def _setup_collections(self):
        self._timeline_collection = TimelineCollection(self)
        self._timeline_ui_collection = self.ui.get_timeline_ui_collection()

        _associate_timeline_and_timeline_ui_collections(
            self._timeline_collection, self._timeline_ui_collection
        )

    def _setup_components(self):
        self._file_manager = FileManager(self)
        self._player = player.PygamePlayer()
        self._clipboard = Clipboard()
        self._undo_manager = UndoManager()
        self._media_metadata = create_new_media_metadata()

    def _setup_subscriptions(self):
        for event, callback in self.SUBSCRIPTIONS:
            subscribe(self, event, callback)

    def _setup_file(self):
        """
        Checks if a file path was passed as an argument to process.
        If it was, the file is opened. Else, calls setup for newly created files.
        """
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            logger.info(f"Opening file provided at startup: {sys.argv[1]}")
            self._file_manager.open_file_by_path(sys.argv[1])
        else:
            self._blank_file_setup()

    def _blank_file_setup(self):
        """
        Creates a slider timeline. To be used on newly created timelines.
        """
        create_timeline(
            TimelineKind.SLIDER_TIMELINE,
            self._timeline_collection,
            self._timeline_ui_collection,
            "",
        )

    @property
    def media_length(self):
        return self._player.media_length

    @property
    def media_metadata(self):
        return self._media_metadata

    @property
    def current_playback_time(self):
        return self._player.current_time

    @property
    def media_path(self) -> str:
        return self._player.media_path

    @property
    def media_title(self) -> str:
        return self._media_metadata["title"]

    def get_id(self) -> str:
        """
        Returns an unique id (with regards to the file).
        """
        return str(next(self._id_counter))

    def on_request_to_load_media(self, media_path: str) -> None:

        extension = os.path.splitext(media_path)[1][1:]

        self._change_player_according_to_extension(extension)

        self._player.load_media(media_path)

        self._media_metadata["media length"] = self.media_length

    def on_request_to_export_audio_segment(
        self, segment_name: str, start_time: float, end_time: float
    ):

        logger.debug(f"User requested audio segment export.")

        if sys.platform != "win32":
            ERROR_MESSAGE = "Exporting audio is currently only available " "on Windows."
            events.post(
                Evt.REQUEST_DISPLAY_ERROR, title="Export audio", message=ERROR_MESSAGE
            )
            return

        export_dir = Path(self.ui.ask_for_directory("Export audio"))

        media_exporter.export_audio_segment(
            audio_path=self._player.media_path,
            dir=export_dir,
            file_title=self.media_metadata["title"],
            start_time=start_time,
            end_time=end_time,
            segment_name=segment_name,
        )

    def on_request_new_file(self) -> None:
        try:
            self._file_manager.new()
        except UserCancelledSaveError:
            return

        self._blank_file_setup()

        self._undo_manager.clear()
        events.post(Evt.TILIA_FILE_LOADED)
        self._undo_manager.record(self.get_state(), Action.FILE_LOAD)

    def on_request_to_close(self) -> None:
        self._file_manager.ask_save_if_necessary()

        sys.exit()

    def _change_player_according_to_extension(self, extension: str) -> None:

        if (
            extension.lower()
            in globals_.SUPPORTED_AUDIO_FORMATS + globals_.CONVERTIBLE_AUDIO_FORMATS
        ):
            self._change_to_audio_player_if_necessary()
            self.media_type = MediaType.AUDIO
        elif extension.lower() in globals_.SUPPORTED_VIDEO_FORMATS:
            self._change_to_video_player_if_necessary()
            self.media_type = MediaType.VIDEO
        else:
            events.post(
                Evt.REQUEST_DISPLAY_ERROR,
                title="Media file not supported",
                message=f"Media file of type '{extension}' not supported."
                f"Try loading a supported file type.",
            )
            raise ValueError(f"Media file extension '{extension}' is not supported.")

    def _change_to_audio_player_if_necessary(self) -> None:
        if isinstance(self._player, player.VlcPlayer):
            self._player.destroy()
            self._player = player.PygamePlayer(
                previous_media_length=self._player.previous_media_length
            )
            logger.debug(f"Changed to audio player.")

    def _change_to_video_player_if_necessary(self) -> None:
        if isinstance(self._player, player.PygamePlayer):
            try:
                new_player = player.VlcPlayer(
                    previous_media_length=self._player.previous_media_length
                )
                logger.debug(f"Changed to video player.")
            except player.VLCNotInstalledError:
                events.post(
                    Evt.REQUEST_DISPLAY_ERROR,
                    title="VLC not installed",
                    message="To load a video file, VLC player must be installed.\n"
                    "Download and install VLC from https://www.videolan.org, restart TiLiA and"
                    " reload the file.",
                )
                return

            self._player.destroy()
            self._player = new_player

    def get_timelines_as_dict(self) -> dict:
        return self._timeline_collection.serialize_timelines()

    def get_elements_for_pasting(self) -> dict[str : dict | TimelineKind]:
        logger.debug(f"Getting clipboard contents for pasting...")
        elements = self._clipboard.get_contents_for_pasting()
        logger.debug(f"Got '{elements}'")
        return elements

    def clear_app(self) -> None:
        logger.info(f"Clearing app..")
        self._timeline_collection.clear()
        self._file_manager.clear()
        self._player.clear()
        self._undo_manager.clear()
        self._media_metadata = create_new_media_metadata()
        logger.info(f"App cleared.")

    def load_file(self, file: TiliaFile) -> None:
        logger.info(f"Loading file '{file}'...")

        if file.media_path:
            self.on_request_to_load_media(file.media_path)

        file_copy = dataclasses.asdict(
            file
        )  # must copy so keys don't get popped in passed _file

        for _, tl_data in file_copy["timelines"].items():
            kind_str = tl_data.pop("kind")
            if kind_str not in [kind.value for kind in IMPLEMENTED_TIMELINE_KINDS]:
                logger.debug(f"Timeline kind '{kind_str} is not implemented.")
                continue
            kind = TimelineKind[kind_str]

            create_timeline(
                kind, self._timeline_collection, self._timeline_ui_collection, **tl_data
            )

        self._undo_manager.clear()
        self._undo_manager.record(self.get_state(), Action.FILE_LOAD)
        events.post(Evt.TILIA_FILE_LOADED)
        logger.info(f"Loaded file.")

    def on_add_timeline(self, kind: TimelineKind) -> None:
        logger.debug(f"User requested to add timeline...")
        if (
            kind not in IMPLEMENTED_TIMELINE_KINDS
            or kind == TimelineKind.SLIDER_TIMELINE
        ):
            raise NotImplementedError(
                f'Can not create timeline. Invalid timeline kind "{kind}"'
            )

        name = self.ui.ask_string(
            title="Name for new timeline", prompt="Choose name for new timeline"
        )

        create_timeline(
            kind, self._timeline_collection, self._timeline_ui_collection, name
        )

        events.post(Evt.REQUEST_RECORD_STATE, Action.TIMELINE_CREATE)

    def on_metadata_field_edited(self, field_name: str, value: str) -> None:
        self._media_metadata[field_name] = value

    def on_metadata_new_fields(self, field_list: list[str]) -> None:
        """
        Updates self._media_metadata to have attributes in 'field_list'.
        Preserves values in previously existing attributes.
        """
        new_metadata = OrderedDict({key: "" for key in field_list})

        for field in field_list:
            if field in self._media_metadata:
                new_metadata[field] = self._media_metadata[field]

        self._media_metadata = new_metadata

    def get_state(self) -> dict:
        """
        Returns a dictionary with:
        - TimelineCollection state;
        - Player state;
        - MediaMetadata state;
        - file path.
        """
        logging.disable(logging.CRITICAL)
        state = self._file_manager.get_save_parameters()
        logging.disable(logging.NOTSET)
        return state

    def on_request_to_record_state(
        self, action: Action, no_repeat=False, repeat_identifier=""
    ):
        self._undo_manager.record(
            self.get_state(),
            action,
            no_repeat=no_repeat,
            repeat_identifier=repeat_identifier,
        )

    def on_request_to_restore_state(self, state: dict) -> None:
        logging.disable(logging.CRITICAL)
        self._timeline_collection.restore_state(state["timelines"])
        self._file_manager.restore_state(
            media_metadata=state["media_metadata"], media_path=state["media_path"]
        )
        self.restore_player_state(state["media_path"])
        logging.disable(logging.NOTSET)

    def restore_player_state(self, media_path: str) -> None:
        if self._player.media_path == media_path:
            return
        else:
            self.on_request_to_load_media(media_path)


def _associate_timeline_and_timeline_ui_collections(
    timeline_collection: TimelineCollection,
    timeline_ui_collection: TimelineUICollection,
):
    """
    Creates a reference for TimelineUICollection in TimelineCollection and vice-versa
    """
    timeline_ui_collection._timeline_collection = timeline_collection
    timeline_collection._timeline_ui_collection = timeline_ui_collection
