import json
from pathlib import Path
from unittest.mock import mock_open
import pytest
from tests.mock import PatchPost, PatchGet, Serve
from tilia.file.media_metadata import MediaMetadata

import tests.utils
from tilia.requests import Post, post, stop_listening_to_all, stop_serving_all, Get
from tilia.file.tilia_file import TiliaFile
from tilia.file.file_manager import FileManager
from unittest.mock import patch
from tilia.ui.windows.metadata import MediaMetadataWindow

from tilia.ui.actions import TiliaAction


def get_empty_save_params():
    return {
        k: v
        for k, v in TiliaFile().__dict__.items()
        if k in FileManager.FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION
    }


class TestUserActions:
    def test_save(self, tls, marker_tl, tmp_path, actions):
        marker_tl.create_marker(0)
        tmp_file_path = (tmp_path / "test_save.tla").resolve().__str__()
        with Serve(Get.FROM_USER_SAVE_PATH_TILIA, (tmp_file_path, "")):
            actions.trigger(TiliaAction.FILE_SAVE_AS)
        marker_tl.create_marker(1)
        actions.trigger(TiliaAction.FILE_SAVE)
        with Serve(Get.FROM_USER_YES_OR_NO, True):
            actions.trigger(TiliaAction.TIMELINES_CLEAR)
        assert marker_tl.is_empty
        with (
            Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file_path)),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        ):
            actions.trigger(TiliaAction.FILE_OPEN)
        assert len(tls[0]) == 2


class TestFileManager:
    def test_open(self, tilia):
        path = Path(__file__).parent / "test_file.tla"
        tilia.on_clear()
        tilia.file_manager.open(path)

    def test_open_with_timeline(self, tilia, tls, tmp_path, actions):
        timelines_data = {
            "0": {
                "height": 220,
                "is_visible": True,
                "ordinal": 1,
                "name": "test",
                "kind": "HIERARCHY_TIMELINE",
                "components": {},
            }
        }
        hierarchy_attrs = [(0, 1, 1), (1, 2, 1), (2, 3, 2)]

        for i, (start, end, level) in enumerate(hierarchy_attrs):
            timelines_data["0"]["components"][i] = {
                "start": start,
                "end": end,
                "level": level,
                "comments": "",
                "label": "Unit 1",
                "parent": None,
                "children": [],
                "kind": "HIERARCHY",
            }

        file_data = tests.utils.get_blank_file_data()
        file_data["timelines"] = timelines_data
        file_data["media_metadata"]["media length"] = 100
        file_data["media_metadata"]["playback end"] = 100

        tmp_file = tmp_path / "test_open_with_hierarchies.tla"
        tmp_file.write_text(json.dumps(file_data))
        with PatchGet(
            "tilia.file.file_manager", Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)
        ):
            actions.trigger(TiliaAction.FILE_OPEN)

        assert len(tls) == 2  # Slider timeline is also created by default
        assert len(tls[0]) == 3

    def test_file_not_modified_after_open(self, tilia):
        path = Path(__file__).parent / "test_file.tla"
        tilia.on_clear()
        tilia.file_manager.open(path)
        assert not tilia.file_manager.is_file_modified(tilia.file_manager.file.__dict__)

    def test_metadata_edit_fields(self, tilia):
        def get_displayed_list(input: list[str]) -> list[str]:
            output = []
            for item in input:
                if (
                    item
                    not in MediaMetadataWindow.SEPARATE_WINDOW_FIELDS
                    + list(MediaMetadataWindow.READ_ONLY_FIELDS)
                    + MediaMetadataWindow.PLAYBACK_TIMES
                ):
                    output.append(item)
            return output

        original = get_displayed_list(tilia.file_manager.file.media_metadata)
        fields = get_displayed_list(tilia.file_manager.file.media_metadata)
        fields.insert(2, "newfield")
        post(Post.METADATA_UPDATE_FIELDS, fields)
        assert (
            get_displayed_list(tilia.file_manager.file.media_metadata)[2] == "newfield"
        )

        fields.pop(2)
        post(Post.METADATA_UPDATE_FIELDS, fields)
        assert (
            get_displayed_list(tilia.file_manager.file.media_metadata)[2] != "newfield"
        )
        assert get_displayed_list(tilia.file_manager.file.media_metadata) == original

    def test_metadata_not_duplicated_required_fields(self, tilia):
        original = list(tilia.file_manager.file.media_metadata)
        duplicate = list(tilia.file_manager.file.media_metadata) + ["title"]
        post(Post.METADATA_UPDATE_FIELDS, duplicate)
        assert list(tilia.file_manager.file.media_metadata) == original

    def test_metadata_delete_fields(self, tilia):
        empty_list = []
        post(Post.METADATA_UPDATE_FIELDS, empty_list)
        assert list(tilia.file_manager.file.media_metadata) == list(
            tilia.file_manager.file.media_metadata.REQUIRED_FIELDS
        )

    def test_metadata_title_stays_on_top(self, tilia):
        not_so_empty_list = ["newfield"]
        post(Post.METADATA_UPDATE_FIELDS, not_so_empty_list)
        assert list(tilia.file_manager.file.media_metadata)[0] == "title"

    def test_metadata_set_field(self, tilia):
        post(Post.MEDIA_METADATA_FIELD_SET, "title", "new title")
        assert tilia.file_manager.file.media_metadata["title"] == "new title"

    def test_open_file_with_custom_metadata_fields(self, tilia):
        path = Path(__file__).parent / "custom_fields.tla"
        tilia.file_manager.open(path)

        assert list(tilia.file_manager.file.media_metadata.items()) == [
            ("test_field1", "a"),
            ("test_field2", "b"),
            ("test_field3", "c"),
        ]

    def test_is_file_modified_empty_file(self, tilia):
        assert not tilia.file_manager.is_file_modified(get_empty_save_params())

    def test_is_file_modified_not_modified_after_update(self, tilia):
        params = get_empty_save_params()
        params["media_metadata"]["title"] = "New Title"
        tilia.file_manager.update_file(params)
        assert not tilia.file_manager.is_file_modified(params)

    def test_is_file_modified_when_modified_timelines(self, tilia):
        params = get_empty_save_params()

        params["timelines"] = {
            "0": {
                "kind": "SLIDER_TIMELINE",
                "ordinal": 0,
                "is_visible": True,
                "height": 10,
            },
            "1": {
                "kind": "HIERARCHY_TIMELINE",
                "ordinal": 0,
                "height": 10,
                "is_visible": True,
                "name": "test",
                "components": {},
            },
        }

        assert tilia.file_manager.is_file_modified(params)

    def test_is_file_modified_modified_tile(self, tilia):
        params = get_empty_save_params()
        params["media_metadata"]["title"] = "modified title"
        assert tilia.file_manager.is_file_modified(params)

    def test_is_file_modified_removed_field_from_media_metadata(self, tilia):
        params = get_empty_save_params()
        params["media_metadata"].pop("title")
        assert tilia.file_manager.is_file_modified(params)

    def test_is_file_modified_modified_media_path(self, tilia):
        params = get_empty_save_params()
        params["media_path"] = "modified path"
        assert tilia.file_manager.is_file_modified(params)

    def test_import_metadata(self, tilia):
        data = {
            "title": "test",
            "artist": "artist",
            "album": "album",
            "genre": "genre",
            "year": "1999",
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(data))):
            post(Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH, "")

        assert tilia.file_manager.file.media_metadata == MediaMetadata.from_dict(data)

    def test_import_metadata_invalid_json(self, tilia):
        data = "nonsense"

        with patch("builtins.open", mock_open(read_data=data)):
            with PatchPost("tilia.errors", Post.DISPLAY_ERROR) as post_mock:
                post(Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH, "")

                post_mock.assert_called()

    def test_import_metadata_file_does_not_exist(self, tilia):
        with PatchPost("tilia.errors", Post.DISPLAY_ERROR) as post_mock:
            post(Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH, "nonexistent.json")

            post_mock.assert_called()
