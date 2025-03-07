import json
import tilia.log
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest

import tests.utils
from tests.constants import EXAMPLE_MEDIA_PATH, EXAMPLE_OGG_DURATION
from tests.mock import Serve, PatchPost, patch_file_dialog, patch_yes_or_no_dialog
from tilia.media.player import YouTubePlayer, QtAudioPlayer
from tilia.settings import settings

from tilia.requests import Get, Post, post, get
from tilia.ui.actions import TiliaAction
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.windows import WindowKind


class TestLogger:
    def test_sentry_not_logging(self):
        # TODO: make this test run first in batch testing.
        # enabling sentry during tests will fill inbox up unneccesarily
        assert "tilia.log" in tilia.log.sentry_sdk.integrations.logging._IGNORED_LOGGERS


class TestSaveFileOnClose:
    @staticmethod
    def _get_modified_file_state():
        return {
            "timelines": {},
            "media_path": "modified.ogg",
            "media_metadata": {},
            "file_path": "",
        }

    def test_no_changes(self, user_actions):
        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
            patch("tilia.file.file_manager.FileManager.save") as save_mock,
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            user_actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_called()
        save_mock.assert_not_called()

    def test_file_modified_and_user_chooses_to_save_changes(
        self, user_actions, tmp_path
    ):
        tmp_file = tmp_path / "test_file_modified_and_user_chooses_to_save_changes.tla"
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, tmp_file)),
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            user_actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_called()
        assert tmp_file.exists()

    def test_file_modified_and_user_chooses_to_save_changes_when_file_was_previously_saved(
        self, user_actions, tmp_path
    ):
        tmp_file = tmp_path / "test_file_modified_and_user_chooses_to_save_changes.tla"
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, tmp_file)),
        ):
            user_actions.trigger(TiliaAction.FILE_SAVE)

        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            user_actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_called()
        assert tmp_file.exists()

    def test_file_is_modified_and_user_cancels_close_on_should_save_changes_dialog(
        self, user_actions
    ):
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (False, True)),
            patch("tilia.file.file_manager.FileManager.save") as save_mock,
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            user_actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_not_called()
        save_mock.assert_not_called()

    def test_file_is_modified_and_user_cancels_file_save_dialog(self, user_actions):
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (False, "")),
            patch("tilia.file.file_manager.FileManager.save") as save_mock,
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            user_actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_not_called()
        save_mock.assert_not_called()


class TestFileLoad:
    def test_media_path_does_not_exist_and_media_length_available(
        self, tilia_state, qtui, tmp_path, user_actions
    ):
        tilia_state.duration = 101

        # set media path to a non-existing file
        nonexisting_media = tmp_path / "nothere.mp3"
        with patch_file_dialog(True, [str(nonexisting_media)]):
            user_actions.trigger(TiliaAction.MEDIA_LOAD_LOCAL)

        # save tilia file
        tla_path = tmp_path / "test.tla"
        with patch_file_dialog(True, [str(tla_path)]):
            user_actions.trigger(TiliaAction.FILE_SAVE_AS)

        # open tilia file
        with (
            patch_file_dialog(True, [str(tla_path)]),
            patch_yes_or_no_dialog(False),
        ):
            user_actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == ""
        assert tilia_state.duration == 101

    def test_media_path_does_not_exist_and_media_length_not_available(
        self, qtui, tilia_state, tmp_path, user_actions
    ):
        tilia_state.duration = 0
        file_data = tests.utils.get_blank_file_data()
        file_data["media_path"] = "invalid.tla"
        tmp_file = tmp_path / "test_file_load.tla"
        tmp_file.write_text(json.dumps(file_data))
        with (
            patch_file_dialog(True, [str(tmp_file)]),
            patch_yes_or_no_dialog(False),  # do no try to load another media
        ):
            user_actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == ""
        assert tilia_state.duration == 0

    def test_media_path_exists(
        self, tilia, qtui, tilia_state, tmp_path, tls, user_actions
    ):
        tmp_file = tmp_path / "test_file_load.tla"
        with patch_file_dialog(True, [EXAMPLE_MEDIA_PATH]):
            user_actions.trigger(TiliaAction.MEDIA_LOAD_LOCAL)

        with patch_file_dialog(True, [str(tmp_file)]):
            user_actions.trigger(TiliaAction.FILE_SAVE_AS)
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            user_actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == EXAMPLE_MEDIA_PATH
        assert tilia_state.duration == EXAMPLE_OGG_DURATION

    def test_media_path_is_youtube_url(self, tilia_state, tmp_path, user_actions):
        file_data = tests.utils.get_blank_file_data()
        tmp_file = tmp_path / "test_file_load.tla"
        media_path = "https://www.youtube.com/watch?v=wBfVsucRe1w"
        file_data["media_path"] = media_path
        file_data["media_metadata"]["media length"] = 101
        tmp_file.write_text(json.dumps(file_data))
        with (
            Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)),
            Serve(Get.PLAYER_CLASS, YouTubePlayer),
        ):
            user_actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == media_path
        assert tilia_state.duration == 101


class TestMediaLoad:
    EXAMPLE_PATH_OGG = str(
        (Path(__file__).parent / "resources" / "example.ogg").resolve()
    ).replace("\\", "/")
    EXAMPLE_OGG_DURATION = 9.952

    @staticmethod
    def _load_media(path, scale_timelines: Literal["yes", "no", "prompt"] = "prompt"):
        with Serve(Get.PLAYER_CLASS, QtAudioPlayer):
            post(Post.APP_MEDIA_LOAD, path, scale_timelines=scale_timelines)

    def test_load_local(self, tilia_state):
        self._load_media(self.EXAMPLE_PATH_OGG)
        assert tilia_state.media_path == self.EXAMPLE_PATH_OGG
        assert tilia_state.duration == self.EXAMPLE_OGG_DURATION

    def test_undo(self, tilia_state, user_actions):
        self._load_media(self.EXAMPLE_PATH_OGG)
        user_actions.trigger(TiliaAction.EDIT_UNDO)
        assert not tilia_state.media_path

    def test_redo(self, tilia_state, user_actions):
        self._load_media(self.EXAMPLE_PATH_OGG)
        user_actions.trigger(TiliaAction.EDIT_UNDO)
        user_actions.trigger(TiliaAction.EDIT_REDO)
        assert tilia_state.media_path == self.EXAMPLE_PATH_OGG

    def test_load_invalid_extension(self, tilia_state, tilia_errors):
        self._load_media("invalid.xyz")
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("xyz")
        assert not tilia_state.media_path

    def test_load_invalid_extension_with_media_loaded(self, tilia_state, tilia_errors):
        self._load_media(self.EXAMPLE_PATH_OGG)
        self._load_media("invalid.xyz")
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("xyz")
        assert tilia_state.media_path == self.EXAMPLE_PATH_OGG

    def test_load_media_after_loading_media_with_invalid_extension(self, tilia_state):
        self._load_media("invalid.xyz")
        self._load_media(self.EXAMPLE_PATH_OGG)
        assert tilia_state.media_path == self.EXAMPLE_PATH_OGG

    def test_scale_timelines_is_no(self, marker_tl):
        marker_tl.create_marker(5)
        marker_tl.create_marker(10)
        self._load_media(self.EXAMPLE_PATH_OGG, "no")
        assert len(marker_tl) == 1
        assert marker_tl[0].get_data("time") == 5

    def test_scale_timelines_is_yes(self, tilia_state, marker_tl):
        prev_duration = tilia_state.duration
        marker_tl.create_marker(50)
        self._load_media(self.EXAMPLE_PATH_OGG, "yes")
        assert (
            marker_tl[0].get_data("time")
            == 50 * self.EXAMPLE_OGG_DURATION / prev_duration
        )


class TestScaleCropTimeline:
    @pytest.mark.parametrize(
        "scale_timelines,scale_factor",
        [
            (("yes", "yes"), (2, 2)),
            (("yes", "no"), (2, 2)),
            (("no", "yes"), (2, 2)),
            (("no", "no"), (2, 2)),
        ],
    )
    def test_set_duration_twice_without_cropping(
        self, scale_timelines, scale_factor, tilia_state, marker_tlui, user_actions
    ):
        marker_time = 50
        tilia_state.current_time = marker_time
        user_actions.trigger(TiliaAction.MARKER_ADD)
        displacement_factor = 1
        for factor, should_scale in zip(scale_factor, scale_timelines, strict=True):
            tilia_state.set_duration(
                tilia_state.duration * factor, scale_timelines=should_scale
            )
            if should_scale == "yes":
                displacement_factor *= factor
        assert marker_tlui[0].get_data("time") == marker_time * displacement_factor

    def test_scale_then_crop(self, marker_tl, tilia_state, user_actions):
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.MARKER_ADD)
        tilia_state.current_time = 50
        user_actions.trigger(TiliaAction.MARKER_ADD)
        tilia_state.set_duration(200, scale_timelines="yes")
        tilia_state.set_duration(50, scale_timelines="no")
        assert len(marker_tl) == 1
        assert marker_tl[0].get_data("time") == 20

    def test_crop_then_scale(self, marker_tl, tilia_state, user_actions):
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.MARKER_ADD)
        tilia_state.current_time = 50
        user_actions.trigger(TiliaAction.MARKER_ADD)
        tilia_state.set_duration(40, scale_timelines="no")
        tilia_state.set_duration(80, scale_timelines="yes")
        assert len(marker_tl) == 1
        assert marker_tl[0].get_data("time") == 20

    def test_crop_twice(self, marker_tlui, tilia_state, user_actions):
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.MARKER_ADD)
        tilia_state.current_time = 50
        user_actions.trigger(TiliaAction.MARKER_ADD)
        tilia_state.set_duration(80, scale_timelines="no")
        tilia_state.set_duration(40, scale_timelines="no")
        assert len(marker_tlui) == 1
        assert marker_tlui[0].get_data("time") == 10


class TestFileSetup:
    def test_slider_timeline_is_created_when_loaded_file_does_not_have_one(
        self, tls, tmp_path, user_actions
    ):
        file_data = tests.utils.get_blank_file_data()
        file_data["timelines"] = {
            "1": {
                "name": "",
                "height": 40,
                "is_visible": True,
                "ordinal": 1,
                "components": {},
                "kind": "HIERARCHY_TIMELINE",
            }
        }  # empty hierarchy timeline
        tmp_file = tmp_path / "test_file_setup.tla"
        tmp_file.write_text(json.dumps(file_data))
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            user_actions.trigger(TiliaAction.FILE_OPEN)

        assert len(tls) == 2
        assert TimelineKind.SLIDER_TIMELINE in tls.timeline_kinds


def assert_open_failed(tilia, tilia_errors, opened_file_path, prev_file):
    tilia_errors.assert_error()
    assert settings.get_recent_files()[0] != opened_file_path
    assert tilia.file_manager.file == prev_file


class TestOpen:
    def test_open_with_timeline(self, tilia, tls, tmp_path, user_actions):
        tl_data = tests.utils.get_dummy_timeline_data()
        tl_id = list(tl_data.keys())[0]

        for i, (start, end, level) in enumerate([(0, 1, 1), (1, 2, 1), (2, 3, 2)]):
            tl_data[tl_id]["components"][i] = {
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
        file_data["timelines"] = tl_data
        file_data["media_metadata"]["media length"] = 100

        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text(json.dumps(file_data, indent=2))
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            user_actions.trigger(TiliaAction.FILE_OPEN)

        assert Path(settings.get_recent_files()[0]) == tmp_file
        assert len(tls) == 2  # Slider timeline is also created by default
        assert len(tls[0]) == 3

    def test_open_with_path(self, tilia, tls, tmp_path):
        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)
        post(Post.FILE_OPEN, tmp_file)

        assert Path(settings.get_recent_files()[0]) == tmp_file
        assert len(tls) == 2  # Slider timeline is also created by default

    def test_open_file_does_not_exist(self, tilia, tmp_path, tilia_errors):
        prev_file = tilia.file_manager.file
        tmp_file = tmp_path / "test.tla"
        post(Post.FILE_OPEN, tmp_file)

        assert_open_failed(tilia, tilia_errors, tmp_file, prev_file)

    def test_open_file_is_not_valid_json(self, tilia, tmp_path, tilia_errors):
        prev_file = tilia.file_manager.file
        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text("{")
        post(Post.FILE_OPEN, tmp_file)

        assert_open_failed(tilia, tilia_errors, tmp_file, prev_file)

    def test_open_file_is_not_valid_tla(self, tilia, tmp_path, tilia_errors):
        prev_file = tilia.file_manager.file
        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text('{"a": 1, "b": 2}')
        post(Post.FILE_OPEN, tmp_file)

        assert_open_failed(tilia, tilia_errors, tmp_file, prev_file)

    def test_open_file_with_bad_timeline_data(self, tilia, tmp_path, tilia_errors):
        prev_file = tilia.file_manager.file
        tmp_file = tmp_path / "test.tla"
        file_data = tests.utils.get_blank_file_data()
        file_data["timelines"] = {"nonsense": 404}
        tmp_file.write_text(json.dumps(file_data))
        post(Post.FILE_OPEN, tmp_file)

        assert_open_failed(tilia, tilia_errors, tmp_file, prev_file)

    def test_file_not_modified_after_open(self, tilia, tmp_path):
        file_data = tests.utils.get_blank_file_data()
        tl_data = tests.utils.get_dummy_timeline_data()
        file_data["timelines"] = tl_data
        file_path = tmp_path / "test.tla"
        file_path.write_text(json.dumps(file_data))

        tilia.on_clear()
        post(Post.FILE_OPEN, file_path)
        assert not tilia.file_manager.is_file_modified(tilia.file_manager.file.__dict__)

    def test_open_file_with_custom_metadata_fields(self, tilia, tmp_path):
        file_data = """{
  "file_path": "C:/Programa\u00e7\u00e3o/TiLiA/tests/test_metadata_custom_fields.tla",
  "media_path": "",
  "media_metadata": {
    "test_field1": "a",
    "test_field2": "b",
    "test_field3": "c"

  },
  "timelines": {
    "0": {
      "is_visible": true,
      "ordinal": 0,
      "height": 25,
      "kind": "SLIDER_TIMELINE",
      "components": {}
    }
  },
  "app_name": "TiLiA",
  "version": "0.0.1"
}"""

        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text(file_data, encoding="utf-8")
        post(Post.FILE_OPEN, tmp_file)

        assert list(tilia.file_manager.file.media_metadata.items()) == [
            ("test_field1", "a"),
            ("test_field2", "b"),
            ("test_field3", "c"),
        ]

    def test_open_saving_changes(self, tilia, tls, marker_tlui, user_actions, tmp_path):
        previous_path = tmp_path / "previous.tla"
        with Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, previous_path)):
            post(Post.FILE_SAVE)

        # make change

        user_actions.trigger(TiliaAction.MARKER_ADD)
        prev_tl_id = marker_tlui.id
        prev_marker_id = marker_tlui[0].id

        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)):
            post(Post.FILE_OPEN, tmp_file)

        with open(previous_path, "r", encoding="utf-8") as f:
            contents = json.load(f)  # read contents

        assert len(tls) == 2  # assert load was successful
        assert (
            contents["timelines"][str(prev_tl_id)]["components"][str(prev_marker_id)][
                "time"
            ]
            == 0
        )

    def test_open_without_saving_changes(self, tilia, tls, marker_tlui, tmp_path):
        previous_path = tmp_path / "previous.tla"
        with Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, previous_path)):
            post(Post.FILE_SAVE)

        # make change
        marker_tlui.create_marker(10)
        prev_tl_id = marker_tlui.id

        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)):
            post(Post.FILE_OPEN, tmp_file)

        with open(previous_path, "r", encoding="utf-8") as f:
            contents = json.load(f)  # read contents

        assert len(tls) == 2  # assert load was successful
        assert len(list(contents["timelines"][str(prev_tl_id)]["components"])) == 0

    def test_open_canceling_should_save_changes_dialog(
        self, tilia, tls, marker_tlui, tmp_path
    ):
        previous_path = tmp_path / "previous.tla"
        with Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, previous_path)):
            post(Post.FILE_SAVE)

        # make change
        marker_tlui.create_marker(10)

        prev_state = tilia.get_app_state()

        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (False, True)):
            post(Post.FILE_OPEN, tmp_file)

        assert len(tls) == 1  # assert file wasn't opened
        assert tilia.get_app_state() == prev_state

    def test_open_then_save(self, tmp_path, tilia_errors):
        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)
        post(Post.FILE_OPEN, tmp_file)
        post(Post.FILE_SAVE)
        tilia_errors.assert_no_error()


class TestUndoRedo:
    def test_undo_fails(
        self, tilia, qtui, user_actions, tluis, tilia_state, tilia_errors
    ):
        with Serve(Get.FROM_USER_STRING, (True, "test")):
            user_actions.trigger(TiliaAction.TIMELINES_ADD_MARKER_TIMELINE)

        # this will record an invalid state that will raise an exception when
        # we try to restore it
        with patch.object(tilia, "get_app_state", return_value={}):
            user_actions.trigger(TiliaAction.MARKER_ADD)

        # doing another action so the following redo
        # will try to restore the previous, faulty state
        # Note: this could be improved by providing a state that is actually
        # similar to a healthy state
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.MARKER_ADD)

        user_actions.trigger(TiliaAction.EDIT_UNDO)

        # as the undo failed, the current state (with both markers)
        # should be recovered
        assert len(tluis[0]) == 2
        tilia_errors.assert_error()

    def test_redo_fails(
        self, tilia, qtui, user_actions, tluis, tilia_state, tilia_errors
    ):
        with Serve(Get.FROM_USER_STRING, (True, "test")):
            user_actions.trigger(TiliaAction.TIMELINES_ADD_MARKER_TIMELINE)

        # this will record an invalid state that will raise an exception when
        # we try to restore it
        # Note: this could be improved by providing a state that is actually
        # similar to a healthy state
        with patch.object(tilia, "get_app_state", return_value={}):
            user_actions.trigger(TiliaAction.MARKER_ADD)

        # going back to previous state
        user_actions.trigger(TiliaAction.EDIT_UNDO)

        # restoring state (this will fail)
        user_actions.trigger(TiliaAction.EDIT_REDO)

        # as the redo failed, the current state (with no markers)
        # should be recovered
        assert tluis[0].is_empty
        tilia_errors.assert_error()


class TestFileNew:
    def test_media_is_unloaded(self, tilia, qtui, user_actions):
        with Serve(Get.FROM_USER_MEDIA_PATH, (True, EXAMPLE_MEDIA_PATH)):
            user_actions.trigger(TiliaAction.MEDIA_LOAD_LOCAL)

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)):
            user_actions.trigger(TiliaAction.FILE_NEW)

        assert get(Get.MEDIA_DURATION) == 0
        assert not tilia.player.media_path

    def test_all_windows_are_closed(self, tilia, qtui, user_actions):
        for kind in WindowKind:
            post(Post.WINDOW_OPEN, kind)

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)):
            user_actions.trigger(TiliaAction.FILE_NEW)

        # this doesn't actaully check if windows are closed
        # it checks if app._windows[kind] is None.
        # Those should be equivalent, if everything is working as it should
        assert not any(qtui.is_window_open(k) for k in WindowKind)


class TestRelativePaths:
    def test_path_exists(self, tmp_path):
        existing_path = tmp_path / "previous.file"
        existing_path.mkdir()
        assert get(Get.VERIFIED_PATH, str(existing_path)) == str(existing_path)

    def test_path_nonexistent(self, tilia, tmp_path):
        tilia.old_file_path = Path()
        tilia.cur_file_path = tmp_path
        not_a_path = tmp_path / "nonexistent.file"
        assert get(Get.VERIFIED_PATH, str(not_a_path)) == ""

    @pytest.mark.parametrize(
        "tla,media",
        [
            ("tilia.tla", "music.mp3"),
            ("folderName/tilia.tla", "folderName/music.mp3"),
            ("folderName/files/tilia.tla", "folderName/media/music.mp3"),
        ],
    )
    def test_moving_files(self, tla, media, tilia, qtui, tmp_path, user_actions):
        # create tla and media in old folder
        old_folder = tmp_path / "old" / "folder"
        old_tla = old_folder / tla
        old_tla.parent.mkdir(parents=True, exist_ok=True)
        old_media = old_folder / media
        old_media.parent.mkdir(parents=True, exist_ok=True)
        old_media.write_bytes(
            Path(EXAMPLE_MEDIA_PATH).read_bytes()
        )  # copy example media

        # load media
        with patch_file_dialog(True, [str(old_media.resolve())]):
            user_actions.trigger(TiliaAction.MEDIA_LOAD_LOCAL)

        # save tla
        with patch_file_dialog(True, [str(old_tla.resolve())]):
            user_actions.trigger(TiliaAction.FILE_SAVE_AS)

        # move tla and media to new folder
        new_folder = tmp_path / "the" / "new" / "one"
        (new_folder / tla).parent.mkdir(parents=True, exist_ok=True)
        (new_folder / media).parent.mkdir(parents=True, exist_ok=True)
        new_tla = old_tla.rename(new_folder / tla)
        new_media = old_media.rename(new_folder / media)

        # open file at new folder
        with (patch_file_dialog(True, [str(new_tla)])):
            user_actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia.player.media_path == str(new_media)
