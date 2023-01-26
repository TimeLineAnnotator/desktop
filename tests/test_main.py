from pathlib import Path
from unittest.mock import patch

import pytest
import os

from tilia import events
from tilia.events import Event
from tilia.files import TiliaFile
from tilia.globals_ import SUPPORTED_VIDEO_FORMATS, SUPPORTED_AUDIO_FORMATS
from tilia.file_manager import FileManager
from tilia.player import player


# noinspection PyProtectedMember


@pytest.fixture
def file_manager(tilia):
    return tilia._file_manager


class TestTilia:
    def test_change_player_according_to_extension(self, tilia):

        tilia._change_player_according_to_extension(SUPPORTED_VIDEO_FORMATS[0])
        assert isinstance(tilia._player, player.VlcPlayer)

        tilia._change_player_according_to_extension(SUPPORTED_AUDIO_FORMATS[0])
        assert isinstance(tilia._player, player.PygamePlayer)

        tilia._change_player_according_to_extension(SUPPORTED_VIDEO_FORMATS[0])
        assert isinstance(tilia._player, player.VlcPlayer)

        tilia._change_player_according_to_extension(SUPPORTED_AUDIO_FORMATS[0])
        assert isinstance(tilia._player, player.PygamePlayer)


class TestFileManager:
    def test_open(self, tilia, file_manager):
        os.chdir(Path(Path(__file__).absolute().parents[1], "tests"))
        file_manager._app.ui.get_file_open_path = lambda: "test_file.tla"
        file_manager.ask_save_if_necessary = lambda: True

        with patch("tkinter.PhotoImage", lambda *args, **kwargs: None):
            file_manager.open()

        tilia.clear_app()

    def test_on_metadata_new_fields(self, tilia):
        new_metadata_fields = ["test_field1", "test_field2"]
        events.post(Event.METADATA_NEW_FIELDS, new_metadata_fields)

        assert list(tilia.media_metadata) == new_metadata_fields

    def test_on_metadata_field_edited(self, tilia):
        edited_field = "title"
        new_value = "test title"
        events.post(Event.METADATA_FIELD_EDITED, edited_field, new_value)

        assert tilia.media_metadata[edited_field] == new_value

    def test_load_custom_metadata_fields(self, tilia, file_manager):
        os.chdir(Path(Path(__file__).absolute().parents[1], "tests"))
        file_manager.open_file_by_path("test_metadata_custom_fields.tla")

        assert list(file_manager._file.media_metadata.items()) == [
            ("test_field1", "a"),
            ("test_field2", "b"),
            ("test_field3", "c"),
        ]

        tilia.clear_app()

    def test_is_file_modified(self, tilia, file_manager):

        empty_file = TiliaFile()
        empty_file_save_params = {}
        for attr in FileManager.FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION:
            empty_file_save_params[attr] = getattr(empty_file, attr)
        file_manager.get_save_parameters = lambda: empty_file_save_params

        assert not file_manager.was_file_modified()

        file_manager.get_save_parameters = lambda: modified_save_params

        import copy

        modified_save_params = copy.deepcopy(empty_file_save_params)
        modified_save_params["timelines"] = {
            "0": {
                "kind": "SLIDER_TIMELINE",
                "display_position": 0,
                "is_visible": True,
                "height": 10,
            },
            "1": {
                "kind": "HIERARCHY_TIMELINE",
                "display_position": 0,
                "height": 10,
                "is_visible": True,
                "name": "test",
                "components": {},
            },
        }

        assert file_manager.was_file_modified()

        modified_save_params = copy.deepcopy(empty_file_save_params)
        modified_save_params["media_metadata"]["title"] = "modified title"
        assert file_manager.was_file_modified()

        modified_save_params = copy.deepcopy(empty_file_save_params)
        modified_save_params["media_metadata"].pop("title")
        assert file_manager.was_file_modified()

        modified_save_params = copy.deepcopy(empty_file_save_params)
        modified_save_params["media_path"] = "modified path"
        assert file_manager.was_file_modified()
