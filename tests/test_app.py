import json
from pathlib import Path
from unittest.mock import patch


import tests.utils
from tests.mock import PatchGet

from tilia.requests import Get
from tilia.ui import actions
from tilia.ui.actions import TiliaAction


class TestSaveFileOnClose:
    def test_no_changes(self, app, actions):
        app.file_manager.ask_save_changes_if_modified.return_value = (True, False)

        with patch('sys.exit') as exit_mock:
            actions.trigger(TiliaAction.UI_CLOSE)

        exit_mock.assert_called()
        actions.assert_not_triggered(TiliaAction.FILE_SAVE)

    def test_user_accepts_save(self, app, actions):
        app.file_manager.ask_save_changes_if_modified.return_value = (True, True)

        with patch('sys.exit') as exit_mock:
            actions.trigger(TiliaAction.UI_CLOSE)

        exit_mock.assert_called()
        actions.assert_triggered(TiliaAction.FILE_SAVE)

    def test_user_cancels_dialog(self, app, actions):
        app.file_manager.ask_save_changes_if_modified.return_value = (False, True)
        with patch('sys.exit') as exit_mock:
            actions.trigger(TiliaAction.UI_CLOSE)

        exit_mock.assert_not_called()
        actions.assert_not_triggered(TiliaAction.FILE_SAVE)


class TestFileLoad:
    def test_media_path_does_not_exist_and_media_length_available(self, tilia, tilia_state, tmp_path):
        file_data = tests.utils.get_blank_file_data()
        file_data['media_metadata']['media length'] = 101
        file_data['media_path'] = 'invalid.tla'
        tmp_file = tmp_path / 'test_file_load.tla'
        tmp_file.write_text(json.dumps(file_data))
        with PatchGet('tilia.file.file_manager', Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == ''
        assert tilia_state.duration == 101

    def test_media_path_does_not_exist_and_media_length_not_available(self, tilia, tilia_state, tmp_path):
        file_data = tests.utils.get_blank_file_data()
        file_data['media_path'] = 'invalid.tla'
        tmp_file = tmp_path / 'test_file_load.tla'
        tmp_file.write_text(json.dumps(file_data))
        with PatchGet('tilia.file.file_manager', Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == ''
        assert tilia_state.duration == 0

    def test_media_path_exists(self, tilia, tilia_state, tmp_path):
        file_data = tests.utils.get_blank_file_data()
        tmp_file = tmp_path / 'test_file_load.tla'
        media_path = str(Path('resources', 'example.ogg').resolve())
        file_data['media_path'] = media_path
        tmp_file.write_text(json.dumps(file_data))
        with PatchGet('tilia.file.file_manager', Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            actions.trigger(TiliaAction.FILE_OPEN)

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == media_path
