import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QPushButton

from tests.constants import EXAMPLE_MEDIA_DURATION, EXAMPLE_MEDIA_PATH
from tests.mock import Serve, patch_yes_or_no_dialog
from tests.utils import save_tilia_to_tmp_path
from tilia.media.player import QtAudioPlayer
from tilia.requests import Get, Post, get, post
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.ui import commands
from tilia.ui.dialogs.add_timeline_without_media import AddTimelineWithoutMedia
from tilia.ui.dialogs.basic import YesOrNoMessageBox
from tilia.ui.format import format_media_time
from tilia.ui.windows import WindowKind
from tilia.ui.windows.metadata_edit_fields import EditMetadataFieldsDialog
from tilia.ui.windows.metadata_edit_notes import EditNotesDialog


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


def is_shown(widget):
    # Widgets added to an open window are shown once the event loop runs.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.MetaCall)
    return widget.isVisible()


def add_timeline_setting_length(length):
    # With no length, adding a timeline asks how to go on; this sets one.
    with (
        Serve(
            Get.FROM_USER_ADD_TIMELINE_WITHOUT_MEDIA,
            (True, AddTimelineWithoutMedia.Result.SET_DURATION),
        ),
        Serve(Get.FROM_USER_FLOAT, (True, length)),
    ):
        commands.execute("timelines.add.marker", name="marker")


@pytest.fixture
def new_file(tilia, tilia_state):
    tilia_state.duration = 0
    tilia.reset_undo_manager()


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
        assert is_shown(media_metadata_window.media_length_edit)
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
        # Undo can't run while the window is open.
        media_metadata_window.close()

        commands.execute("edit.undo")
        assert tilia_state.duration == 100
        assert tilia_state.metadata["media length"] == 100

        commands.execute("edit.redo")
        assert tilia_state.duration == 150
        assert tilia_state.metadata["media length"] == 150

    def test_undo_gives_back_no_length(self, tilia, media_metadata_window, tilia_state):
        # As in a new file.
        tilia_state.duration = 0
        tilia.reset_undo_manager()
        self.set_length(media_metadata_window, "1:00")
        media_metadata_window.close()

        commands.execute("edit.undo")

        assert tilia_state.duration == 0
        assert tilia_state.metadata["media length"] == 0

    @pytest.mark.parametrize(
        "text, message",
        [
            ("0", "Cannot set media length to '0'."),
            ("00:00.0", "Cannot set media length to '00:00.0'."),
            ("", "Media length is empty."),
            (":", "Cannot set media length to ':'."),
        ],
    )
    def test_refuses_a_length_that_is_not_positive(
        self, media_metadata_window, tilia_state, tilia_errors, text, message
    ):
        recorded = len(tilia_state.undo_manager.stack)

        self.set_length(media_metadata_window, text)

        tilia_errors.assert_in_error_message(message)
        assert tilia_state.duration == 100
        assert len(tilia_state.undo_manager.stack) == recorded

    def test_the_shown_length_changes_nothing(
        self, media_metadata_window, marker_tlui, tilia_state
    ):
        # Shown rounded, as 01:40.0.
        tilia_state.set_duration(100.04, scale_timelines="no")
        marker_tlui.create_marker(50)
        post(Post.APP_STATE_RECORD, "marker")
        recorded = len(tilia_state.undo_manager.stack)

        with patch_yes_or_no_dialog(True) as prompt:
            self.set_length(media_metadata_window, "1:40")

        prompt.assert_not_called()
        assert tilia_state.duration == 100.04
        assert len(tilia_state.undo_manager.stack) == recorded

    def test_the_exact_length_records_nothing(self, media_metadata_window, tilia_state):
        tilia_state.duration = 100.04
        recorded = len(tilia_state.undo_manager.stack)

        self.set_length(media_metadata_window, "100.04")

        assert tilia_state.duration == 100.04
        assert len(tilia_state.undo_manager.stack) == recorded

    def test_shows_a_length_the_player_reports_late(self, qtui, tilia):
        load_media()
        post(Post.WINDOW_OPEN, WindowKind.MEDIA_METADATA)
        window = qtui._windows[WindowKind.MEDIA_METADATA]

        # As a YouTube video's length arrives, after the video has loaded.
        tilia.player.on_media_duration_available(20.0, is_late=True)

        assert window.read_only_labels["media length"].text() == "00:20.0"
        window.close()

    def test_edit_fields_asks_about_a_length_not_applied(
        self, media_metadata_window, tilia_state
    ):
        self.type_length(media_metadata_window, "2:30")

        with (
            patch.object(EditMetadataFieldsDialog, "exec", return_value=False),
            patch_yes_or_no_dialog(False) as prompt,
        ):
            media_metadata_window.on_edit_metadata_fields_button()

        prompt.assert_called_once()
        assert tilia_state.duration == 100

    def test_redo_keeps_other_fields_applied_with_the_length(
        self, media_metadata_window, tilia_state
    ):
        media_metadata_window.metadata["title"].setText("New Title")
        self.set_length(media_metadata_window, "2:30")
        media_metadata_window.close()

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
        media_metadata_window.close()

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

        assert not is_shown(window.media_length_edit)
        label = window.read_only_labels["media length"]
        assert is_shown(label)
        assert label.text() == format_media_time(EXAMPLE_MEDIA_DURATION)
        window.close()

    def test_loading_media_makes_it_read_only(self, media_metadata_window):
        load_media()

        assert not is_shown(media_metadata_window.media_length_edit)
        label = media_metadata_window.read_only_labels["media length"]
        assert is_shown(label)
        assert label.text() == format_media_time(EXAMPLE_MEDIA_DURATION)
        path_label = media_metadata_window.read_only_labels["media path"]
        assert path_label.text() == EXAMPLE_MEDIA_PATH

    def test_loading_media_drops_a_length_not_applied(
        self, media_metadata_window, tilia_state
    ):
        self.type_length(media_metadata_window, "2:30")
        load_media()

        media_metadata_window.apply_fields()

        assert tilia_state.duration == EXAMPLE_MEDIA_DURATION

    def test_closed_window_stops_following_the_length(
        self, media_metadata_window, tilia_state
    ):
        media_metadata_window.close()

        tilia_state.duration = 150

        assert media_metadata_window.media_length_edit.text() == "01:40.0"


def test_undoing_a_timeline_added_with_a_length_gives_back_no_length(
    qtui, tls, tilia_state, new_file
):
    add_timeline_setting_length(60)
    assert tilia_state.duration == 60

    commands.execute("edit.undo")
    assert tilia_state.duration == 0
    assert not tls.get_timelines_by_type(MarkerTimeline)

    commands.execute("edit.redo")
    assert tilia_state.duration == 60
    assert tls.get_timelines_by_type(MarkerTimeline)


class Received(QObject):
    """Counts the key and mouse button presses a window receives."""

    def __init__(self):
        super().__init__()
        self.count = 0

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress):
            self.count += 1
        return False


def press_escape(window):
    QTest.keyClick(window.windowHandle(), Qt.Key.Key_Escape)


class TestModal:
    def test_main_window_takes_no_input(self, media_metadata_window, marker_tlui):
        commands.execute("timeline.marker.add", time=10)
        main_window = get(Get.MAIN_WINDOW).windowHandle()
        received = Received()
        main_window.installEventFilter(received)
        try:
            QTest.keyClick(
                main_window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
            )
            QTest.mouseClick(
                main_window, Qt.MouseButton.LeftButton, pos=QPoint(50, 200)
            )
        finally:
            main_window.removeEventFilter(received)

        assert received.count == 0
        # The app's undo didn't run.
        assert len(marker_tlui) == 1

    def test_ctrl_z_in_a_field_undoes_the_typing(
        self, media_metadata_window, marker_tlui
    ):
        commands.execute("timeline.marker.add", time=10)
        title = media_metadata_window.metadata["title"]
        old_title = title.text()
        title.setFocus()
        QTest.keyClicks(title, " typed")

        QTest.keyClick(
            media_metadata_window.windowHandle(),
            Qt.Key.Key_Z,
            Qt.KeyboardModifier.ControlModifier,
        )

        assert title.text() == old_title
        assert len(marker_tlui) == 1

    def test_escape_without_edits_closes(self, qtui, media_metadata_window):
        press_escape(media_metadata_window)

        assert not media_metadata_window.isVisible()
        assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)

    def test_escape_with_edits_asks(self, qtui, media_metadata_window):
        media_metadata_window.metadata["title"].setText("Typed title")

        with patch_yes_or_no_dialog(False) as prompt:
            press_escape(media_metadata_window)

        prompt.assert_called_once()
        assert media_metadata_window.isVisible()
        assert qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert media_metadata_window.metadata["title"].text() == "Typed title"

    def test_escape_with_edits_closes_if_confirmed(
        self, qtui, media_metadata_window, tilia_state
    ):
        old_title = tilia_state.metadata["title"]
        media_metadata_window.metadata["title"].setText("Typed title")

        with patch_yes_or_no_dialog(True) as prompt:
            press_escape(media_metadata_window)

        prompt.assert_called_once()
        assert not media_metadata_window.isVisible()
        assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert tilia_state.metadata["title"] == old_title

    def test_reopens_after_escape(self, qtui, media_metadata_window):
        press_escape(media_metadata_window)

        commands.execute("window.open.metadata")

        window = qtui._windows[WindowKind.MEDIA_METADATA]
        assert window is not None and window.isVisible()
        window.close()


@contextmanager
def answer_questions(yes: bool):
    """Answers the window's yes-or-no questions with Yes or No, and keeps the
    text of each."""
    asked = []

    def exec_(box):
        asked.append(box.text())
        return QMessageBox.StandardButton.Yes if yes else QMessageBox.StandardButton.No

    with patch.object(YesOrNoMessageBox, "exec", new=exec_):
        yield asked


# A field of each kind, and a text to type in it.
FIELD_KINDS = [
    pytest.param("title", "Typed title", id="required"),
    pytest.param("composer", "Typed composer", id="default"),
    pytest.param("media length", "2:30", id="media-length"),
]


def line_edit_of(window, field):
    if field == "media length":
        return window.media_length_edit
    return window.metadata[field]


def type_in(window, field, text):
    line_edit = line_edit_of(window, field)
    line_edit.clear()
    QTest.keyClicks(line_edit, text)
    return line_edit


def buttons(window):
    return window.findChildren(QPushButton)


def button(window, text):
    return next(button for button in buttons(window) if button.text() == text)


def edit_fields(window, add=None):
    """Clicks "Edit fields...", and in its box, OK with the field `add` added,
    or Cancel if `add` is None."""

    def exec_(dialog):
        if add is None:
            return False
        dialog.text_edit.setPlainText(dialog.text_edit.toPlainText() + add + "\n")
        return True

    with patch.object(EditMetadataFieldsDialog, "exec", new=exec_):
        button(window, "Edit fields...").click()


class TestEnter:
    """Enter does nothing: no button is the default, and the person clicks
    Apply (#910, point 1)."""

    @staticmethod
    def assert_no_button_is_or_becomes_the_default(window):
        # The window makes its first auto-default button the default when it
        # is shown, and any other when it gets the focus.
        assert {"Apply", "Cancel", "Edit notes...", "Edit fields..."} <= {
            button_.text() for button_ in buttons(window)
        }
        for button_ in buttons(window):
            assert not button_.isDefault(), button_.text()
            assert not button_.autoDefault(), button_.text()

    def test_no_button_is_or_becomes_the_default(self, media_metadata_window):
        self.assert_no_button_is_or_becomes_the_default(media_metadata_window)

        # Apply makes the buttons below the fields again.
        media_metadata_window.apply_fields()

        self.assert_no_button_is_or_becomes_the_default(media_metadata_window)

    @pytest.mark.parametrize(
        "key", [Qt.Key.Key_Return, Qt.Key.Key_Enter], ids=["return", "enter"]
    )
    @pytest.mark.parametrize("field, text", FIELD_KINDS)
    def test_in_a_field_does_nothing(
        self, qtui, media_metadata_window, tilia_state, field, text, key
    ):
        before = dict(tilia_state.metadata)
        line_edit = type_in(media_metadata_window, field, text)
        typed = line_edit.text()

        with (
            answer_questions(True) as asked,
            patch.object(EditMetadataFieldsDialog, "exec", return_value=False) as names,
            patch.object(EditNotesDialog, "exec", return_value=False) as notes,
        ):
            QTest.keyClick(line_edit, key)

        assert asked == []
        names.assert_not_called()
        notes.assert_not_called()
        assert media_metadata_window.isVisible()
        assert qtui.is_window_open(WindowKind.MEDIA_METADATA)
        # Nothing applied, and the typing is still there.
        assert tilia_state.metadata == before
        assert tilia_state.duration == 100
        assert line_edit.text() == typed


class TestEditFieldsWithEditsNotApplied:
    """'Edit fields...' asks "Leave window without saving changes?". Yes leaves
    the edits not applied, as the question says, and No stays in the window
    (#910, point 3)."""

    LEAVE = "Leave window without saving changes?"
    CLOSE = "Close window without saving changes?"

    @pytest.mark.parametrize("field, text", FIELD_KINDS)
    def test_yes_then_ok_drops_the_edit(
        self, media_metadata_window, tilia_state, tmp_path, field, text
    ):
        # A title of its own: saving an untitled file names it after the file.
        type_in(media_metadata_window, "title", "Bolero")
        media_metadata_window.apply_fields()
        before = dict(tilia_state.metadata)
        shown = line_edit_of(media_metadata_window, field).text()
        type_in(media_metadata_window, field, text)

        with answer_questions(True) as asked:
            edit_fields(media_metadata_window, add="custom")

        assert asked == [self.LEAVE]
        assert tilia_state.metadata == {**before, "custom": ""}
        assert tilia_state.duration == 100
        # OK on the names box shows the fields again, without the edit.
        assert line_edit_of(media_metadata_window, field).text() == shown
        assert media_metadata_window.metadata["custom"].text() == ""

        # Nothing is left to apply.
        with answer_questions(True) as asked:
            media_metadata_window.close()
        assert asked == []

        # The file has the names change only.
        with open(save_tilia_to_tmp_path(tmp_path), encoding="utf-8") as file:
            assert json.load(file)["media_metadata"] == {**before, "custom": ""}

    @pytest.mark.parametrize("field, text", FIELD_KINDS)
    def test_yes_then_cancel_keeps_the_typing_not_applied(
        self, qtui, media_metadata_window, tilia_state, field, text
    ):
        before = dict(tilia_state.metadata)
        typed = type_in(media_metadata_window, field, text).text()

        with answer_questions(True) as asked:
            edit_fields(media_metadata_window, add=None)

        assert asked == [self.LEAVE]
        # Back in the window, as in the timeline fields window: the typing is
        # still shown, and still not applied. Only OK on the names box shows
        # the fields again.
        assert qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert line_edit_of(media_metadata_window, field).text() == typed
        assert tilia_state.metadata == before
        assert tilia_state.duration == 100

        # So closing asks about it, and Yes drops it.
        with answer_questions(True) as asked:
            media_metadata_window.close()
        assert asked == [self.CLOSE]
        assert tilia_state.metadata == before
        assert tilia_state.duration == 100

    @pytest.mark.parametrize("field, text", FIELD_KINDS)
    def test_no_stays_in_the_window_with_the_edit(
        self, qtui, media_metadata_window, tilia_state, field, text
    ):
        before = dict(tilia_state.metadata)
        typed = type_in(media_metadata_window, field, text).text()

        with (
            answer_questions(False) as asked,
            patch.object(EditMetadataFieldsDialog, "exec") as names,
        ):
            button(media_metadata_window, "Edit fields...").click()

        assert asked == [self.LEAVE]
        names.assert_not_called()
        assert qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert line_edit_of(media_metadata_window, field).text() == typed
        assert tilia_state.metadata == before
        assert tilia_state.duration == 100

    def test_without_edits_it_asks_nothing(self, media_metadata_window, tilia_state):
        before = dict(tilia_state.metadata)

        with answer_questions(True) as asked:
            edit_fields(media_metadata_window, add="custom")

        assert asked == []
        assert tilia_state.metadata == {**before, "custom": ""}
