"""
Entry point for the application.

Defines a TiLiA object which is composed, among other things, of instances of the following classes:
    - FileManager, which handles _file processing (open, save, new, etc...);
    - TimelineWithUIBuilder, which handles request to create timelines and their uis;
    - Player, which handles the playing of;
    - UI (currently a TkinterUI), which handles the GUI as a whole;
    - TimelineColleciton, which handles timeline logic/
    - TimelineUICollection, which handles the user interface for the timelines.

"""

from __future__ import annotations

import dataclasses
import itertools
from collections import OrderedDict
from pathlib import Path

from typing import TYPE_CHECKING

from tilia.clipboard import Clipboard
from tilia.file_manager import FileManager
from tilia.timelines.create import create_timeline
from tilia.timelines.state_actions import StateAction
from tilia.undo_manager import UndoManager

if TYPE_CHECKING:
    from tilia.ui.timelines.common import TimelineUICollection

from unittest.mock import MagicMock

from tilia import globals_, media_exporter
from tilia.exceptions import UserCancelledSaveError
from tilia.globals_ import UserInterfaceKind
from tilia.files import TiliaFile, create_new_media_metadata

import os
import sys
from threading import Thread

from tilia.player import player
from tilia.events import Event, subscribe

from tilia.timelines.timeline_kinds import TimelineKind, IMPLEMENTED_TIMELINE_KINDS
from tilia.timelines.collection import TimelineCollection
from tilia.ui.tkinterui import TkinterUI

import logging

logger = logging.getLogger(__name__)


class TiLiA:
    def __init__(self, ui_kind: UserInterfaceKind):
        logger.info("TiLia starting...")

        subscribe(self, Event.REQUEST_LOAD_MEDIA, self.on_request_to_load_media)
        subscribe(self, Event.APP_ADD_TIMELINE, self.on_add_timeline)
        subscribe(self, Event.REQUEST_NEW_FILE, self.on_request_new_file)
        subscribe(self, Event.REQUEST_CLOSE_APP, self.on_request_to_close)
        subscribe(self, Event.REQUEST_RECORD_STATE, self.on_request_to_record_state)
        subscribe(self, Event.REQUEST_RESTORE_APP_STATE, self.on_request_to_restore_state)
        subscribe(self, Event.METADATA_FIELD_EDITED, self.on_metadata_field_edited)
        subscribe(self, Event.METADATA_NEW_FIELDS, self.on_metadata_new_fields)
        subscribe(self, Event.REQUEST_EXPORT_AUDIO_SEGMENT, self.on_request_to_export_audio_segment)

        self._id_counter = itertools.count()

        self.ui = get_ui(ui_kind, self)

        self._timeline_collection = TimelineCollection(self)
        self._timeline_ui_collection = self.ui.get_timeline_ui_collection()

        _associate_timeline_and_timeline_ui_collections(
            self._timeline_collection, self._timeline_ui_collection
        )

        self._file_manager = FileManager(self)
        self._player = player.PygamePlayer()
        self._clipboard = Clipboard()
        self._undo_manager = UndoManager()
        self._media_metadata = create_new_media_metadata()

        logger.info("TiLiA started.")

        self._initial_file_setup()

        self._code_for_dev()

        self.ui.launch()

    # noinspection PyProtectedMember
    def _code_for_dev(self):
        """Use this to execute code before the ui mainloop runs."""

        self._timeline_collection.delete_timeline(self._timeline_collection._timelines[0])

        self._file_manager._open_file_by_path(
            r"C:\Programação\TiLiA-devresources\audio_2mrk.tla")

    def get_id(self) -> str:
        return str(next(self._id_counter))

    @property
    def media_length(self):
        return self._player.media_length

    @property
    def media_metadata(self):
        return self._media_metadata

    @property
    def current_playback_time(self):
        return self._player.current_time

    def get_media_path(self) -> str:
        return self._player.media_path

    def get_media_title(self) -> str:
        return self._media_metadata['title']

    def on_request_to_load_media(self, media_path: str) -> None:

        extension = os.path.splitext(media_path)[1][1:]

        self._change_player_according_to_extension(extension)

        self._player.load_media(media_path)

        self._media_metadata['media length'] = self.media_length

    def on_request_to_export_audio_segment(self, segment_name: str, start_time: float, end_time: float):

        export_dir = Path(self.ui.ask_for_directory('Export audio'))

        media_exporter.export_audio_segment(
            audio_path=self._player.media_path,
            dir=export_dir,
            file_title=self.media_metadata['title'],
            start_time=start_time,
            end_time=end_time,
            segment_name=segment_name
        )

    def on_request_new_file(self) -> None:
        try:
            self._file_manager.new()
        except UserCancelledSaveError:
            return

        self._initial_file_setup()

        self._undo_manager.clear()
        self._undo_manager.record(self.get_state(), StateAction.FILE_LOAD)

    def on_request_to_close(self) -> None:
        self._file_manager.ask_save_if_necessary()

        sys.exit()

    def _initial_file_setup(self) -> None:
        create_timeline(
            TimelineKind.SLIDER_TIMELINE,
            self._timeline_collection,
            self._timeline_ui_collection,
            ""
        )

    def _change_player_according_to_extension(self, extension: str) -> None:
        if (
                extension
                in globals_.SUPPORTED_AUDIO_FORMATS + globals_.NATIVE_AUDIO_FORMATS
        ):
            self._change_to_audio_player_if_necessary()
        elif extension in globals_.NATIVE_VIDEO_FORMATS:
            self._change_to_video_player_if_necessary()
        else:
            raise ValueError(f"Media _file extension '{extension}' is not supported.")

    def _change_to_audio_player_if_necessary(self) -> None:
        if isinstance(self._player, player.VlcPlayer):
            self._player.destroy()
            self._player = player.PygamePlayer(previous_media_length=self._player.previous_media_length)

    def _change_to_video_player_if_necessary(self) -> None:
        if isinstance(self._player, player.PygamePlayer):
            self._player.destroy()
            self._player = player.VlcPlayer(previous_media_length=self._player.previous_media_length)

    def get_timelines_as_dict(self) -> dict:
        return self._timeline_collection.serialize_timelines()

    def get_elements_for_pasting(self) -> dict[str: dict | TimelineKind]:
        logger.debug(f"Getting clipboard contents for pasting...")
        elements = self._clipboard.get_contents_for_pasting()
        logger.debug(f"Got '{elements}'")
        return elements

    def clear_app(self) -> None:
        logger.info(f"Clearing app..")
        self._timeline_collection.clear()
        self._file_manager.clear()
        self._player.clear()
        logger.info(f"App cleared.")

    def load_file(self, file: TiliaFile) -> None:
        logger.info(f"Loading _file '{file}'...")

        if file.media_path:
            self.on_request_to_load_media(file.media_path)

        file_copy = dataclasses.asdict(file)  # must copy so keys don't get popped in passed _file

        for _, timeline in file_copy['timelines'].items():
            kind_str = timeline.pop("kind")
            if kind_str not in IMPLEMENTED_TIMELINE_KINDS:
                logger.debug(f"Timeline kind '{kind_str} is not implemented.")
                continue
            kind = TimelineKind[kind_str]
            try:
                name = timeline.pop("name")
            except KeyError:
                name = ""
            components = timeline.pop("components")

            create_timeline(
                kind,
                self._timeline_collection,
                self._timeline_ui_collection,
                name,
                components
            )

        self._undo_manager.clear()
        self._undo_manager.record(self.get_state(), StateAction.FILE_LOAD)

        logger.info(f"Loaded file.")


    def on_add_timeline(self, kind: TimelineKind) -> None:
        if kind not in (TimelineKind.HIERARCHY_TIMELINE, TimelineKind.MARKER_TIMELINE):
            raise NotImplementedError
        name = self.ui.ask_string(
            title="Name for new timeline", prompt="Choose name for new timeline"
        )

        create_timeline(
            kind,
            self._timeline_collection,
            self._timeline_ui_collection,
            name
        )

    def on_metadata_field_edited(self, field_name: str, value: str) -> None:
        self._media_metadata[field_name] = value

    def on_metadata_new_fields(self, field_list: list[str]) -> None:

        new_metadata = OrderedDict({key: '' for key in field_list})

        for field in field_list:
            if field in self._media_metadata:
                new_metadata[field] = self._media_metadata[field]

        self._media_metadata = new_metadata

    def get_state(self):
        return self._file_manager.get_save_parameters()

    def on_request_to_record_state(self, action: StateAction, no_repeat=False, repeat_identifier=''):
        self._undo_manager.record(self.get_state(), action, no_repeat=no_repeat, repeat_identifier=repeat_identifier)

    def on_request_to_restore_state(self, state: dict) -> None:
        self._timeline_collection.restore_state(state['timelines'])
        self._file_manager.restore_state(media_metadata=state['media_metadata'], media_path=state['media_path'])
        self.restore_player_state(state['media_path'])

    def restore_player_state(self, media_path: str) -> None:
        if self._player.media_path == media_path:
            return
        else:
            self.on_request_to_load_media(media_path)


def _associate_timeline_and_timeline_ui_collections(
        timeline_collection: TimelineCollection,
        timeline_ui_collection: TimelineUICollection,
):
    timeline_ui_collection._timeline_collection = timeline_collection
    timeline_collection._timeline_ui_collection = timeline_ui_collection


def config_logging():
    FORMAT = " %(name)-50s %(lineno)-5s %(levelname)-8s %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)


def get_ui(kind: UserInterfaceKind, app: TiLiA):
    if kind == UserInterfaceKind.TKINTER:
        return TkinterUI(app)
    if kind == UserInterfaceKind.MOCK:
        return MagicMock()


def main():
    config_logging()
    os.chdir(os.path.dirname(__file__))

    TiLiA(ui_kind=UserInterfaceKind.TKINTER)


if __name__ == "__main__":
    class PropagatingThread(Thread):
        # noinspection PyAttributeOutsideInit
        def run(self):
            self.exc = None
            try:
                self.ret = self._target(*self._args, **self._kwargs)
            except BaseException as e:
                self.exc = e

        def join(self, timeout=None):
            super(PropagatingThread, self).join(timeout)
            if self.exc:
                raise self.exc
            return self.ret

    main_thread = PropagatingThread(target=main)
    main_thread.start()
    main_thread.join()
