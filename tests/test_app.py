from unittest.mock import Mock, patch

import pytest
from tests.mock import PatchPost

from tilia.app import App
from tilia.file.media_metadata import MediaMetadata
from tilia.file.tilia_file import TiliaFile
from tilia.requests import stop_serving_all, stop_listening_to_all, get, Get
from tilia.requests.post import Post
from tilia.ui.actions import TiliaAction


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


class TestApp:
    def test_constructor(self, app):
        pass

    def test_get_id(self, app):
        assert get(Get.ID) == 0
        assert get(Get.ID) == 1
        assert get(Get.ID) == 2



    def test_on_request_to_load_media(self, app):
        path = "media.ogg"
        with (
            patch("tilia.app.MediaLoader") as media_loader_mock,
            PatchPost("tilia.app", Post.PLAYER_DURATION_CHANGED),
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
            patch("tilia.app.App.reset_undo_manager") as reset_undo_manager_mock,
            PatchPost("tilia.app", Post.PLAYER_URL_CHANGED) as patch_post,
        ):
            app.on_file_load(file)

        reset_undo_manager_mock.assert_called_once()
        patch_post.assert_called_with(Post.PLAYER_URL_CHANGED, "")
        app.player.duration = 101

    def test_media_path_does_not_exist_and_media_length_not_available(self, app):
        metadata = MediaMetadata()
        file = TiliaFile(
            media_path="non-existent.ogg",
            media_metadata=metadata,
        )
        with (
            patch("tilia.app.App.reset_undo_manager") as reset_undo_manager_mock,
            PatchPost("tilia.app", Post.PLAYER_URL_CHANGED) as patch_post,
        ):
            app.on_file_load(file)

        reset_undo_manager_mock.assert_called_once()
        patch_post.assert_called_with(Post.PLAYER_URL_CHANGED, "")
        app.player.duration.assert_not_called()

    def test_media_path_exists(self, app, tmp_path):
        metadata = MediaMetadata()
        (tmp_path / "media.ogg").touch()
        path = str((tmp_path / "media.ogg").resolve())
        file = TiliaFile(
            media_path=path,
            media_metadata=metadata,
        )
        with (
            patch("tilia.app.App.load_media") as load_media_mock,
            patch("tilia.app.App.reset_undo_manager") as reset_undo_manager_mock,
        ):
            app.on_file_load(file)

        load_media_mock.assert_called_with(path)
        reset_undo_manager_mock.assert_called_once()
