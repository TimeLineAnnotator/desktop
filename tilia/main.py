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
import json
from collections import OrderedDict
from datetime import datetime

from typing import TYPE_CHECKING

from tilia.clipboard import Clipboard
from tilia.timelines.hash_timelines import hash_timeline_collection_data
from tilia.undo_manager import UndoManager

if TYPE_CHECKING:
    from tilia.ui.timelines.common import TimelineUICollection

from unittest.mock import MagicMock

from tilia import globals_, events
from tilia.exceptions import UserCancelledSaveError, UserCancelledOpenError
from tilia.globals_ import UserInterfaceKind
from tilia.files import TiliaFile, create_new_media_metadata

import os
import sys
from threading import Thread

from tilia.player import player
from tilia.events import Event, subscribe

from tilia.timelines.timeline_kinds import TimelineKind, IMPLEMENTED_TIMELINE_KINDS
from tilia.timelines.collection import TimelineCollection
from tilia.ui.tkinter.tkinterui import TkinterUI

import logging

logger = logging.getLogger(__name__)


class TiLiA:
    def __init__(self, ui_kind: UserInterfaceKind):
        logger.info("TiLia starting...")

        subscribe(self, Event.FILE_REQUEST_TO_LOAD_MEDIA, self.on_request_to_load_media)
        subscribe(self, Event.APP_ADD_TIMELINE, self.on_add_timeline)
        subscribe(self, Event.FILE_REQUEST_NEW_FILE, self.on_request_new_file)
        subscribe(self, Event.APP_REQUEST_TO_CLOSE, self.on_request_to_close)
        subscribe(self, Event.METADATA_FIELD_EDITED, self.on_metadata_field_edited)
        subscribe(self, Event.METADATA_NEW_FIELDS, self.on_metadata_new_fields)

        self.settings = None  # TODO load settings

        self._id_counter = itertools.count()
        self._file_manager = FileManager(self)

        self.ui = get_ui(ui_kind, self)

        self._timeline_collection = TimelineCollection(self)
        self._timeline_ui_collection = self.ui.get_timeline_ui_collection()

        self._associate_timeline_and_timeline_ui_collections(
            self._timeline_collection, self._timeline_ui_collection
        )

        self._timeline_with_ui_builder = TimelineWithUIBuilder(
            self._timeline_collection, self._timeline_ui_collection
        )

        self._player = player.PygamePlayer()
        self._clipboard = Clipboard()
        self._undo_manager = UndoManager()

        self._media_metadata = create_new_media_metadata()

        logger.info("TiLiA started.")

        self._code_for_dev()

        self._initial_file_setup()

        self.ui.launch()

    # noinspection PyProtectedMember
    def _code_for_dev(self):
        """Use this to execute code before the ui mainloop runs."""

        # self.on_request_to_load_media(
        #     r"C:\Música e musicologia\Outros\Sonatas do Mozart\Piano Sonata No -12 in F - K332 - I - Allegro.ogg")
        #
        # self._timeline_with_ui_builder.create_timeline(
        #     TimelineKind.HIERARCHY_TIMELINE, "HTL1"
        # )

    @property
    def media_length(self):
        return self._player.media_length

    @property
    def media_metadata(self):
        return self._media_metadata

    @property
    def current_playback_time(self):
        return self._player.current_time

    def on_request_to_load_media(self, media_path: str) -> None:
        import os

        extension = os.path.splitext(media_path)[1][1:]

        self._change_player_according_to_extension(extension)

        self._player.load_media(media_path)

        self._media_metadata['media length'] = self.media_length

    def on_request_new_file(self) -> None:
        try:
            self._file_manager.new()
        except UserCancelledSaveError:
            return

        self._initial_file_setup()

    def on_request_to_close(self) -> None:
        self._file_manager.ask_save_if_necessary()

        sys.exit()

    def get_id(self) -> str:
        return str(next(self._id_counter))

    def _initial_file_setup(self) -> None:
        self._timeline_with_ui_builder.create_timeline(TimelineKind.SLIDER_TIMELINE, "")

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
            self._player = player.PygamePlayer()

    def _change_to_video_player_if_necessary(self) -> None:
        if isinstance(self._player, player.PygamePlayer):
            self._player.destroy()
            self._player = player.VlcPlayer()

    def get_timelines_as_dict(self) -> dict:
        return self._timeline_collection.serialize_timelines()

    def get_media_path(self) -> str:
        return self._player.media_path

    def get_media_title(self) -> str:
        return self._media_metadata['title']

    def get_elements_for_pasting(self):
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
            self._timeline_with_ui_builder.create_timeline(kind, name, components)

        logger.info(f"Loaded _file.")

    def on_add_timeline(self, kind: TimelineKind) -> None:
        if kind != TimelineKind.HIERARCHY_TIMELINE:
            raise NotImplementedError
        name = self.ui.ask_string(
            title="Name for new timeline", prompt="Choose name for new timeline"
        )
        self._timeline_with_ui_builder.create_timeline(kind, name)

    @staticmethod
    def _associate_timeline_and_timeline_ui_collections(
        timeline_collection: TimelineCollection,
        timeline_ui_collection: TimelineUICollection,
    ):
        timeline_ui_collection._timeline_collection = timeline_collection
        timeline_collection._timeline_ui_collection = timeline_ui_collection

    def on_metadata_field_edited(self, field_name: str, value: str) -> None:
        self._media_metadata[field_name] = value

    def on_metadata_new_fields(self, field_list: list[str]) -> None:

        new_metadata = OrderedDict({key: '' for key in field_list})

        for field in field_list:
            if field in self._media_metadata:
                new_metadata[field] = self._media_metadata[field]

        self._media_metadata = new_metadata


class FileManager:
    JSON_CONFIG = {"indent": 2}

    FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION = ['media_metadata', 'timelines', 'media_path']

    def __init__(self, app: TiLiA, file: TiliaFile = None):
        subscribe(self, Event.PLAYER_MEDIA_LOADED, self.on_media_loaded)
        subscribe(self, Event.FILE_REQUEST_TO_SAVE, self.save)
        subscribe(self, Event.FILE_REQUEST_TO_OPEN, self.open)

        self._app = app

        if not file:
            self._file = TiliaFile()
        else:
            self._file = file

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
        self._file.file_path = self._get_file_path(save_as)
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
            self._file_manager.ask_save_if_necessary()
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

    def _get_file_path(self, save_as: bool) -> str:
        if not self._file.file_path or save_as:
            return self._app.ui.get_file_save_path(self.get_default_filename())
        else:
            return self._file.file_path

    def get_default_filename(self) -> str:
        return f"{self._app.get_media_title()} {datetime.now().strftime('%d-%m-%Y %H%M%S')}"

    def clear(self) -> None:
        logger.debug(f"Clearing _file manager...")
        self._file = TiliaFile()


class TimelineWithUIBuilder:
    def __init__(
        self,
        timeline_collection: TimelineCollection,
        timeline_ui_collection: TimelineUICollection,
    ):
        self.timeline_ui_collection = timeline_ui_collection
        self.timeline_collection = timeline_collection

    @staticmethod
    def _validate_timeline_kind(timeline_kind: TimelineKind):
        if not isinstance(timeline_kind, TimelineKind):
            raise ValueError(
                f"Can't create timeline: invalid timeline kind '{timeline_kind}'"
            )

    def create_timeline(
        self, timeline_kind: TimelineKind, name: str, components: dict[int] = None
    ):
        self._validate_timeline_kind(timeline_kind)

        timeline = self.timeline_collection.create_timeline(timeline_kind)
        timeline_ui = self.timeline_ui_collection.create_timeline_ui(
            timeline_kind, name
        )

        timeline.ui = timeline_ui
        timeline_ui.timeline = timeline

        if components:
            timeline.component_manager.deserialize_components(components)
        else:
            if timeline_kind == TimelineKind.HIERARCHY_TIMELINE:
                timeline.component_manager.create_initial_hierarchy()  # TODO temporary workaround. Make this into an user action.


# noinspection PyUnresolvedReferences
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

    # sys.excepthook = handle_exception

    opening_file = ""

    try:
        opening_file = sys.argv[1]
    except IndexError:
        pass

    app = TiLiA(ui_kind=UserInterfaceKind.TKINTER)


if __name__ == "__main__":
    main_thread = PropagatingThread(target=main)
    main_thread.start()
    main_thread.join()
