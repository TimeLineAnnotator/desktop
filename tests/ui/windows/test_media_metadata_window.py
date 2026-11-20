import json
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QEventLoop,
    QObject,
    QPoint,
    Qt,
    QTimer,
)
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QMenu,
    QMessageBox,
    QPushButton,
)

from tests.constants import EXAMPLE_MEDIA_DURATION, EXAMPLE_MEDIA_PATH
from tests.mock import Serve, patch_yes_or_no_dialog
from tests.utils import save_tilia_to_tmp_path
from tilia.boot import PendingFileOpen, TiliaApplication
from tilia.media.player import QtAudioPlayer
from tilia.requests import Get, Post, get, post
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.ui import commands
from tilia.ui.dialogs.add_timeline_without_media import AddTimelineWithoutMedia
from tilia.ui.dialogs.basic import YesNoOrCancelMessageBox, YesOrNoMessageBox
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
    # The window's own: the names and notes boxes stay its children once
    # closed, with buttons of their own.
    return [
        button_
        for button_ in window.findChildren(QPushButton)
        if button_.window() is window
    ]


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

        # Apply makes the buttons below the fields again, and so does OK on the
        # names box.
        media_metadata_window.apply_fields()

        self.assert_no_button_is_or_becomes_the_default(media_metadata_window)

        edit_fields(media_metadata_window, add="custom")

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


class Questions:
    def __init__(self):
        self.asked = []
        self.answered = []


@contextmanager
def press_enter_on_questions():
    """Shows each yes-or-no question on screen, as exec() does, and presses Enter
    on it, as a person does out of habit. Keeps the text of each question and the
    button Enter clicked, None if it clicked none."""
    questions = Questions()

    def exec_(box):
        questions.asked.append(box.text())
        clicked = []
        # A click closes the box, which deletes it.
        box.buttonClicked.connect(
            lambda button_: clicked.append(box.standardButton(button_))
        )
        box.setWindowModality(Qt.WindowModality.ApplicationModal)
        box.show()
        QTest.keyClick(box.windowHandle(), Qt.Key.Key_Return)
        if not clicked:
            box.close()
        questions.answered.append(clicked[0] if clicked else None)
        return clicked[0] if clicked else QMessageBox.StandardButton.No

    with patch.object(YesOrNoMessageBox, "exec", new=exec_):
        yield questions


# Ways the window is asked to close, or to leave for the names box. Each gets the
# window, a file to open over it, and Finder.


def click_button(text):
    def click(window, _file, _finder):
        button(window, text).click()

    return click


def escape(window, _file, _finder):
    press_escape(window)


def close_from_the_title_bar(window, _file, _finder):
    window.windowHandle().close()


def open_the_file(window, file, _finder):
    commands.execute("file.open", file)


def open_the_file_from_the_system(window, file, finder):
    finder.open(file)


class TestEnterOnTheQuestions:
    """Enter on "Close window without saving changes?" and "Leave window without
    saving changes?" answers No: the window stays open, with the edits. Losing
    them takes a click on Yes."""

    CLOSE = "Close window without saving changes?"
    LEAVE = "Leave window without saving changes?"

    @pytest.mark.parametrize("field, text", FIELD_KINDS)
    @pytest.mark.parametrize(
        "ask, question",
        [
            pytest.param(click_button("Cancel"), CLOSE, id="cancel"),
            pytest.param(escape, CLOSE, id="escape"),
            pytest.param(close_from_the_title_bar, CLOSE, id="title-bar"),
            pytest.param(open_the_file, CLOSE, id="file-opened"),
            pytest.param(
                open_the_file_from_the_system, CLOSE, id="file-from-the-system"
            ),
            pytest.param(click_button("Edit fields..."), LEAVE, id="edit-fields"),
        ],
    )
    def test_keeps_the_window_open_with_the_edits(
        self,
        qtui,
        tilia_state,
        files,
        window_over_file_a,
        finder,
        ask,
        question,
        field,
        text,
    ):
        window = window_over_file_a
        before = dict(tilia_state.metadata)
        duration = tilia_state.duration
        typed = type_in(window, field, text).text()

        with (
            press_enter_on_questions() as questions,
            patch.object(EditMetadataFieldsDialog, "exec", return_value=False) as names,
        ):
            ask(window, files["B"], finder)

        assert questions.asked == [question]
        assert questions.answered == [QMessageBox.StandardButton.No]
        names.assert_not_called()
        assert window.isVisible()
        assert qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert line_edit_of(window, field).text() == typed
        # File A is still open, as it was.
        assert open_file_path() == files["A"]
        assert tilia_state.metadata == before
        assert tilia_state.duration == duration

    def test_other_questions_keep_yes(self, qtui):
        with press_enter_on_questions() as questions:
            answer = get(Get.FROM_USER_YES_OR_NO, "Title", "Prompt?")

        assert questions.asked == ["Prompt?"]
        assert questions.answered == [QMessageBox.StandardButton.Yes]
        assert answer is True


def open_file_with(tmp_path, values):
    """Saves a file, then opens it with `values` in its metadata, as a script may
    write them: TiLiA itself writes text."""
    path = save_tilia_to_tmp_path(tmp_path, "made-by-a-script")
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    data["media_metadata"].update(values)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file)
    commands.execute("file.open", path)
    return path


def saved_metadata(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)["media_metadata"]


def file_bytes(path):
    with open(path, "rb") as file:
        return file.read()


@pytest.fixture
def open_window(qtui):
    def open_():
        commands.execute("window.open.metadata")
        return qtui._windows[WindowKind.MEDIA_METADATA]

    yield open_

    if qtui.is_window_open(WindowKind.MEDIA_METADATA):
        with patch_yes_or_no_dialog(True):
            qtui._windows[WindowKind.MEDIA_METADATA].close()


# A value that isn't text, as a file made by a script may hold, and its text.
VALUES_NOT_TEXT = [
    pytest.param(1990, "1990", id="integer"),
    pytest.param(19.5, "19.5", id="decimal"),
    pytest.param(True, "True", id="true"),
    pytest.param(None, "None", id="null"),
]


class TestAValueThatIsNotText:
    """A single value that isn't text, such as the number 1990, isn't an edit:
    its box shows its text, and nothing is asked until it is typed over. The first
    Apply that sets a field stores it as text, as the box shows it."""

    @pytest.mark.parametrize("value, shown", VALUES_NOT_TEXT)
    def test_opening_and_closing_asks_nothing(
        self, qtui, tmp_path, open_window, tilia_state, value, shown
    ):
        open_file_with(tmp_path, {"composer": value})
        window = open_window()
        assert window.metadata["composer"].text() == shown

        with answer_questions(False) as asked:
            window.close()

        assert asked == []
        assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)
        # Kept as it is: nothing was applied.
        assert repr(tilia_state.metadata["composer"]) == repr(value)

    @pytest.mark.parametrize("add", ["custom", None], ids=["ok", "cancel"])
    @pytest.mark.parametrize("value, shown", VALUES_NOT_TEXT)
    def test_edit_fields_asks_nothing(
        self, tmp_path, open_window, tilia_state, value, shown, add
    ):
        open_file_with(tmp_path, {"composer": value})
        window = open_window()

        with answer_questions(False) as asked:
            edit_fields(window, add=add)

        assert asked == []
        assert repr(tilia_state.metadata["composer"]) == repr(value)
        assert window.metadata["composer"].text() == shown
        assert ("custom" in tilia_state.metadata) == (add is not None)

        with answer_questions(False) as asked:
            window.close()
        assert asked == []

    @pytest.mark.parametrize("value, shown", VALUES_NOT_TEXT)
    def test_an_apply_of_another_field_stores_it_as_text(
        self, tmp_path, open_window, tilia_state, value, shown
    ):
        path = open_file_with(tmp_path, {"composer": value, "year": value})
        window = open_window()
        type_in(window, "title", "Bolero")

        button(window, "Apply").click()

        assert tilia_state.metadata["title"] == "Bolero"
        assert tilia_state.metadata["composer"] == shown
        assert tilia_state.metadata["year"] == shown
        assert window.metadata["composer"].text() == shown

        with answer_questions(False) as asked:
            window.close()
        assert asked == []

        commands.execute("file.save")
        metadata = saved_metadata(path)
        assert metadata["composer"] == shown
        assert metadata["year"] == shown

    @pytest.mark.parametrize("value, shown", VALUES_NOT_TEXT)
    def test_typed_over_it_stores_the_text_typed(
        self, tmp_path, open_window, tilia_state, value, shown
    ):
        open_file_with(tmp_path, {"composer": value, "year": value})
        window = open_window()
        type_in(window, "composer", "Ravel")

        with answer_questions(False) as asked:
            edit_fields(window, add=None)
        assert asked == [TestEnterOnTheQuestions.LEAVE]

        button(window, "Apply").click()

        assert tilia_state.metadata["composer"] == "Ravel"
        assert tilia_state.metadata["year"] == shown

    @pytest.mark.parametrize("value, shown", VALUES_NOT_TEXT)
    def test_an_apply_with_no_edits_keeps_it(
        self, tilia, tmp_path, open_window, tilia_state, value, shown
    ):
        path = open_file_with(tmp_path, {"composer": value})
        window = open_window()

        button(window, "Apply").click()

        assert repr(tilia_state.metadata["composer"]) == repr(value)
        assert not tilia.is_file_modified()
        window.close()
        commands.execute("file.save")
        assert repr(saved_metadata(path)["composer"]) == repr(value)

    @pytest.mark.parametrize("value, shown", VALUES_NOT_TEXT)
    def test_an_apply_of_the_length_alone_keeps_it(
        self, tmp_path, open_window, tilia_state, value, shown
    ):
        open_file_with(tmp_path, {"composer": value})
        window = open_window()
        type_in(window, "media length", "2:30")

        with patch_yes_or_no_dialog(False):  # Don't scale the timelines.
            button(window, "Apply").click()

        assert tilia_state.duration == 150
        assert repr(tilia_state.metadata["composer"]) == repr(value)

    def test_a_file_all_text_is_unchanged_by_an_apply_with_no_edits(
        self, tilia, tmp_path, open_window, tilia_state
    ):
        path = open_file_with(tmp_path, {"composer": "Ravel", "year": "1928"})
        before = dict(tilia_state.metadata)
        commands.execute("file.save")
        saved = file_bytes(path)
        window = open_window()

        with answer_questions(False) as asked:
            button(window, "Apply").click()
            window.close()

        assert asked == []
        assert tilia_state.metadata == before
        assert not tilia.is_file_modified()
        commands.execute("file.save")
        assert file_bytes(path) == saved


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


class Finder:
    """Opens files as macOS does one opened from Finder: a FileOpen event to
    the application, which hands the file on to App.on_open, as boot() sets it
    up. A modal window doesn't block the event."""

    def __init__(self, qapplication, app):
        self.qapplication = qapplication
        self.handed_on = []
        # When each open handed on starts and ends: one inside another shows
        # in the order.
        self.opens = []

        def on_open(path):
            name = Path(path).stem
            self.handed_on.append(Path(path))
            self.opens.append(f"start {name}")
            try:
                app.on_open(path)
            finally:
                self.opens.append(f"end {name}")

        # The session's QApplication can't be a TiliaApplication (only one may
        # exist per process), so its event handling is borrowed, as in
        # test_boot.
        TiliaApplication.set_file_open_callback(qapplication, on_open)

    def open(self, path):
        self.handed_on_before_open = list(self.handed_on)
        assert TiliaApplication.event(self.qapplication, QFileOpenEvent(str(path)))

    def assert_waits(self):
        """Checks that the file last opened hasn't been handed on, at once or
        when it tried again."""
        # Long enough for it to try again.
        QTest.qWait(3 * PendingFileOpen.RETRY_INTERVAL_MS)
        assert self.handed_on == self.handed_on_before_open

    def wait_until_handed_on(self, count=1):
        deadline = time.monotonic() + 5
        while len(self.handed_on) < count:
            assert time.monotonic() < deadline, "The file wasn't handed on."
            QTest.qWait(10)


@pytest.fixture
def finder(qapplication, tilia, monkeypatch):
    file_open = PendingFileOpen()
    monkeypatch.setattr(qapplication, "_file_open", file_open, raising=False)
    yield Finder(qapplication, tilia)
    # Dropped, so that a file still waiting can't open in a later test.
    file_open._pending = None


@pytest.fixture
def files(qtui, tmp_path):
    """Files A, B and C, saved with their own titles. A is open."""
    paths = {}
    for name in ("A", "B", "C"):
        post(Post.MEDIA_METADATA_FIELD_SET, "title", f"Title {name}")
        paths[name] = Path(save_tilia_to_tmp_path(tmp_path, name))
    commands.execute("file.open", paths["A"])
    return paths


@pytest.fixture
def window_over_file_a(qtui, files):
    """The Metadata window, open over file A."""
    commands.execute("window.open.metadata")
    window = qtui._windows[WindowKind.MEDIA_METADATA]

    yield window

    if qtui.is_window_open(WindowKind.MEDIA_METADATA):
        with patch_yes_or_no_dialog(True):
            window.close()


@contextmanager
def on_screen(dialog_class, *answers):
    """Patches dialog_class.exec(): the n-th dialog is on screen, modal, while
    answers[n](dialog) runs, and exec() returns what that returns. Yields the
    dialogs shown."""
    shown = []

    def exec_(dialog):
        shown.append(dialog)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()
        try:
            return answers[len(shown) - 1](dialog)
        finally:
            dialog.hide()

    # A function, not a mock, so that it gets the dialog as `self`.
    with patch.object(dialog_class, "exec", exec_):
        yield shown


@contextmanager
def questions(*answers):
    """Answers the yes/no questions in turn, each on screen while its answer,
    a bool or a function that returns one, is given. Yields the questions
    asked."""
    asked = []

    def answer(box):
        asked.append(box.text())
        given = answers[len(asked) - 1]
        is_yes = given() if callable(given) else given
        return (
            QMessageBox.StandardButton.Yes if is_yes else QMessageBox.StandardButton.No
        )

    with on_screen(YesOrNoMessageBox, *[answer] * len(answers)):
        yield asked


def file_arrives(finder, path, answer):
    """An answer to a dialog: opens `path` from Finder while the dialog is on
    screen, checks that it waits, then gives `answer`."""

    def give(*_):
        finder.open(path)
        finder.assert_waits()
        return answer

    return give


def open_file_path():
    return Path(get(Get.FILE_PATH))


CLOSE_QUESTION = "Close window without saving changes?"
LEAVE_QUESTION = "Leave window without saving changes?"


class TestFileOpenedFromTheSystem:
    def test_with_edits_yes_closes_the_window_and_opens_the_file(
        self, qtui, tilia_state, files, window_over_file_a, finder
    ):
        window = window_over_file_a
        window.metadata["title"].setText("Typed over A")

        with questions(True) as asked:
            finder.open(files["B"])

        assert asked == [CLOSE_QUESTION]
        assert not window.isVisible()
        assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert open_file_path() == files["B"]
        # A's typed text went nowhere: B is as saved.
        assert tilia_state.metadata["title"] == "Title B"
        assert not get(Get.IS_FILE_MODIFIED)

    def test_with_edits_no_keeps_the_window_and_file_a(
        self, qtui, tilia_state, files, window_over_file_a, finder
    ):
        window = window_over_file_a
        window.metadata["title"].setText("Typed over A")

        with questions(False) as asked:
            finder.open(files["B"])

        assert asked == [CLOSE_QUESTION]
        assert window.isVisible()
        assert qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert window.metadata["title"].text() == "Typed over A"
        assert open_file_path() == files["A"]
        assert tilia_state.metadata["title"] == "Title A"
        # Apply writes to A, the file the window shows.
        window.apply_fields()
        assert open_file_path() == files["A"]
        assert tilia_state.metadata["title"] == "Typed over A"

    def test_without_edits_closes_the_window_and_opens_the_file(
        self, qtui, tilia_state, files, window_over_file_a, finder
    ):
        window = window_over_file_a

        with questions() as asked:
            finder.open(files["B"])

        assert asked == []
        assert not window.isVisible()
        assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert open_file_path() == files["B"]
        assert tilia_state.metadata["title"] == "Title B"


class TestFileOpenedWhileADialogIsOpen:
    """The file waits until the dialog is closed, then opens as usual."""

    @pytest.mark.parametrize(
        "answers, is_opened",
        [
            # The window closes, and then B opens.
            ([True], True),
            # The window stays, and is asked again for B.
            ([False, True], True),
            ([False, False], False),
        ],
        ids=["yes", "no-then-yes", "no-then-no"],
    )
    def test_the_windows_question(
        self, qtui, tilia_state, files, window_over_file_a, finder, answers, is_opened
    ):
        window = window_over_file_a
        window.metadata["title"].setText("Typed over A")
        first, *then = answers

        with questions(file_arrives(finder, files["B"], first), *then) as asked:
            press_escape(window)
            finder.wait_until_handed_on()

        assert asked == [CLOSE_QUESTION] * len(answers)
        assert qtui.is_window_open(WindowKind.MEDIA_METADATA) is not is_opened
        assert open_file_path() == files["B" if is_opened else "A"]
        assert tilia_state.metadata["title"] == ("Title B" if is_opened else "Title A")

    @pytest.mark.parametrize("accepted", [True, False], ids=["ok", "cancel"])
    def test_edit_notes(
        self, qtui, tilia_state, files, window_over_file_a, finder, accepted
    ):
        window = window_over_file_a

        def type_notes_while_file_arrives(dialog):
            dialog.text_edit.setPlainText("Notes typed over A")
            return file_arrives(finder, files["B"], accepted)()

        with (
            on_screen(EditNotesDialog, type_notes_while_file_arrives),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)) as save_question,
            questions() as asked,
        ):
            window.on_edit_notes_button()
            # The notes went to A, the file the window shows.
            notes_in_a = "Notes typed over A" if accepted else ""
            assert tilia_state.metadata["notes"] == notes_in_a
            finder.wait_until_handed_on()

        # Then B opens with the usual questions: about A's changes, if any.
        assert save_question.called is accepted
        assert asked == []
        assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert open_file_path() == files["B"]
        assert tilia_state.metadata["notes"] == ""

    @pytest.mark.parametrize("accepted", [True, False], ids=["ok", "cancel"])
    def test_edit_fields(
        self, qtui, tilia_state, files, window_over_file_a, finder, accepted
    ):
        window = window_over_file_a

        def add_a_field_while_file_arrives(dialog):
            dialog.text_edit.append("extra")
            return file_arrives(finder, files["B"], accepted)()

        with (
            on_screen(EditMetadataFieldsDialog, add_a_field_while_file_arrives),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)) as save_question,
            questions() as asked,
        ):
            window.on_edit_metadata_fields_button()
            assert ("extra" in tilia_state.metadata) is accepted
            finder.wait_until_handed_on()

        assert save_question.called is accepted
        assert asked == []
        assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert open_file_path() == files["B"]
        assert "extra" not in tilia_state.metadata

    @pytest.mark.parametrize("answer", [True, False], ids=["yes", "no"])
    def test_edit_fields_question_about_edits(
        self, qtui, tilia_state, files, window_over_file_a, finder, answer
    ):
        window = window_over_file_a
        window.metadata["title"].setText("Typed over A")

        with (
            # Neither answer applies the edits. After Yes, OK on the names box
            # shows the fields again without them; after No, they are still
            # typed, and closing the window for B asks about them.
            questions(file_arrives(finder, files["B"], answer), True) as asked,
            on_screen(EditMetadataFieldsDialog, lambda dialog: True),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)) as save_question,
        ):
            window.on_edit_metadata_fields_button()
            assert tilia_state.metadata["title"] == "Title A"
            finder.wait_until_handed_on()

        assert asked == (
            [LEAVE_QUESTION] if answer else [LEAVE_QUESTION, CLOSE_QUESTION]
        )
        assert not save_question.called
        assert not qtui.is_window_open(WindowKind.MEDIA_METADATA)
        assert open_file_path() == files["B"]
        assert tilia_state.metadata["title"] == "Title B"

    @pytest.fixture
    def dialog(self, qtui):
        """A dialog on screen, over the main window."""
        dialog = QDialog(get(Get.MAIN_WINDOW))
        dialog.setModal(True)
        dialog.show()
        yield dialog
        dialog.reject()
        dialog.deleteLater()

    @pytest.mark.parametrize("accepted", [True, False], ids=["ok", "cancel"])
    def test_any_dialog(self, tilia_state, files, finder, dialog, accepted):
        finder.open(files["B"])
        finder.assert_waits()

        dialog.done(accepted)
        finder.wait_until_handed_on()

        assert open_file_path() == files["B"]

    def test_two_files_the_last_one_opens(self, tilia_state, files, finder, dialog):
        finder.open(files["C"])
        finder.open(files["B"])
        finder.assert_waits()

        dialog.reject()
        finder.wait_until_handed_on()
        QTest.qWait(3 * PendingFileOpen.RETRY_INTERVAL_MS)

        assert finder.handed_on == [files["B"]]
        assert open_file_path() == files["B"]


SAVE_QUESTION = "Save changes to current file?"


def in_main_loop(body):
    """Runs body() inside an event loop, as TiLiA's code runs inside the
    application's main loop: an event loop that the code starts is then nested
    in it, as in the app. Raises what body() raises."""
    loop = QEventLoop()
    raised = []

    def run():
        try:
            body()
        except BaseException as exc:
            raised.append(exc)
        finally:
            loop.quit()

    QTimer.singleShot(0, run)
    loop.exec()
    if raised:
        raise raised[0]


@contextmanager
def media_load_runs_an_event_loop(while_loading=None):
    """Loading media runs an event loop for a while, as QtPlayer's
    wait_for_signal does until the player reports the media loaded.
    `while_loading` runs inside that loop."""

    def load(player, _path):
        loop = QEventLoop()
        QTimer.singleShot(150, loop.quit)
        if while_loading:
            QTimer.singleShot(0, while_loading)
        loop.exec()
        player.on_media_duration_available(EXAMPLE_MEDIA_DURATION)
        return True

    with patch.object(
        QtAudioPlayer, "_engine_load_media", autospec=True, side_effect=load
    ):
        yield


@contextmanager
def save_questions(*answers):
    """Answers "Save changes to current file?" in turn with No (don't save),
    each on screen while its answer, a function or None, runs. Yields the
    questions asked."""
    asked = []

    def answer(box):
        asked.append(box.text())
        if given := answers[len(asked) - 1]:
            given()
        return QMessageBox.StandardButton.No

    with on_screen(YesNoOrCancelMessageBox, *[answer] * len(answers)):
        yield asked


@pytest.fixture
def b_with_media(files):
    """B, saved with media. A is open again."""
    commands.execute("file.open", files["B"])
    load_media()
    commands.execute("file.save")
    commands.execute("file.open", files["A"])


class TestFileOpenedWhileTiliaIsBusy:
    """A file that arrives in the middle of something waits until it ends: a
    file opening, media loading, a menu. These run event loops, or process
    events, in which the file would otherwise open."""

    def test_while_a_file_opens(self, tilia_state, files, finder):
        post(Post.MEDIA_METADATA_FIELD_SET, "title", "Changed A")

        def c_arrives():
            finder.open(files["C"])
            finder.assert_waits()
            # The answer takes long enough for C's next try to fall due while
            # B opens, when only the long operation processes events.
            time.sleep(1.5 * PendingFileOpen.RETRY_INTERVAL_MS / 1000)

        def body():
            with save_questions(c_arrives) as asked:
                finder.open(files["B"])
                finder.wait_until_handed_on(2)
            assert asked == [SAVE_QUESTION]

        in_main_loop(body)

        assert finder.opens == ["start B", "end B", "start C", "end C"]
        assert open_file_path() == files["C"]
        assert tilia_state.metadata["title"] == "Title C"

    @pytest.mark.parametrize(
        "c_arrives_during", ["the save question", "the media load"]
    )
    def test_while_a_file_with_media_opens(
        self, tilia_state, files, b_with_media, finder, c_arrives_during
    ):
        def c_arrives():
            finder.open(files["C"])

        if c_arrives_during == "the save question":
            post(Post.MEDIA_METADATA_FIELD_SET, "title", "Changed A")
            answers, while_loading = [c_arrives], None
        else:
            # B and C opened together: C arrives while B opens.
            answers, while_loading = [], c_arrives

        def body():
            with (
                save_questions(*answers) as asked,
                media_load_runs_an_event_loop(while_loading),
            ):
                finder.open(files["B"])
                finder.wait_until_handed_on(2)
            assert asked == [SAVE_QUESTION] * len(answers)

        in_main_loop(body)

        assert finder.opens == ["start B", "end B", "start C", "end C"]
        assert open_file_path() == files["C"]
        assert tilia_state.metadata["title"] == "Title C"
        assert not get(Get.MEDIA_PATH)

    def test_while_the_player_stops_for_a_file_that_opens(
        self, tilia_state, files, finder
    ):
        # B and C opened together. C arrives while opening B stops the media
        # (on_clear), before B's long operation starts: the player runs an
        # event loop until the media has stopped.
        stops = []

        def stop_running_an_event_loop(player):
            loop = QEventLoop()
            QTimer.singleShot(150, loop.quit)
            if not stops:
                QTimer.singleShot(0, lambda: finder.open(files["C"]))
            stops.append(player)
            loop.exec()

        def body():
            with patch.object(
                QtAudioPlayer,
                "_engine_unload_media",
                autospec=True,
                side_effect=stop_running_an_event_loop,
            ):
                finder.open(files["B"])
                finder.wait_until_handed_on(2)

        in_main_loop(body)

        assert finder.opens == ["start B", "end B", "start C", "end C"]
        assert open_file_path() == files["C"]
        assert tilia_state.metadata["title"] == "Title C"

    def test_while_media_loads(self, tilia_state, files, finder):
        # File > Load media: C arrives while the media file dialog is on
        # screen, and waits until the media has loaded into A.
        def choose_media(dialog):
            finder.open(files["C"])
            finder.assert_waits()
            return True

        def body():
            with (
                patch.object(
                    QFileDialog, "selectedFiles", return_value=[EXAMPLE_MEDIA_PATH]
                ),
                on_screen(QFileDialog, choose_media),
                media_load_runs_an_event_loop(),
                save_questions(None) as asked,
            ):
                commands.execute("media.load.local")
                finder.wait_until_handed_on()
            # A had the media when C opened: it asked whether to save A.
            assert asked == [SAVE_QUESTION]

        in_main_loop(body)

        assert finder.opens == ["start C", "end C"]
        assert open_file_path() == files["C"]
        assert not get(Get.MEDIA_PATH)

    def test_while_a_menu_is_open(self, tilia_state, files, finder):
        handed_on_while_open = []

        def body():
            menu = QMenu(get(Get.MAIN_WINDOW))
            menu.addAction("Action")

            def b_arrives_then_close_the_menu():
                finder.open(files["B"])
                QTest.qWait(3 * PendingFileOpen.RETRY_INTERVAL_MS)
                handed_on_while_open.extend(finder.handed_on)
                menu.close()

            QTimer.singleShot(0, b_arrives_then_close_the_menu)
            menu.exec(QPoint(0, 0))
            finder.wait_until_handed_on()
            menu.deleteLater()

        in_main_loop(body)

        assert handed_on_while_open == []
        assert open_file_path() == files["B"]
