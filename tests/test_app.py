from unittest.mock import Mock, patch

import pytest
from tests.mock import PatchPost

from tilia.app import App
from tilia.file.media_metadata import MediaMetadata
from tilia.file.tilia_file import TiliaFile
from tilia.requests import stop_serving_all, stop_listening_to_all
from tilia.requests.post import Post


@pytest.fixture
def app():
    _app = App(
        file_manager=Mock(),
        clipboard=Mock(),
        undo_manager=Mock(),
    )
    _app.player = Mock()
    yield _app
    stop_listening_to_all(_app)
    stop_serving_all(_app)

    stop_listening_to_all(_app.timelines)
    stop_serving_all(_app.timelines)


class TestApp:
    def test_constructor(self, app):
        pass

    def test_get_id(self, app):
        assert app.get_id() == 0

    def test_on_request_to_close_no_changes(self, app):
        app.file_manager.ask_save_changes_if_modified.return_value = (True, False)

        with pytest.raises(SystemExit):
            app.on_close()

        # noinspection PyUnresolvedReferences
        app.file_manager.on_save_request.assert_not_called()

    def test_on_request_to_close_changes_user_accepts_save(self, app):
        app.file_manager.ask_save_changes_if_modified.return_value = (True, True)

        with pytest.raises(SystemExit):
            app.on_close()

    def test_on_request_to_close_changes_user_cancels(self, app):
        app.file_manager.ask_save_changes_if_modified.return_value = (False, True)
        app.on_close()  # should not raise SystemExit

    def test_on_request_to_load_media(self, app):
        path = "media.ogg"
        with (
            patch("tilia.app.MediaLoader") as media_loader_mock,
            PatchPost('tilia.app', Post.PLAYER_DURATION_CHANGED)
        ):
            app.load_media(path)

        media_loader_mock().load.assert_called_with(path)


class TestFileLoad:
    def test_media_path_does_not_exist_and_media_length_available(self, app):
        metadata = MediaMetadata()
        metadata["media length"] = 101
        file = TiliaFile(
            media_path="non-existent.ogg",
            media_metadata=metadata,
        )
        with (
            patch('tilia.app.App.reset_undo_manager') as reset_undo_manager_mock,
            PatchPost('tilia.app', Post.PLAYER_URL_CHANGED) as patch_post
        ):
            app.on_file_load(file)

        reset_undo_manager_mock.assert_called_once()
        patch_post.assert_called_with(Post.PLAYER_URL_CHANGED, '')
        app.player.duration = 101

    def test_media_path_does_not_exist_and_media_length_not_available(self, app):
        metadata = MediaMetadata()
        file = TiliaFile(
            media_path="non-existent.ogg",
            media_metadata=metadata,
        )
        with (
            patch('tilia.app.App.reset_undo_manager') as reset_undo_manager_mock,
            PatchPost('tilia.app', Post.PLAYER_URL_CHANGED) as patch_post
        ):
            app.on_file_load(file)

        reset_undo_manager_mock.assert_called_once()
        patch_post.assert_called_with(Post.PLAYER_URL_CHANGED, '')
        app.player.duration.assert_not_called()

    def test_media_path_exists(self, app, tmp_path):
        metadata = MediaMetadata()
        (tmp_path / 'media.ogg').touch()
        path = str((tmp_path / 'media.ogg').resolve())
        file = TiliaFile(
            media_path=path,
            media_metadata=metadata,
        )
        with (
            patch('tilia.app.App.load_media') as load_media_mock,
            patch('tilia.app.App.reset_undo_manager') as reset_undo_manager_mock,
        ):
            app.on_file_load(file)

        load_media_mock.assert_called_with(path)
        reset_undo_manager_mock.assert_called_once()
