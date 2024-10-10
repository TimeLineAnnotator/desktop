import json
from unittest.mock import mock_open
from tests.mock import PatchPost, Serve
from tilia.file.media_metadata import MediaMetadata

from tilia.requests import Post, post, Get
from tilia.file.tilia_file import TiliaFile
from tilia.file.file_manager import FileManager
from unittest.mock import patch

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
