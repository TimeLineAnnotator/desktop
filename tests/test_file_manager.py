from pathlib import Path
import pytest

from tilia.requests import Post, post
from tilia.file.tilia_file import TiliaFile
from tilia.file.file_manager import FileManager


@pytest.fixture
def file_manager():
    return FileManager()


def get_empty_save_params():
    return {
        k: v
        for k, v in TiliaFile().__dict__.items()
        if k in FileManager.FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION
    }


class TestFileManager:
    def test_open(self, tilia, file_manager):
        path = Path(__file__).parent / "test_file.tla"
        tilia.clear_app()
        file_manager.open(path)
        tilia.clear_app()

    def test_file_not_modified_after_open(self, tilia, file_manager):
        path = Path(__file__).parent / "test_file.tla"
        tilia.clear_app()
        file_manager.open(path)
        assert not file_manager.is_file_modified(file_manager.file.__dict__)

    def test_add_metadata_field_at_start(self, file_manager):
        post(Post.REQUEST_ADD_MEDIA_METADATA_FIELD, "newfield", 0)
        assert list(file_manager.file.media_metadata)[0] == "newfield"

    def test_add_metadata_field_at_middle(self, file_manager):
        post(Post.REQUEST_ADD_MEDIA_METADATA_FIELD, "newfield", 2)
        assert list(file_manager.file.media_metadata)[2] == "newfield"

    def test_set_metadata_field(self, file_manager):
        post(Post.REQUEST_SET_MEDIA_METADATA_FIELD, "title", "new title")
        assert file_manager.file.media_metadata["title"] == "new title"

    def test_open_file_with_custom_metadata_fields(self, file_manager):
        path = Path(
            Path(__file__).parent.parent,
            "tests",
            "test_metadata_custom_fields.tla",
        )
        file_manager.open(path)

        assert list(file_manager.file.media_metadata.items()) == [
            ("test_field1", "a"),
            ("test_field2", "b"),
            ("test_field3", "c"),
        ]

    def test_is_file_modified_empty_file(self, tilia, file_manager):
        # get save parameters of empty file
        assert not file_manager.is_file_modified(get_empty_save_params())

    def test_is_file_modified_not_modified_after_update(self, file_manager):
        params = get_empty_save_params()
        params["media_metadata"]["title"] = "New Title"
        file_manager.update_file(params)
        assert not file_manager.is_file_modified(params)

    def test_is_file_modified_when_modified_timelines(self, file_manager):
        # get save parameters of empty file
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
