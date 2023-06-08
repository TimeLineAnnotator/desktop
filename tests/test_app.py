from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tilia.app import App
from tilia.exceptions import UserCancel
from tilia.requests import stop_serving_all, stop_listening_to_all


class TestApp:

    @pytest.fixture
    def app(self):
        _app = App(
            player=Mock(),
            file_manager=Mock(),
            clipboard=Mock(),
            undo_manager=Mock(),
        )
        yield _app
        stop_listening_to_all(_app)
        stop_serving_all(_app)

        stop_listening_to_all(_app.timeline_collection)
        stop_serving_all(_app.timeline_collection)

    def test_constructor(self):
        app = App(
            player=Mock(),
            file_manager=Mock(),
            clipboard=Mock(),
            undo_manager=Mock(),
        )

        # cleanup
        stop_listening_to_all(app)
        stop_serving_all(app)

        stop_listening_to_all(app.timeline_collection)
        stop_serving_all(app.timeline_collection)

    def test_get_id(self, app):
        assert app.get_id() == '0'

    def test_on_request_to_close_no_changes(self, app):
        app.file_manager.ask_save_changes_if_modified.return_value = False

        with patch('tilia.dirs.delete_temp_dir') as delete_temp_dir_mock:
            with pytest.raises(SystemExit):
                app.on_request_to_close()

            delete_temp_dir_mock.assert_called_once()
            app.file_manager.on_save_request.assert_not_called()

    def test_on_request_to_close_changes_user_accepts_save(self, app):
        app.file_manager.ask_save_changes_if_modified.return_value = True

        with patch('tilia.dirs.delete_temp_dir'):
            with pytest.raises(SystemExit):
                app.on_request_to_close()

    def test_on_request_to_close_changes_user_cancels(self, app):
        def raise_user_cancel():
            raise UserCancel

        app.file_manager.ask_save_changes_if_modified = raise_user_cancel

        assert app.on_request_to_close() is None  # should not raise SystemExit

    def test_on_request_to_load_media(self, app):
        path = 'media.ogg'
        with patch('tilia.app.MediaLoader') as media_loader_mock:
            app.on_request_to_load_media(path)

            media_loader_mock().load.assert_called_with(Path(path))
            app.file_manager.set_media_path.assert_called_with(path)
