import json
import shutil
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
from tests.utils import (
    EXAMPLE_YOUTUBE_URL,
    load_local_media,
    load_youtube_media,
    save_tilia_to_tmp_path,
)
from tilia.file import autosave
from tilia.file.file_manager import FileManager
from tilia.file.media_metadata import MediaMetadata
from tilia.file.tilia_file import TiliaFile
from tilia.media.player import QtAudioPlayer
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

    def test_file_open_duration_confirmation_does_not_mark_modified(
        self, tilia, tmp_path
    ):
        # Opening a .tla occasionally sets media duration twice, due to the asynchronous nature of the YouTube player.
        # Confirmation reports with "keep" should not trigger a modification flag.
        tilia.set_file_media_duration(100, scale_timelines="keep")
        tmp_file_path = (tmp_path / "test_save.tla").resolve().__str__()
        tilia.file_manager.on_save_to_path_request(tmp_file_path)
        assert not tilia.file_manager.is_file_modified(get(Get.APP_STATE))

        tilia.set_file_media_duration(100.94, scale_timelines="keep")
        assert not tilia.file_manager.is_file_modified(get(Get.APP_STATE))

    def test_duration_change_after_save_marks_file_modified(self, tilia, tmp_path):
        tilia.set_file_media_duration(120, scale_timelines="prompt")
        tmp_file_path = (tmp_path / "test_save.tla").resolve().__str__()
        tilia.file_manager.on_save_to_path_request(tmp_file_path)
        tilia.set_file_media_duration(10, scale_timelines="prompt")
        assert tilia.file_manager.is_file_modified(get(Get.APP_STATE))

    def test_media_load_marks_file_modified(self, tilia):
        # Loading a different media file is a user action and must be
        # detected as a modification so the "save changes?" prompt fires.
        if not post(Post.APP_MEDIA_LOAD, EXAMPLE_MEDIA_PATH):
            pytest.skip("media failed to load")
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


HASH_KEYS = {"hash", "components_hash", "timelines_hash"}


def find_hash_keys(data, path=()):
    """Returns the path to every hash key in `data`, at any depth."""
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in HASH_KEYS:
                found.append((*path, key))
            found += find_hash_keys(value, (*path, key))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            found += find_hash_keys(value, (*path, index))
    return found


class TestHashesAreNotSaved:
    def test_saved_file_has_no_hashes(self, tilia, marker_tlui, tmp_path):
        commands.execute("timeline.marker.add")
        file_path = save_tilia_to_tmp_path(tmp_path)

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        marker_tl_data = data["timelines"][str(marker_tlui.id)]
        assert len(marker_tl_data["components"]) == 1
        assert find_hash_keys(data) == []

    @staticmethod
    def save_and_reopen_checking_no_hashes(tmp_path):
        file_path = save_tilia_to_tmp_path(tmp_path)
        with open(file_path, encoding="utf-8") as f:
            assert find_hash_keys(json.load(f)) == []
        post(Post.APP_CLEAR)
        commands.execute("file.open", path=file_path)

    def test_file_without_hashes_reopens_unmodified(self, tilia, marker_tlui, tmp_path):
        commands.execute("timeline.marker.add")
        self.save_and_reopen_checking_no_hashes(tmp_path)

        assert not get(Get.IS_FILE_MODIFIED)

    def test_change_after_reopening_file_without_hashes_is_detected(
        self, tilia, tls, marker_tlui, tmp_path
    ):
        self.save_and_reopen_checking_no_hashes(tmp_path)
        commands.execute("timeline.marker.add")

        assert get(Get.IS_FILE_MODIFIED)


class TestOtherMediaIsAnUnsavedChange:
    """Loading other media is an unsaved change, as any other, whether it is as long
    as the media the file had or not: closing TiLiA, a new file and opening another
    file ask to save it. An undo back to the saved media is no change."""

    # take1 is the media the file stores; take2 is as long, take3 is longer.
    LENGTHS = {"take1.mp3": 180.0, "take2.mp3": 180.0, "take3.mp3": 200.0}

    @pytest.fixture(autouse=True)
    def a_player_that_reports_their_lengths(self):
        def load(player, media_path):
            # As Qt's player does, once the media has loaded.
            player.on_media_duration_available(self.LENGTHS[Path(media_path).name])
            return True

        with patch.object(QtAudioPlayer, "_engine_load_media", load):
            yield

    @pytest.fixture
    def takes(self, tmp_path) -> Path:
        """The folder the media is in."""
        for name in self.LENGTHS:
            shutil.copy(EXAMPLE_MEDIA_PATH, tmp_path / name)
        return tmp_path

    @pytest.fixture
    def piece(self, qtui, tilia, tls, takes) -> str:
        """piece.tla, open, which stores take1.mp3, 3:00 long."""
        load_local_media((takes / "take1.mp3").as_posix())
        path = save_tilia_to_tmp_path(takes, "piece")
        commands.execute("file.open", path)
        assert Path(get(Get.MEDIA_PATH)) == takes / "take1.mp3"
        assert not tilia.is_file_modified()
        return path

    @staticmethod
    def media_stored_in(path: str) -> Path:
        """The media the file opens with."""
        post(Post.APP_CLEAR)
        commands.execute("file.open", path)
        return Path(get(Get.MEDIA_PATH))

    def test_closing_tilia_asks_to_save_it(self, piece, takes):
        load_local_media((takes / "take2.mp3").as_posix())

        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)) as asked,
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            commands.execute("tilia.close")

        assert asked.called
        exit_mock.assert_called()
        assert self.media_stored_in(piece) == takes / "take2.mp3"

    def test_a_new_file_asks_to_save_it(self, piece, takes):
        load_local_media((takes / "take2.mp3").as_posix())

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)) as asked:
            commands.execute("file.new")

        assert asked.called
        assert self.media_stored_in(piece) == takes / "take2.mp3"

    def test_opening_another_file_asks_to_save_it(self, piece, tilia, takes):
        load_local_media((takes / "take2.mp3").as_posix())

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (False, False)) as asked:
            commands.execute("file.open", piece)

        assert asked.called
        # Cancelled: the file is still open, with its change.
        assert Path(get(Get.MEDIA_PATH)) == takes / "take2.mp3"
        assert tilia.is_file_modified()

    @pytest.mark.parametrize(
        "take", ["take2.mp3", "take3.mp3"], ids=["as long", "longer"]
    )
    def test_reads_as_modified_until_undone(self, piece, tilia, takes, take):
        load_local_media((takes / take).as_posix())

        assert tilia.is_file_modified()
        commands.execute("edit.undo")
        assert Path(get(Get.MEDIA_PATH)) == takes / "take1.mp3"
        assert not tilia.is_file_modified()
        commands.execute("edit.redo")
        assert tilia.is_file_modified()

    def test_a_youtube_link_is_one_before_its_length_is_known(self, piece, tilia):
        def loads_it(player, url, **_):
            # What YouTube's player does at once: its length comes later, if at all.
            player.on_media_load_done(url, 0.0, 0.0)
            return True, player

        with patch("tilia.app.load_media", side_effect=loads_it):
            load_youtube_media(EXAMPLE_YOUTUBE_URL)

        assert get(Get.MEDIA_PATH) == EXAMPLE_YOUTUBE_URL
        assert tilia.is_file_modified()
        commands.execute("edit.undo")
        assert not tilia.is_file_modified()

    def test_an_undo_once_it_is_saved_is_a_change(self, piece, tilia, takes):
        load_local_media((takes / "take2.mp3").as_posix())
        commands.execute("file.save")
        assert not tilia.is_file_modified()

        commands.execute("edit.undo")

        assert tilia.is_file_modified()

    def test_an_undo_back_to_no_media_is_no_change(self, qtui, tilia, tls, takes):
        path = save_tilia_to_tmp_path(takes, "piece")
        commands.execute("file.open", path)
        load_local_media((takes / "take1.mp3").as_posix())
        assert tilia.is_file_modified()

        commands.execute("edit.undo")

        assert get(Get.MEDIA_PATH) == ""
        assert not tilia.is_file_modified()

    @pytest.mark.parametrize("spelt", [Path.as_posix, str], ids=["posix", "system"])
    def test_the_same_media_again_is_no_change(self, piece, tilia, takes, spelt):
        load_local_media(spelt(takes / "take1.mp3"))

        assert not tilia.is_file_modified()

    @pytest.mark.parametrize("spelt", [Path.as_posix, str], ids=["posix", "system"])
    def test_saved_it_is_no_change(self, piece, tilia, takes, spelt):
        load_local_media(spelt(takes / "take2.mp3"))

        commands.execute("file.save")

        assert not tilia.is_file_modified()

    def test_needs_an_autosave(self, piece, tilia, takes):
        with patch.object(autosave.settings, "get", return_value=0):
            # No thread: nothing is autosaved here.
            saver = autosave.AutoSaver(tilia.get_app_state)
        saver._last_autosave_data = tilia.get_app_state()
        assert not saver.needs_auto_save()

        load_local_media((takes / "take2.mp3").as_posix())

        assert saver.needs_auto_save()
