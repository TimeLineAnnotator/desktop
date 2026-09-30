from unittest.mock import patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from tests.mock import PatchPost, Serve
from tests.utils import save_tilia_to_tmp_path
from tilia.media.player.base import MediaTimeChangeReason
from tilia.requests import Get, Post, post
from tilia.ui import commands
from tilia.ui.format import format_media_time, parse_media_time
from tilia.ui.player import PlayerStatus, PlayerToolbarElement


class TestPlayToggle:
    def test_trigger_posts_toggle_play_pause(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        with patch.object(commands, "execute") as mock:
            qtui.player_toolbar.play_toggle_action.trigger()
        mock.assert_called_once_with("media.toggle_play", True)

    def test_ui_update_checks(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_PLAY_PAUSE, True)
        assert qtui.player_toolbar.play_toggle_action.isChecked()

    def test_ui_update_unchecks(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_PLAY_PAUSE, True)
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_PLAY_PAUSE, False)
        assert not qtui.player_toolbar.play_toggle_action.isChecked()

    def test_ui_update_ignored_when_not_player_enabled(self, qtui):
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_PLAY_PAUSE, True)
        assert not qtui.player_toolbar.play_toggle_action.isChecked()


class TestLoopToggle:
    def test_trigger_posts_toggle_loop(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        with PatchPost("tilia.ui.player", Post.PLAYER_TOGGLE_LOOP) as mock:
            qtui.player_toolbar.loop_toggle_action.trigger()
        mock.assert_called_once()

    def test_ui_update_checks(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_LOOP, True)
        assert qtui.player_toolbar.loop_toggle_action.isChecked()

    def test_ui_update_unchecks(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_LOOP, True)
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_LOOP, False)
        assert not qtui.player_toolbar.loop_toggle_action.isChecked()


class TestVolume:
    def test_toggle_posts_volume_mute(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        with patch.object(commands, "execute") as mock:
            qtui.player_toolbar.volume_toggle_action.trigger()
        mock.assert_called_once_with("media.volume.mute", True)

    def test_toggle_disables_slider(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        qtui.player_toolbar.volume_toggle_action.trigger()
        assert not qtui.player_toolbar.volume_slider.isEnabled()

    def test_untoggle_re_enables_slider(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        qtui.player_toolbar.volume_toggle_action.trigger()
        qtui.player_toolbar.volume_toggle_action.trigger()
        assert qtui.player_toolbar.volume_slider.isEnabled()

    def test_slider_posts_volume_change(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        with patch.object(commands, "execute") as mock:
            qtui.player_toolbar.volume_slider.setValue(50)
        mock.assert_called_once_with("media.volume.change", 50)

    def test_ui_update_sets_volume_silently(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        with patch.object(commands, "execute") as mock:
            post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.SLIDER_VOLUME, 50)
        mock.assert_not_called()
        assert qtui.player_toolbar.volume_slider.value() == 50

    def test_ui_update_checks_volume_toggle(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_VOLUME, True)
        assert qtui.player_toolbar.volume_toggle_action.isChecked()


class TestPlaybackRate:
    def test_spinbox_posts_rate_change(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        with patch.object(commands, "execute") as mock:
            qtui.player_toolbar.playback_rate_spinbox.setValue(1.5)
        mock.assert_called_once_with("media.playback_rate.try", pytest.approx(1.5))

    def test_ui_update_sets_rate_silently(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        with patch.object(commands, "execute") as mock:
            post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.SPINBOX_PLAYBACK, 2.0)
        mock.assert_not_called()
        assert qtui.player_toolbar.playback_rate_spinbox.value() == pytest.approx(2.0)


class TestParseMediaTime:
    def test_plain_seconds(self):
        assert parse_media_time("5") == pytest.approx(5.0)

    def test_plain_seconds_with_decimal(self):
        assert parse_media_time("5.5") == pytest.approx(5.5)

    def test_mm_ss(self):
        assert parse_media_time("1:30") == pytest.approx(90.0)

    def test_mm_ss_with_decimal(self):
        assert parse_media_time("1:30.5") == pytest.approx(90.5)

    def test_hh_mm_ss(self):
        assert parse_media_time("1:00:00") == pytest.approx(3600.0)

    def test_hh_mm_ss_with_decimal(self):
        assert parse_media_time("1:30:45.5") == pytest.approx(5445.5)

    def test_empty_returns_none(self):
        assert parse_media_time("") is None

    def test_trailing_colon_returns_none(self):
        assert parse_media_time("1:") is None

    def test_colon_only_returns_none(self):
        assert parse_media_time(":") is None


class TestTimeEditEnabled:
    @pytest.fixture(autouse=True)
    def reset_to_no_media(self):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.NO_MEDIA)
        post(Post.FILE_MEDIA_DURATION_CHANGED, 0.0)

    def test_time_edit_disabled_when_no_media_and_no_duration(self, qtui):
        assert not qtui.player_toolbar.time_edit.isEnabled()

    def test_time_edit_enabled_when_duration_set_in_no_media_state(self, qtui):
        post(Post.FILE_MEDIA_DURATION_CHANGED, 60.0)
        assert qtui.player_toolbar.time_edit.isEnabled()

    def test_time_edit_disabled_when_duration_cleared_in_no_media_state(self, qtui):
        post(Post.FILE_MEDIA_DURATION_CHANGED, 60.0)
        post(Post.FILE_MEDIA_DURATION_CHANGED, 0.0)
        assert not qtui.player_toolbar.time_edit.isEnabled()

    def test_time_edit_enabled_when_player_enabled(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        assert qtui.player_toolbar.time_edit.isEnabled()

    def test_time_edit_disabled_when_waiting_for_youtube(self, qtui):
        post(Post.FILE_MEDIA_DURATION_CHANGED, 60.0)
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.WAITING_FOR_YOUTUBE)
        assert not qtui.player_toolbar.time_edit.isEnabled()


class TestTimeEditInteraction:
    def test_seek_posted_on_valid_input(self, qtui):
        qtui.player_toolbar.duration = 100.0
        qtui.player_toolbar.time_edit.setText("1:30")
        with patch.object(commands, "execute") as mock:
            qtui.player_toolbar.time_edit.returnPressed.emit()
        mock.assert_called_once_with("media.seek", pytest.approx(90.0))

    def test_seek_clamped_to_duration(self, qtui):
        qtui.player_toolbar.duration = 60.0
        qtui.player_toolbar.time_edit.setText("200")
        with patch.object(commands, "execute") as mock:
            qtui.player_toolbar.time_edit.returnPressed.emit()
        mock.assert_called_once_with("media.seek", pytest.approx(60.0))

    def test_no_seek_on_parse_failure(self, qtui):
        qtui.player_toolbar.time_edit.setText("")
        with patch.object(commands, "execute") as mock:
            qtui.player_toolbar.time_edit.returnPressed.emit()
        mock.assert_not_called()

    def test_text_reverts_after_successful_commit(self, qtui):
        qtui.player_toolbar.current_time_string = "01:30.0"
        qtui.player_toolbar.duration = 100.0
        qtui.player_toolbar.time_edit.setText("02:00")
        with patch.object(commands, "execute"):
            qtui.player_toolbar.time_edit.returnPressed.emit()
        assert qtui.player_toolbar.time_edit.text() == "01:30.0"

    def test_text_reverts_after_failed_commit(self, qtui):
        qtui.player_toolbar.current_time_string = "01:30.0"
        qtui.player_toolbar.time_edit.setText("")
        qtui.player_toolbar.time_edit.returnPressed.emit()
        assert qtui.player_toolbar.time_edit.text() == "01:30.0"

    def test_escape_reverts_text(self, qtui):
        qtui.player_toolbar.current_time_string = "01:30.0"
        qtui.player_toolbar.time_edit.setText("02:00.0")
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        qtui.player_toolbar.eventFilter(qtui.player_toolbar.time_edit, event)
        assert qtui.player_toolbar.time_edit.text() == "01:30.0"

    def test_escape_does_not_seek(self, qtui):
        qtui.player_toolbar.duration = 100.0
        qtui.player_toolbar.time_edit.setText("1:30")
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        with patch.object(commands, "execute") as mock:
            qtui.player_toolbar.eventFilter(qtui.player_toolbar.time_edit, event)
        mock.assert_not_called()

    def test_time_display_updates_on_time_changed(self, qtui):
        post(Post.PLAYER_CURRENT_TIME_CHANGED, 90.0, MediaTimeChangeReason.PLAYBACK)
        assert qtui.player_toolbar.time_edit.text() == format_media_time(90.0)

    def test_time_display_not_updated_when_focused(self, qtui):
        qtui.player_toolbar.time_edit.setText("typing...")
        with patch.object(qtui.player_toolbar.time_edit, "hasFocus", return_value=True):
            post(Post.PLAYER_CURRENT_TIME_CHANGED, 90.0, MediaTimeChangeReason.PLAYBACK)
        assert qtui.player_toolbar.time_edit.text() == "typing..."

    def test_seek_via_timeline_updates_time_edit(self, qtui, tilia_state):
        tilia_state.duration = 120.0
        tilia_state.current_time = 90.0
        assert qtui.player_toolbar.time_edit.text() == format_media_time(90.0)


class TestDisplayUpdates:
    def test_duration_label_updated(self, qtui):
        post(Post.FILE_MEDIA_DURATION_CHANGED, 180.0)
        assert qtui.player_toolbar.duration_label.text() == format_media_time(180.0)

    def test_time_resets_to_zero_on_stop(self, qtui):
        post(Post.PLAYER_CURRENT_TIME_CHANGED, 90.0, MediaTimeChangeReason.PLAYBACK)
        post(Post.PLAYER_STOPPED)
        assert qtui.player_toolbar.time_edit.text() == format_media_time(0)

    def test_play_toggle_unchecked_on_stop(self, qtui):
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.PLAYER_ENABLED)
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_PLAY_PAUSE, True)
        post(Post.PLAYER_STOPPED)
        assert not qtui.player_toolbar.play_toggle_action.isChecked()


class TestTimePersistence:
    def test_pending_time_set_on_file_load(self, tilia, qtui, tmp_path):
        with Serve(Get.MEDIA_CURRENT_TIME, 42.0):
            file_path = save_tilia_to_tmp_path(tmp_path)
        post(Post.APP_CLEAR)
        commands.execute("file.open", path=file_path)
        assert qtui.player_toolbar._pending_time == pytest.approx(42.0)

    def test_seek_posted_when_duration_available(self, qtui):
        qtui.player_toolbar._pending_time = 42.0
        with patch.object(commands, "execute") as mock:
            post(Post.FILE_MEDIA_DURATION_CHANGED, 100.0)
        mock.assert_called_once_with("media.seek", pytest.approx(42.0))

    def test_seek_clamped_to_duration(self, qtui):
        qtui.player_toolbar._pending_time = 200.0
        with patch.object(commands, "execute") as mock:
            post(Post.FILE_MEDIA_DURATION_CHANGED, 100.0)
        mock.assert_called_once_with("media.seek", pytest.approx(100.0))

    def test_pending_time_cleared_after_seek(self, qtui):
        qtui.player_toolbar._pending_time = 42.0
        post(Post.FILE_MEDIA_DURATION_CHANGED, 100.0)
        assert qtui.player_toolbar._pending_time is None

    def test_no_seek_when_no_pending_time(self, qtui):
        with patch.object(commands, "execute") as mock:
            post(Post.FILE_MEDIA_DURATION_CHANGED, 100.0)
        mock.assert_not_called()

    def test_pending_time_not_applied_for_youtube(self, qtui):
        qtui.player_toolbar._pending_time = 42.0
        post(Post.PLAYER_UPDATE_CONTROLS, PlayerStatus.WAITING_FOR_YOUTUBE)
        assert qtui.player_toolbar._pending_time is None

    def test_pending_time_cleared_on_app_clear(self, qtui):
        qtui.player_toolbar._pending_time = 42.0
        post(Post.APP_CLEAR)
        assert qtui.player_toolbar._pending_time is None
