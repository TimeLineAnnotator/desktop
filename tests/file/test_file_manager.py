import json
from pathlib import Path
from unittest.mock import mock_open
import pytest
from tests.mock import PatchPost
from tilia.file.media_metadata import MediaMetadata

from tilia.requests import Post, post, stop_listening_to_all, stop_serving_all
from tilia.file.tilia_file import TiliaFile
from tilia.file.file_manager import FileManager
from unittest.mock import patch


@pytest.fixture
def file_manager():
    _file_manager = FileManager()
    yield _file_manager
    stop_listening_to_all(_file_manager)
    stop_serving_all(_file_manager)


def get_empty_save_params():
    return {
        k: v
        for k, v in TiliaFile().__dict__.items()
        if k in FileManager.FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION
    }


class TestFileManager:
    def test_open(self, tilia):
        path = Path(__file__).parent / "test_file.tla"
        tilia.clear_app()
        tilia.file_manager.open(path)

    def test_file_not_modified_after_open(self, tilia):
        path = Path(__file__).parent / "test_file.tla"
        tilia.clear_app()
        tilia.file_manager.open(path)
        assert not tilia.file_manager.is_file_modified(tilia.file_manager.file.__dict__)

    def test_add_metadata_field_at_start(self, file_manager):
        previous_fields = list(file_manager.file.media_metadata)
        post(Post.REQUEST_ADD_MEDIA_METADATA_FIELD, "newfield", 0)
        assert list(file_manager.file.media_metadata)[0] == "newfield"
        assert list(file_manager.file.media_metadata)[1:] == previous_fields

    def test_add_metadata_field_at_middle(self, file_manager):
        previous_fields = list(file_manager.file.media_metadata)
        post(Post.REQUEST_ADD_MEDIA_METADATA_FIELD, "newfield", 2)
        result = list(file_manager.file.media_metadata)
        assert list(file_manager.file.media_metadata)[2] == "newfield"
        result.pop(2)
        assert result == previous_fields

    def test_set_metadata_field(self, file_manager):
        post(Post.REQUEST_SET_MEDIA_METADATA_FIELD, "title", "new title")
        assert file_manager.file.media_metadata["title"] == "new title"

    def test_open_file_with_custom_metadata_fields(self, file_manager):
        path = Path(__file__).parent / "custom_fields.tla"
        file_manager.open(path)

        assert list(file_manager.file.media_metadata.items()) == [
            ("test_field1", "a"),
            ("test_field2", "b"),
            ("test_field3", "c"),
        ]

    def test_is_file_modified_empty_file(self, file_manager):
        assert not file_manager.is_file_modified(get_empty_save_params())

    def test_is_file_modified_not_modified_after_update(self, file_manager):
        params = get_empty_save_params()
        params["media_metadata"]["title"] = "New Title"
        file_manager.update_file(params)
        assert not file_manager.is_file_modified(params)

    def test_is_file_modified_when_modified_timelines(self, file_manager):
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

        assert file_manager.is_file_modified(params)

    def test_is_file_modified_modified_tile(self, file_manager):
        params = get_empty_save_params()
        params["media_metadata"]["title"] = "modified title"
        assert file_manager.is_file_modified(params)

    def test_is_file_modified_removed_field_from_media_metadata(self, file_manager):
        params = get_empty_save_params()
        params["media_metadata"].pop("title")
        assert file_manager.is_file_modified(params)

    def test_is_file_modified_modified_media_path(self, file_manager):
        params = get_empty_save_params()
        params["media_path"] = "modified path"
        assert file_manager.is_file_modified(params)

    def test_import_metadata(self, file_manager):
        data = {
            "title": "test",
            "artist": "artist",
            "album": "album",
            "genre": "genre",
            "year": "1999",
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(data))):
            post(Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH, "")

        assert file_manager.file.media_metadata == MediaMetadata.from_dict(data)

    def test_import_metadata_invalid_json(self, file_manager):
        data = "nonsense"

        with patch("builtins.open", mock_open(read_data=data)):
            with PatchPost(
                "tilia.file.file_manager", Post.REQUEST_DISPLAY_ERROR
            ) as post_mock:
                post(Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH, "")

                post_mock.assert_called()

    def test_import_metadata_file_does_not_exist(self, file_manager):
        with PatchPost(
            "tilia.file.file_manager", Post.REQUEST_DISPLAY_ERROR
        ) as post_mock:
            post(Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH, "nonexistent.json")

            post_mock.assert_called()
