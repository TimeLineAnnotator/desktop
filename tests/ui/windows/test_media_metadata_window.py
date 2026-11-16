from unittest.mock import patch

import pytest
from PySide6.QtTest import QTest

from tests.constants import EXAMPLE_MEDIA_DURATION, EXAMPLE_MEDIA_PATH
from tests.mock import patch_yes_or_no_dialog
from tilia.media.player import QtAudioPlayer
from tilia.requests import Post, post
from tilia.ui import commands
from tilia.ui.format import format_media_time
from tilia.ui.windows import WindowKind
from tilia.ui.windows.metadata_edit_fields import EditMetadataFieldsDialog


@pytest.fixture
def media_metadata_window(qtui):
    post(Post.WINDOW_OPEN, WindowKind.MEDIA_METADATA)
    window = qtui._windows[WindowKind.MEDIA_METADATA]
    yield window
    with patch_yes_or_no_dialog(True):
        window.close()


def test_open(media_metadata_window):
    assert media_metadata_window


def test_close(qtui, media_metadata_window):
    media_metadata_window.close()
    assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)


def test_edit_field_value(qtui, media_metadata_window, tilia_state):
    media_metadata_window.metadata["title"].setText("New Title")
    media_metadata_window.apply_fields()
    media_metadata_window.close()

    assert tilia_state.metadata["title"] == "New Title"


def test_do_not_confirm_close(qtui, media_metadata_window, tilia_state):
    prev_title = tilia_state.metadata["title"]
    media_metadata_window.metadata["title"].setText("New Title")
    with patch_yes_or_no_dialog(False):
        media_metadata_window.close()

    assert qtui.is_window_open(WindowKind.MEDIA_METADATA)
    assert tilia_state.metadata["title"] == prev_title


def test_confirm_close_discards_changes(qtui, media_metadata_window, tilia_state):
    prev_title = tilia_state.metadata["title"]
    media_metadata_window.metadata["title"].setText("New Title")
    with patch_yes_or_no_dialog(True):
        media_metadata_window.close()

    assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)
    assert tilia_state.metadata["title"] == prev_title


def test_close_with_unsaved_changes_and_do_not_confirm_keeps_changes_in_window(
    qtui, media_metadata_window, tilia_state
):
    prev_title = tilia_state.metadata["title"]
    media_metadata_window.metadata["title"].setText("New Title")
    with patch_yes_or_no_dialog(False):
        media_metadata_window.close()

    assert qtui.is_window_open(WindowKind.MEDIA_METADATA)
    # The in-progress edit is kept in the window, ready to be applied/saved
    # later, rather than being reverted just because the close was aborted.
    assert media_metadata_window.metadata["title"].text() == "New Title"
    assert tilia_state.metadata["title"] == prev_title


def _set_custom_fields(window, valid_fields, invalid_fields=None):
    """Drive the "Edit fields..." button, replacing the full custom-fields
    list with `valid_fields` -- mirrors what the user would get by editing
    the dialog's text box and clicking Ok."""
    with (
        patch.object(EditMetadataFieldsDialog, "exec", return_value=True),
        patch.object(
            EditMetadataFieldsDialog,
            "get_result",
            return_value=(valid_fields, invalid_fields or []),
        ),
    ):
        window.on_edit_metadata_fields_button()


def test_adding_a_duplicate_field_does_not_add_it(media_metadata_window, tilia_state):
    _set_custom_fields(media_metadata_window, ["custom_field", "custom_field"])

    assert list(tilia_state.metadata).count("custom_field") == 1


def test_add_several_fields(media_metadata_window, tilia_state):
    _set_custom_fields(media_metadata_window, ["custom_field1", "custom_field2"])

    assert tilia_state.metadata["custom_field1"] == ""
    assert tilia_state.metadata["custom_field2"] == ""


def test_add_one_field(media_metadata_window, tilia_state):
    _set_custom_fields(media_metadata_window, ["custom_field"])

    assert tilia_state.metadata["custom_field"] == ""


def test_set_a_value_to_an_empty_string(media_metadata_window, tilia_state):
    media_metadata_window.metadata["composer"].setText("Some Composer")
    media_metadata_window.apply_fields()
    assert tilia_state.metadata["composer"] == "Some Composer"

    media_metadata_window.metadata["composer"].setText("")
    media_metadata_window.apply_fields()

    assert tilia_state.metadata["composer"] == ""


def test_edit_several_values(media_metadata_window, tilia_state):
    media_metadata_window.metadata["composer"].setText("New Composer")
    media_metadata_window.metadata["tonality"].setText("D minor")
    media_metadata_window.apply_fields()

    assert tilia_state.metadata["composer"] == "New Composer"
    assert tilia_state.metadata["tonality"] == "D minor"


def test_remove_all_fields(media_metadata_window, tilia_state):
    _set_custom_fields(media_metadata_window, ["custom_field1", "custom_field2"])
    assert "custom_field1" in tilia_state.metadata

    _set_custom_fields(media_metadata_window, [])

    assert "custom_field1" not in tilia_state.metadata
    assert "custom_field2" not in tilia_state.metadata
    # "composer" & co. are pre-populated *default* custom fields (see
    # settings["media_metadata"]["default_fields"]), not required ones, so
    # they are removed too. Only the truly required fields survive.
    assert "title" in tilia_state.metadata
    assert "notes" in tilia_state.metadata


def test_remove_one_field(media_metadata_window, tilia_state):
    _set_custom_fields(media_metadata_window, ["keep_field", "remove_field"])

    _set_custom_fields(media_metadata_window, ["keep_field"])

    assert "keep_field" in tilia_state.metadata
    assert "remove_field" not in tilia_state.metadata


def test_remove_several_fields(media_metadata_window, tilia_state):
    _set_custom_fields(
        media_metadata_window, ["keep_field", "remove_field1", "remove_field2"]
    )

    _set_custom_fields(media_metadata_window, ["keep_field"])

    assert "keep_field" in tilia_state.metadata
    assert "remove_field1" not in tilia_state.metadata
    assert "remove_field2" not in tilia_state.metadata


def test_replace_a_field_rename(media_metadata_window, tilia_state):
    _set_custom_fields(media_metadata_window, ["oldname"])
    media_metadata_window.metadata["oldname"].setText("some value")
    media_metadata_window.apply_fields()
    assert tilia_state.metadata["oldname"] == "some value"

    _set_custom_fields(media_metadata_window, ["newname"])

    assert "oldname" not in tilia_state.metadata
    assert "newname" in tilia_state.metadata
    assert tilia_state.metadata["newname"] == "some value"


@pytest.mark.parametrize(
    "new_fields",
    [
        pytest.param(["field_b", "field_c"], id="remove-the-first-field"),
        pytest.param(
            ["field_new", "field_a", "field_b", "field_c"], id="add-a-field-first"
        ),
        pytest.param(["field_c", "field_a", "field_b"], id="reorder-fields"),
    ],
)
def test_editing_fields_keeps_each_value_under_its_own_name(
    media_metadata_window, tilia_state, new_fields
):
    # Renames are told apart from removals and additions by comparing the old
    # and new field lists; shifted positions must not move values between fields.
    old_fields = ["field_a", "field_b", "field_c"]
    _set_custom_fields(media_metadata_window, old_fields)
    for name in old_fields:
        media_metadata_window.metadata[name].setText(f"{name} value")
    media_metadata_window.apply_fields()

    _set_custom_fields(media_metadata_window, new_fields)

    for name in old_fields:
        if name in new_fields:
            assert tilia_state.metadata[name] == f"{name} value"
    assert all(
        tilia_state.metadata[name] == ""
        for name in new_fields
        if name not in old_fields
    )


def load_media():
    # Without decoding the file, which can take longer than the tests' timeout.
    def load_reporting_duration(player, _path):
        # Like QtPlayer._engine_load_media, report the duration mid-load.
        player.on_media_duration_available(EXAMPLE_MEDIA_DURATION)
        return True

    with patch.object(
        QtAudioPlayer,
        "_engine_load_media",
        autospec=True,
        side_effect=load_reporting_duration,
    ):
        post(Post.APP_MEDIA_LOAD, EXAMPLE_MEDIA_PATH)


class TestMediaLength:
    @staticmethod
    def type_length(window, text):
        window.media_length_edit.clear()
        QTest.keyClicks(window.media_length_edit, text)

    def set_length(self, window, text):
        self.type_length(window, text)
        window.apply_fields()

    @staticmethod
    def marker_times(marker_tlui):
        return [m.get_data("time") for m in marker_tlui.timeline]

    def test_can_be_edited_without_media(self, media_metadata_window):
        assert media_metadata_window.media_length_edit.isVisible()
        assert media_metadata_window.media_length_edit.text() == "01:40.0"

    def test_set_without_media(self, media_metadata_window, tilia_state):
        self.set_length(media_metadata_window, "2:30.5")

        assert tilia_state.duration == 150.5
        assert tilia_state.metadata["media length"] == 150.5
        assert media_metadata_window.media_length_edit.text() == "02:30.5"

    def test_only_a_time_can_be_typed(self, media_metadata_window):
        self.type_length(media_metadata_window, "-1:3a0.5s")

        assert media_metadata_window.media_length_edit.text() == "1:30.5"

    def test_undo_and_redo(self, media_metadata_window, tilia_state):
        self.set_length(media_metadata_window, "2:30")

        commands.execute("edit.undo")
        assert tilia_state.duration == 100
        assert media_metadata_window.media_length_edit.text() == "01:40.0"

        commands.execute("edit.redo")
        assert tilia_state.duration == 150
        assert media_metadata_window.media_length_edit.text() == "02:30.0"

    def test_undo_gives_back_no_length(self, tilia, media_metadata_window, tilia_state):
        # As in a new file.
        tilia_state.duration = 0
        tilia.reset_undo_manager()
        self.set_length(media_metadata_window, "1:00")

        commands.execute("edit.undo")

        assert tilia_state.duration == 0
        assert tilia_state.metadata["media length"] == 0
        assert media_metadata_window.media_length_edit.text() == "00:00.0"

    @pytest.mark.parametrize("text", ["0", "00:00.0", "", ":"])
    def test_refuses_a_length_that_is_not_positive(
        self, media_metadata_window, tilia_state, tilia_errors, text
    ):
        recorded = len(tilia_state.undo_manager.stack)

        self.set_length(media_metadata_window, text)

        tilia_errors.assert_error()
        assert tilia_state.duration == 100
        assert len(tilia_state.undo_manager.stack) == recorded

    def test_the_same_length_records_nothing(self, media_metadata_window, tilia_state):
        recorded = len(tilia_state.undo_manager.stack)

        self.set_length(media_metadata_window, "100")

        assert tilia_state.duration == 100
        assert len(tilia_state.undo_manager.stack) == recorded

    def test_redo_keeps_other_fields_applied_with_the_length(
        self, media_metadata_window, tilia_state
    ):
        media_metadata_window.metadata["title"].setText("New Title")
        self.set_length(media_metadata_window, "2:30")

        commands.execute("edit.undo")
        commands.execute("edit.redo")

        assert tilia_state.metadata["title"] == "New Title"
        assert tilia_state.duration == 150

    def test_shorter_length_asks_to_scale(
        self, media_metadata_window, marker_tlui, tilia_state
    ):
        # As an earlier `load-media --scale-timelines yes` would leave it.
        tilia_state.set_duration(100, scale_timelines="yes")
        marker_tlui.create_marker(80)

        with patch_yes_or_no_dialog(True) as scale_prompt:
            self.set_length(media_metadata_window, "40")

        scale_prompt.assert_called_once()
        assert self.marker_times(marker_tlui) == [32]

    def test_shorter_length_crops_if_not_scaled_and_undo_restores(
        self, media_metadata_window, marker_tlui, tilia_state
    ):
        marker_tlui.create_marker(20)
        marker_tlui.create_marker(80)
        post(Post.APP_STATE_RECORD, "markers")

        # Don't scale; crop.
        with patch_yes_or_no_dialog([False, True]):
            self.set_length(media_metadata_window, "40")
        assert self.marker_times(marker_tlui) == [20]

        with patch_yes_or_no_dialog(True) as prompt:
            commands.execute("edit.undo")

        prompt.assert_not_called()
        assert tilia_state.duration == 100
        assert sorted(self.marker_times(marker_tlui)) == [20, 80]

    def test_closing_with_a_length_not_applied_asks(self, qtui, media_metadata_window):
        self.type_length(media_metadata_window, "2:30")

        with patch_yes_or_no_dialog(False):
            media_metadata_window.close()

        assert qtui.is_window_open(WindowKind.MEDIA_METADATA)

    def test_read_only_when_opened_with_media(self, qtui, tilia_state):
        load_media()
        post(Post.WINDOW_OPEN, WindowKind.MEDIA_METADATA)
        window = qtui._windows[WindowKind.MEDIA_METADATA]

        assert not window.media_length_edit.isVisible()
        label = window.read_only_labels["media length"]
        assert label.isVisible()
        assert label.text() == format_media_time(EXAMPLE_MEDIA_DURATION)
        window.close()

    def test_loading_media_makes_it_read_only(self, media_metadata_window):
        load_media()

        assert not media_metadata_window.media_length_edit.isVisible()
        label = media_metadata_window.read_only_labels["media length"]
        assert label.isVisible()
        assert label.text() == format_media_time(EXAMPLE_MEDIA_DURATION)

    def test_loading_media_drops_a_length_not_applied(
        self, media_metadata_window, tilia_state
    ):
        self.type_length(media_metadata_window, "2:30")
        load_media()

        media_metadata_window.apply_fields()

        assert tilia_state.duration == EXAMPLE_MEDIA_DURATION

    def test_unloading_media_makes_it_editable(self, media_metadata_window):
        load_media()

        commands.execute("edit.undo")

        assert media_metadata_window.media_length_edit.isVisible()
        assert media_metadata_window.media_length_edit.text() == "01:40.0"

    def test_closed_window_stops_following_the_length(
        self, media_metadata_window, tilia_state
    ):
        media_metadata_window.close()

        tilia_state.duration = 150

        assert media_metadata_window.media_length_edit.text() == "01:40.0"
