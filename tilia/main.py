"""
Entry point for the application.

Defines a TiLiA object which is composed, among other things, of instances of the following classes:
    - FileManager, which handles file processing (open, save, new, etc...);
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
from datetime import datetime

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from tilia.ui.timelines.common import TimelineUICollection

from unittest.mock import MagicMock

from tilia import globals_
from tilia.exceptions import UserCancelledSaveError, UserCancelledOpenError
from tilia.globals_ import UserInterfaceKind
from tilia.files import TiliaFile, MediaMetadata


import os
import sys
from threading import Thread

from tilia.player import player
from tilia.events import Subscriber, EventName

from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.collection import TimelineCollection
from tilia.ui.tkinter.tkinterui import TkinterUI

import logging

logger = logging.getLogger(__name__)


class TiLiA(Subscriber):
    def __init__(self, ui_kind: UserInterfaceKind):
        super().__init__(
            subscriptions=[
                EventName.PLAYER_CHANGE_TO_VIDEO_PLAYER,
                EventName.PLAYER_CHANGE_TO_AUDIO_PLAYER,
                EventName.FILE_REQUEST_TO_LOAD_MEDIA,
                EventName.APP_ADD_TIMELINE,
                EventName.FILE_REQUEST_NEW_FILE,
                EventName.APP_REQUEST_TO_CLOSE,
            ]
        )

        self.settings = None  # TODO load settings

        self._id_counter = itertools.count()
        self._file_manager = FileManager(self)

        logger.info("TiLia starting...")

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

        self._media_metadata = MediaMetadata()

        logger.info("TiLiA started.")

        self._code_for_dev()

        self._initial_file_setup()

        self.ui.launch()

    # noinspection PyProtectedMember
    def _code_for_dev(self):
        """Use this to execute code before the ui mainloop runs."""
        # self._timeline_with_ui_builder.create_timeline(
        #     TimelineKind.HIERARCHY_TIMELINE, "HTL1"
        # )
        #
        # self._timeline_with_ui_builder.create_timeline(
        #     TimelineKind.HIERARCHY_TIMELINE, "HTL2"
        # )

    @property
    def media_length(self):
        return self._player.media_length

    @property
    def current_playback_time(self):
        return self._player.current_time

    def on_subscribed_event(
        self, event_name: str, *args: tuple, **kwargs: dict
    ) -> None:
        if event_name == EventName.FILE_REQUEST_TO_LOAD_MEDIA:
            self.on_request_to_load_media(*args)
        elif event_name == EventName.APP_ADD_TIMELINE:
            self.on_add_timeline(*args)
        elif event_name == EventName.FILE_REQUEST_NEW_FILE:
            self.on_request_new_file()
        elif event_name == EventName.APP_REQUEST_TO_CLOSE:
            self.on_request_to_close()

    def on_request_to_load_media(self, media_path: str):
        import os

        extension = os.path.splitext(media_path)[1][1:]

        self._change_player_according_to_extension(extension)

        self._player.load_media(media_path)

    def on_request_new_file(self):
        try:
            self._file_manager.new()
        except UserCancelledSaveError:
            return

        self._initial_file_setup()

    @staticmethod
    def on_request_to_close():
        """TODO should ask to save if file was modified."""
        sys.exit()

    def get_id(self) -> str:
        return str(next(self._id_counter))

    def _initial_file_setup(self):
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
            raise ValueError(f"Media file extension '{extension}' is not supported.")

    def _change_to_audio_player_if_necessary(self):
        if isinstance(self._player, player.VlcPlayer):
            self._player.destroy()
            self._player = player.PygamePlayer()

    def _change_to_video_player_if_necessary(self):
        if isinstance(self._player, player.PygamePlayer):
            self._player.destroy()
            self._player = player.VlcPlayer()

    def get_media_metadata_as_dict(self):
        return dataclasses.asdict(self._media_metadata)

    def get_timelines_as_dict(self):
        return self._timeline_collection.serialize_timelines()

    def get_media_path(self):
        return self._player.media_path

    def get_media_title(self):
        return self._media_metadata.title

    def clear_app(self):
        logger.info(f"Clearing app..")
        self._timeline_collection.clear()
        self._file_manager.clear()
        self._player.clear()
        logger.info(f"App cleared.")

    def load_file(self, file: TiliaFile) -> None:
        logger.info(f"Loading file '{file}'...")

        if file.media_path:
            self.on_request_to_load_media(file.media_path)

        for _, timeline in file.timelines.items():
            kind = TimelineKind[timeline.pop("kind")]
            try:
                name = timeline.pop("name")
            except KeyError:
                name = ""
            components = timeline.pop("components")
            self._timeline_with_ui_builder.create_timeline(kind, name, components)

        logger.info(f"Loaded file.")

    def on_add_timeline(self, kind: TimelineKind):
        """Not functional yet."""
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


class FileManager(Subscriber):
    JSON_CONFIG = {"indent": 2}
    SUBSCRIPTIONS = [
        EventName.PLAYER_MEDIA_LOADED,
        EventName.FILE_REQUEST_TO_SAVE,
        EventName.FILE_REQUEST_TO_OPEN,
    ]

    def __init__(self, app: TiLiA, file: TiliaFile = None):
        super().__init__(subscriptions=self.SUBSCRIPTIONS)
        # self.auto_saver = AutoSaver() # TODO reimplement autosaver
        self._file_is_modified = False
        self._app = app

        if not file:
            self._file = TiliaFile()
        else:
            self._file = file

    def _update_file(self, **kwargs) -> None:
        for keyword, value in kwargs.items():
            logger.debug(f"Updating file paramenter '{keyword}' to '{value}'")
            setattr(self._file, keyword, value)

    def save(self, save_as: bool) -> None:
        logger.info(f"Saving file...")
        try:
            save_params = self._get_save_parameters(save_as)
        except UserCancelledSaveError:
            return

        self._update_file(**save_params)

        logger.debug(f"Using path '{self._file.file_path}'")
        with open(self._file.file_path, "w", encoding="utf-8") as file:
            json.dump(dataclasses.asdict(self._file), file, **self.JSON_CONFIG)

        logger.info(f"File saved.")

    def new(self):
        logger.debug(f"Processing new file request.")
        try:
            self._ask_save_if_necessary()
        except UserCancelledOpenError:
            return

        self._app.clear_app()

        self._file = TiliaFile()

        logger.info(f"New file created.")

    def open(self):
        logger.debug(f"Processing open file request.")
        try:
            self._ask_save_if_necessary()
            logger.debug(f"Getting path of file to open.")
            file_path = self._app.ui.get_file_open_path()
            logger.debug(f"Got path {file_path}")
        except UserCancelledOpenError:
            return

        self._app.clear_app()

        self._open_file_path(file_path)

    def _open_file_path(self, file_path: str):
        logger.debug(f"Opening file path {file_path}.")

        with open(file_path, "r", encoding="utf-8") as file:
            file_dict = json.load(file)

        self._file = TiliaFile(**file_dict)
        self._app.load_file(self._file)

    def _ask_save_if_necessary(self):
        if not self._file_is_modified:
            return

        response = self._app.ui.ask_save_changes()

        if response:
            logger.debug("User chose to save file before opening.")
            self.save(save_as=False)
        elif response is False:
            logger.debug("User chose not to save file before opening.")
            pass
        elif response is None:
            logger.debug("User cancelled file open.")
            raise UserCancelledOpenError()

    def _get_save_parameters(self, save_as: bool) -> dict:
        return {
            "media_metadata": self._app.get_media_metadata_as_dict(),
            "timelines": self._app.get_timelines_as_dict(),
            "media_path": self._app.get_media_path(),
            "file_path": self._get_file_path(save_as),
        }

    def on_media_loaded(self, media_path: str, *_) -> None:
        logger.debug(f"Updating file media path to '{media_path}'")
        self._file.media_path = media_path

    def on_subscribed_event(
        self, event_name: str, *args: tuple, **kwargs: dict
    ) -> None:
        if event_name == EventName.PLAYER_MEDIA_LOADED:
            self.on_media_loaded(*args)
        elif event_name == EventName.FILE_REQUEST_TO_SAVE:
            self.save(**kwargs)
        elif event_name == EventName.FILE_REQUEST_TO_OPEN:
            self.open()

    def _get_file_path(self, save_as: bool) -> str:
        if not self._file.file_path or save_as:
            return self._app.ui.get_file_save_path(self.get_default_filename())
        else:
            return self._file.file_path

    def get_default_filename(self) -> str:
        return f"{self._app.get_media_title()} {datetime.now().strftime('%d-%m-%Y %H%M%S')}"

    def clear(self):
        logger.debug(f"Clearing file manager...")
        self._file = TiliaFile(media_metadata=MediaMetadata())


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
