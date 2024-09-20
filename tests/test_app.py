import json
from pathlib import Path
from unittest.mock import patch


import tests.utils
from tests.mock import Serve, PatchPost

from tilia.requests import Get, Post, post
from tilia.ui.actions import TiliaAction
from tilia.timelines.timeline_kinds import TimelineKind


class TestSaveFileOnClose:
    @staticmethod
    def _get_modified_file_state():
        return {
            "timelines": {},
            "media_path": "modified.ogg",
            "media_metadata": {},
            "file_path": "",
        }

    def test_no_changes(self, tilia, tls, actions):
        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
            patch("tilia.file.file_manager.FileManager.save") as save_mock,
            PatchPost('tilia.app', Post.UI_EXIT) as exit_mock,
        ):
            actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_called()
        save_mock.assert_not_called()

    def test_file_modified_and_user_chooses_to_save_changes(
        self, tilia, actions, tmp_path
    ):
        tmp_file = tmp_path / "test_file_modified_and_user_chooses_to_save_changes.tla"
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (tmp_file, True)),
            PatchPost('tilia.app', Post.UI_EXIT) as exit_mock,
        ):
            actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_called()
        assert tmp_file.exists()

    def test_file_modified_and_user_chooses_to_save_changes_when_file_was_previously_saved(
        self, tilia, actions, tmp_path
    ):
        tmp_file = tmp_path / "test_file_modified_and_user_chooses_to_save_changes.tla"
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (tmp_file, True)),
        ):
            actions.trigger(TiliaAction.FILE_SAVE)

        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            PatchPost('tilia.app', Post.UI_EXIT) as exit_mock,
        ):
            actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_called()
        assert tmp_file.exists()

    def test_file_is_modified_and_user_cancels_close_on_should_save_changes_dialog(
        self, tilia, actions
    ):
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (False, True)),
            patch("tilia.file.file_manager.FileManager.save") as save_mock,
            PatchPost('tilia.app', Post.UI_EXIT) as exit_mock,
        ):
            actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_not_called()
        save_mock.assert_not_called()

    def test_file_is_modified_and_user_cancels_file_save_dialog(self, tilia, actions):
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, ("", "")),
            patch("tilia.file.file_manager.FileManager.save") as save_mock,
            PatchPost('tilia.app', Post.UI_EXIT) as exit_mock,
        ):
            actions.trigger(TiliaAction.APP_CLOSE)

        exit_mock.assert_not_called()
        save_mock.assert_not_called()


class TestFileLoad:
    def test_media_path_does_not_exist_and_media_length_available(
        self, tilia, tilia_state, tmp_path, tls, actions
    ):
        file_data = tests.utils.get_blank_file_data()
        file_data["media_metadata"]["media length"] = 101
        file_data["media_path"] = "invalid.tla"
        tmp_file = tmp_path / "test_file_load.tla"
        tmp_file.write_text(json.dumps(file_data))
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == ""
        assert tilia_state.duration == 101

    def test_media_path_does_not_exist_and_media_length_not_available(
        self, tilia, tilia_state, tmp_path, tls, actions
    ):
        tilia_state.duration = 0
        file_data = tests.utils.get_blank_file_data()
        file_data["media_path"] = "invalid.tla"
        tmp_file = tmp_path / "test_file_load.tla"
        tmp_file.write_text(json.dumps(file_data))
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == ""
        assert tilia_state.duration == 0

    def test_media_path_exists(self, tilia, tilia_state, tmp_path, tls, actions):
        file_data = tests.utils.get_blank_file_data()
        tmp_file = tmp_path / "test_file_load.tla"
        media_path = str((Path(__file__).parent / "resources" / "example.ogg").resolve())
        file_data["media_path"] = media_path
        file_data["media_metadata"]["media length"] = 101
        tmp_file.write_text(json.dumps(file_data))
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == media_path
        assert tilia_state.duration == 101

    def test_media_path_is_youtube_url(self, tilia_state, tmp_path, actions):
        file_data = tests.utils.get_blank_file_data()
        tmp_file = tmp_path / "test_file_load.tla"
        media_path = "https://www.youtube.com/watch?v=wBfVsucRe1w"
        file_data["media_path"] = media_path
        file_data["media_metadata"]["media length"] = 101
        tmp_file.write_text(json.dumps(file_data))
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == media_path
        assert tilia_state.duration == 101


class TestMediaLoad:
    EXAMPLE_PATH_OGG = "tilia/tests/resources/example.ogg"

    @staticmethod
    def _load_media(path):
        post(Post.APP_MEDIA_LOAD, path)

    def test_load_local(self, tilia, tilia_state):
        self._load_media(self.EXAMPLE_PATH_OGG)
        assert tilia_state.media_path == self.EXAMPLE_PATH_OGG

    def test_undo(self, tilia, tilia_state, actions):
        self._load_media(self.EXAMPLE_PATH_OGG)
        actions.trigger(TiliaAction.EDIT_UNDO)
        assert not tilia_state.media_path

    def test_redo(self, tilia, tilia_state, actions):
        self._load_media(self.EXAMPLE_PATH_OGG)
        actions.trigger(TiliaAction.EDIT_UNDO)
        actions.trigger(TiliaAction.EDIT_REDO)
        assert tilia_state.media_path == self.EXAMPLE_PATH_OGG

    def test_load_invalid_extension(self, tilia, tilia_state, tilia_errors):
        self._load_media("invalid.xyz")
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("xyz")
        assert not tilia_state.media_path

    def test_load_invalid_extension_with_media_loaded(
        self, tilia, tilia_state, tilia_errors
    ):
        self._load_media(self.EXAMPLE_PATH_OGG)
        self._load_media("invalid.xyz")
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("xyz")
        assert tilia_state.media_path == self.EXAMPLE_PATH_OGG

    def test_load_media_after_loading_media_with_invalid_extension(
        self, tilia, tilia_state, tilia_errors
    ):
        self._load_media("invalid.xyz")
        self._load_media(self.EXAMPLE_PATH_OGG)
        assert tilia_state.media_path == self.EXAMPLE_PATH_OGG


class TestFileSetup:
    def test_slider_timeline_is_created_when_loaded_file_does_not_have_one(self, tls, tmp_path, actions):
        file_data = tests.utils.get_blank_file_data()
        file_data['timelines'] = {'1': {
            'name': '',
            'height': 40,
            'is_visible': True,
            'ordinal': 1,
            'components': {},
            'kind': 'HIERARCHY_TIMELINE'
        }}  # empty hierarchy timeline
        tmp_file = tmp_path / "test_file_setup.tla"
        tmp_file.write_text(json.dumps(file_data))
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            actions.trigger(TiliaAction.FILE_OPEN)
            
        assert len(tls) == 2
        assert TimelineKind.SLIDER_TIMELINE in tls.timeline_kinds