import json
from unittest.mock import mock_open
from tests.mock import PatchPost, Serve, patch_file_dialog, patch_yes_or_no_dialog
from tilia.file.media_metadata import MediaMetadata

from tilia.requests import Post, post, Get, get
from tilia.file.tilia_file import TiliaFile
from tilia.file.file_manager import FileManager
from unittest.mock import patch


def get_empty_save_params():
    return {
        k: v
        for k, v in TiliaFile().__dict__.items()
        if k in FileManager.FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION
    } | {"timelines_hash": ""}


class Tests:
    def test_save(self, tls, marker_tlui, tmp_path, user_actions):
        marker_tlui.create_marker(0)
        tmp_file_path = (tmp_path / "test_save.tla").resolve().__str__()
        with patch_file_dialog(True, [tmp_file_path]):
            user_actions.trigger("file_save_as")
        marker_tlui.create_marker(1)
        user_actions.trigger("file_save")

        with patch_yes_or_no_dialog(True):
            user_actions.trigger("timelines_clear")
        assert marker_tlui.is_empty
        with (
            patch_file_dialog(True, [tmp_file_path]),
            patch_yes_or_no_dialog(False),  # do not save changes
        ):
            user_actions.trigger("file_open")
        assert len(tls[0]) == 2


class TestFileManager:
    def test_metadata_edit_fields(self, tilia):
        original = list(tilia.file_manager.file.media_metadata)
        fields = list(tilia.file_manager.file.media_metadata)
        fields.insert(2, "newfield")
        post(Post.METADATA_UPDATE_FIELDS, fields)
        assert list(tilia.file_manager.file.media_metadata)[2] == "newfield"

        fields.pop(2)
        post(Post.METADATA_UPDATE_FIELDS, fields)
        assert list(tilia.file_manager.file.media_metadata)[2] != "newfield"
        assert list(tilia.file_manager.file.media_metadata) == original

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

    def test_is_file_modified_empty_file(self, tilia):
        assert not tilia.file_manager.is_file_modified(get(Get.APP_STATE))

    def test_is_file_modified_not_modified_after_update(self, tilia):
        params = get_empty_save_params()
        params["media_metadata"]["title"] = "New Title"
        tilia.file_manager.update_file(params)
        assert not tilia.file_manager.is_file_modified(params)

    def test_is_file_modified_when_modified_timelines(
        self, tilia, marker_tlui, tmp_path
    ):
        with Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, tmp_path / "temp.tla")):
            post(Post.FILE_SAVE)
        post(Post.MARKER_ADD)
        assert tilia.file_manager.is_file_modified(get(Get.APP_STATE))

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

    def test_save_without_set_title_and_different_file_name(
        self, qtui, tilia, tmp_path, user_actions
    ):
        tla_path = tmp_path / "Some Title.tla"
        with patch_file_dialog(True, [str(tla_path)]):
            user_actions.trigger("file_save")

        assert tilia.file_manager.file.media_metadata["title"] == "Some Title"

    def test_save_with_title_set_and_different_file_name(
        self, qtui, tilia, tmp_path, user_actions
    ):
        tilia.file_manager.file.media_metadata["title"] = "Title Already Set"
        tla_path = tmp_path / "Some Title.tla"
        with patch_file_dialog(True, [str(tla_path)]):
            user_actions.trigger("file_save")

        assert tilia.file_manager.file.media_metadata["title"] == "Title Already Set"

    def test_save_fail_reverts_to_original_name(
        self, qtui, tilia, tmp_path, user_actions
    ):
        tla_path = tmp_path / "Non-existent Path" / "Some Other Title.tla"
        with patch_file_dialog(True, [str(tla_path)]):
            user_actions.trigger("file_save")

        assert tilia.file_manager.file.media_metadata[
            "title"
        ] == MediaMetadata.REQUIRED_FIELDS.get("title")
