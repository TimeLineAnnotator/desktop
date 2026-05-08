import json
import sys
from pathlib import Path, WindowsPath
from random import randint
from unittest.mock import mock_open, patch

import pytest

from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import (
    PatchPost,
    Serve,
    patch_file_dialog,
    patch_yes_no_or_cancel_mb,
    patch_yes_or_no_dialog,
)
from tests.utils import load_local_media
from tilia.file.file_manager import FileManager
from tilia.file.media_metadata import MediaMetadata
from tilia.file.tilia_file import TiliaFile
from tilia.requests import Get, Post, get, post
from tilia.ui import commands


def get_empty_save_params():
    return {
        k: v
        for k, v in TiliaFile().__dict__.items()
        if k in FileManager.FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION
    } | {"timelines_hash": ""}


class Tests:
    def test_save(self, tls, marker_tlui, tmp_path):
        marker_tlui.create_marker(0)
        tmp_file_path = (tmp_path / "test_save.tla").resolve().__str__()
        with patch_file_dialog(True, [tmp_file_path]):
            commands.execute("file.save_as")
        marker_tlui.create_marker(1)
        commands.execute("file.save")

        with patch_yes_or_no_dialog(True):
            commands.execute("timelines.clear_all")
        assert marker_tlui.is_empty
        with (
            patch_file_dialog(True, [tmp_file_path]),
            patch_yes_no_or_cancel_mb(False),  # do not save changes
        ):
            commands.execute("file.open")
        assert len(tls[0]) == 2


class TestFileManager:
    def test_metadata_edit_fields(self, tilia):
        num_required_fields = len(
            tilia.file_manager.file.media_metadata.REQUIRED_FIELDS
        )
        original = list(tilia.file_manager.file.media_metadata)
        idx = randint(
            num_required_fields, len(original) - 1
        )  # insert at some random index after the required fields
        fields = list(tilia.file_manager.file.media_metadata)
        fields.insert(idx, "newfield")
        post(Post.METADATA_UPDATE_FIELDS, fields)
        assert list(tilia.file_manager.file.media_metadata)[idx] == "newfield"

        fields.pop(idx)
        post(Post.METADATA_UPDATE_FIELDS, fields)
        assert list(tilia.file_manager.file.media_metadata)[idx] != "newfield"
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
            commands.execute("file.save")
        commands.execute("timeline.marker.add")
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

    def test_is_file_modified_after_notes_edit(self, tilia):
        # Regression test for #377: editing the "notes" metadata field
        # (and any other field, including added custom fields) directly
        # mutates self.file.media_metadata, so comparing the live state
        # against itself never reported a change. The save-changes
        # dialog never fired on close.
        post(Post.MEDIA_METADATA_FIELD_SET, "notes", "user-typed notes")

        assert tilia.file_manager.is_file_modified(get(Get.APP_STATE))

    def test_is_file_modified_after_title_edit(self, tilia):
        # Same root cause as the notes case (#377), so guard the title
        # path explicitly. The reporter mentioned existing automatic
        # tests cover other fields, but only the test at line ~111
        # actually catches it — it passes a custom params dict and so
        # bypasses the live-vs-live comparison this test exercises.
        post(Post.MEDIA_METADATA_FIELD_SET, "title", "Renamed")

        assert tilia.file_manager.is_file_modified(get(Get.APP_STATE))

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

    @pytest.mark.skipif(
        not sys.platform.startswith("win"), reason="Windows specific test"
    )
    def test_is_saved_with_posix_paths(self, qtui, tilia, tmp_path):
        file_path = tmp_path / "test.tla"
        load_local_media(EXAMPLE_MEDIA_PATH)

        with patch_file_dialog(True, [str(WindowsPath(file_path))]):
            commands.execute("file.save")

        with open(file_path, "r") as f:
            data = json.load(f)

        assert data["file_path"] == Path(file_path).as_posix()
        assert data["media_path"] == Path(EXAMPLE_MEDIA_PATH).as_posix()

    def test_save_without_set_title_and_different_file_name(
        self, qtui, tilia, tmp_path
    ):
        tla_path = tmp_path / "Some Title.tla"
        with patch_file_dialog(True, [str(tla_path)]):
            commands.execute("file.save")

        assert tilia.file_manager.file.media_metadata["title"] == "Some Title"

    def test_save_with_title_set_and_different_file_name(self, qtui, tilia, tmp_path):
        tilia.file_manager.file.media_metadata["title"] = "Title Already Set"
        tla_path = tmp_path / "Some Title.tla"
        with patch_file_dialog(True, [str(tla_path)]):
            commands.execute("file.save")

        assert tilia.file_manager.file.media_metadata["title"] == "Title Already Set"

    def test_save_fail_reverts_to_original_name(self, qtui, tilia, tmp_path):
        tla_path = tmp_path / "Non-existent Path" / "Some Other Title.tla"
        with patch_file_dialog(True, [str(tla_path)]):
            commands.execute("file.save")

        assert tilia.file_manager.file.media_metadata[
            "title"
        ] == MediaMetadata.REQUIRED_FIELDS.get("title")
