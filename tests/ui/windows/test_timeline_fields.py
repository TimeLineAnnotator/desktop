"""The fields window, and a component's fields in the inspector (FR-092;
`contracts/controls.md`, rows 8–10).

A timeline's fields are edited in "Fields…", from its context menu, like the file's
in the Metadata window, and undo covers each edit. A component's fields show, read
only, in its inspector. Files are WP3's file of every kind, as the core writes it
into the test's folder, so that an edit in TiLiA can be compared with the same edit
made through the core's API, byte for byte.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox, QLabel, QMessageBox

from tests.file.test_save_through_core import (
    EVERY_KIND,
    open_file,
    save,
    the_core_s_bytes,
    written_by_the_core,
)
from tests.mock import Serve
from tests.utils import get_command_action, undoable
from tilia.requests import Get, Post, get, post
from tilia.ui import commands
from tilia.ui.dialogs.basic import YesOrNoMessageBox
from tilia.ui.windows.kinds import WindowKind
from tilia.ui.windows.timeline_fields import (
    FieldNamesDialog,
    TimelineFieldsWindow,
    on_one_line,
)

# WP3's file of every kind: its timelines, and the components that have fields.
BEATS = "019b76da-a802-75fc-a8eb-94052e5f713a"  # role time_map, author
BARS = "019b76da-a803-7ce2-9d88-eeef1c5ba428"  # a beat timeline without fields
FORM = "019b76da-a804-7297-8763-137b42b8b88a"  # role, author, source, vocabulary
CADENCES = "019b76da-a805-7003-b62f-e431bbc11c02"  # role, vocabulary
HARMONY = "019b76da-a806-7182-af38-21432633180a"
TEXTURE = "019b76da-a807-770b-bd3c-3b8d4932a2b7"
SCORE = "019b76da-a808-74c6-bd97-1031d0e2f2df"
EDITION = "019b76da-a809-70e0-91d8-70058025a2d5"
AUDIOWAVE = "019b76da-a80a-7226-8cd6-07ce294b2718"
TAGGED_HIERARCHY = "019b76da-a824-7a81-acc3-ea266958308f"
TAGGED_BEAT = "019b76da-a80d-7c73-91df-77d8fd89f661"

FORM_FIELDS = {
    "role": "form",
    "author": "Anne",
    "source": "Caplin 1998",
    "vocabulary": "lcma-form@0.3.0",
}


@pytest.fixture
def opened(qtui, tilia, tls, tmp_path):
    """Opens WP3's file of every kind, as the core writes it with `change` made to
    its document, and gives its path."""

    def _open(change=None) -> Path:
        path = written_by_the_core(EVERY_KIND, tmp_path, change)
        assert open_file(path)
        return path

    yield _open
    for window in list(TimelineFieldsWindow.open_windows()):
        with patch_question(True):
            window.close()


@pytest.fixture
def every_kind(opened) -> Path:
    return opened()


def menu_of(tluis, timeline_id):
    timeline_ui = tluis.get_timeline_ui(timeline_id)
    return timeline_ui.CONTEXT_MENU_CLASS(timeline_ui, 0, 0)


def open_fields(tluis, timeline_id) -> TimelineFieldsWindow:
    """Opens the timeline's fields window from its context menu, as a person does."""
    get_command_action(menu_of(tluis, timeline_id), "timeline.fields").trigger()
    window = TimelineFieldsWindow.of(timeline_id)
    assert window is not None
    return window


def shown(window: TimelineFieldsWindow) -> dict[str, str]:
    return {name: edit.text() for name, edit in window.line_edits.items()}


def labels(window: TimelineFieldsWindow) -> list[str]:
    layout = window.form_layout
    return [
        layout.itemAt(row, layout.ItemRole.LabelRole).widget().text()
        for row in range(layout.rowCount())
        if layout.itemAt(row, layout.ItemRole.LabelRole) is not None
    ]


def apply(window: TimelineFieldsWindow) -> None:
    window.button_box.button(QDialogButtonBox.StandardButton.Apply).click()


def cancel(window: TimelineFieldsWindow) -> None:
    window.button_box.button(QDialogButtonBox.StandardButton.Cancel).click()


UNCHANGED = object()


def edit_names(window: TimelineFieldsWindow, text) -> FieldNamesDialog:
    """Clicks "Edit fields…", types `text` in its box and clicks OK, and gives the
    box. None clicks Cancel, UNCHANGED clicks OK with nothing typed, and a function
    is given the box's text edit to edit, as a person would, before OK."""
    opened = []

    def exec_(dialog) -> bool:
        opened.append(dialog)
        if text is None:
            return False
        if callable(text):
            text(dialog.text_edit)
        elif text is not UNCHANGED:
            dialog.text_edit.setPlainText(text)
        return True

    with patch.object(FieldNamesDialog, "exec", new=exec_):
        window.edit_names_button.click()
    return opened[0]


def delete_line(number: int):
    """Deletes a line of the names' box, as selecting it to the start of the next
    and pressing Delete does."""

    def delete(text_edit) -> None:
        block = text_edit.document().findBlockByNumber(number)
        cursor = QTextCursor(block)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor
        )
        cursor.removeSelectedText()

    return delete


def replace_line(number: int, text: str):
    """Types `text` over a line of the names' box, as selecting the line's text and
    typing does."""

    def replace(text_edit) -> None:
        block = text_edit.document().findBlockByNumber(number)
        cursor = QTextCursor(block)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
        cursor.insertText(text)

    return replace


class patch_question:
    """Answers TiLiA's yes-or-no questions with `answer`, and keeps each question's
    title and text."""

    def __init__(self, answer: bool):
        self.answer_yes = answer
        self.asked: list[tuple[str, str]] = []

    def answer(self, box):
        return (
            QMessageBox.StandardButton.Yes
            if self.answer_yes
            else QMessageBox.StandardButton.No
        )

    def __enter__(self):
        made = YesOrNoMessageBox.__init__

        # The words as given: on macOS, a message box keeps no window title.
        def init(box, title, prompt, *args, **kwargs):
            made(box, title, prompt, *args, **kwargs)
            box.words = (title, prompt)

        def exec_(box):
            self.asked.append(box.words)
            return self.answer(box)

        self._patches = [
            patch.object(YesOrNoMessageBox, "__init__", new=init),
            patch.object(YesOrNoMessageBox, "exec", new=exec_),
        ]
        for patch_ in self._patches:
            patch_.__enter__()
        return self

    def __exit__(self, *args):
        for patch_ in reversed(self._patches):
            patch_.__exit__(*args)


class answer_with_enter(patch_question):
    """Answers TiLiA's yes-or-no questions as Enter does: the box shows, and Enter
    clicks the button Qt makes its default."""

    def __init__(self):
        super().__init__(answer=False)

    def answer(self, box):
        box.show()
        QTest.keyClick(box, Qt.Key.Key_Return)
        return box.standardButton(box.clickedButton())


@pytest.fixture(autouse=True)
def no_question_unanswered():
    """A question a test doesn't answer itself is answered No, and fails the test,
    rather than waiting for a click."""
    with patch_question(False) as unanswered:
        yield
    assert unanswered.asked == []


def fields_of(timeline_id: str) -> dict:
    return get(Get.TIMELINE, timeline_id).get_data("fields")


def the_core_s_with(path: Path, timeline_id: str, change) -> bytes:
    """What the core writes for `change` made to the timeline's metadata."""

    def on_doc(doc):
        change(doc.timelines[timeline_id].metadata)

    return the_core_s_bytes(path, on_doc)


def assert_saved_as_the_core_s(path: Path, timeline_id: str, change) -> None:
    expected = the_core_s_with(path, timeline_id, change)
    before = path.read_bytes()

    assert save()

    assert path.read_bytes() != before
    assert path.read_bytes() == expected


class TestTheMenu:
    @pytest.mark.parametrize(
        "timeline_id",
        [BEATS, FORM, CADENCES, HARMONY, TEXTURE, SCORE, EDITION, AUDIOWAVE],
        ids=[
            "beat",
            "hierarchy",
            "marker",
            "harmony",
            "range",
            "score",
            "pdf",
            "audiowave",
        ],
    )
    def test_every_timeline_s_menu_has_fields(self, every_kind, tluis, timeline_id):
        action = get_command_action(menu_of(tluis, timeline_id), "timeline.fields")

        assert action is not None
        assert action.text() == "Fields…"

    def test_it_opens_the_window_of_that_timeline(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        assert window.isVisible()
        assert window.windowTitle() == "Fields of Form"

    def test_twice_it_shows_the_same_window(self, every_kind, tluis):
        # A guard: while the window is open, the menu can't be reached.
        window = open_fields(tluis, FORM)

        assert open_fields(tluis, FORM) is window
        assert list(TimelineFieldsWindow.open_windows()) == [window]


class Received(QObject):
    """Counts the key and mouse button presses a window receives."""

    def __init__(self):
        super().__init__()
        self.count = 0

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress):
            self.count += 1
        return False


class TestModal:
    """Like the Metadata window (TimeLineAnnotator/project-management#634, a)."""

    def test_it_is_modal(self, every_kind, tluis):
        assert open_fields(tluis, FORM).isModal()

    def test_the_main_window_takes_no_input(self, every_kind, tluis):
        commands.execute("timeline.marker.add", time=1.5)
        markers = len(tluis.get_timeline_ui(CADENCES))
        open_fields(tluis, FORM)
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
        # TiLiA's undo didn't run.
        assert len(tluis.get_timeline_ui(CADENCES)) == markers

    def test_ctrl_z_in_a_field_undoes_the_typing(self, every_kind, tluis):
        commands.execute("timeline.marker.add", time=1.5)
        markers = len(tluis.get_timeline_ui(CADENCES))
        window = open_fields(tluis, FORM)
        author = window.line_edits["author"]
        author.setFocus()
        QTest.keyClicks(author, " typed")

        QTest.keyClick(
            window.windowHandle(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
        )

        assert author.text() == "Anne"
        assert len(tluis.get_timeline_ui(CADENCES)) == markers


class TestTheWindow:
    def test_it_shows_each_field_with_its_value_in_order(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        assert list(shown(window).items()) == list(FORM_FIELDS.items())

    def test_like_the_metadata_window_a_name_is_capitalised(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        assert labels(window) == ["Role", "Author", "Source", "Vocabulary"]

    def test_only_its_first_letter(self, opened, tluis):
        def capitals(doc):
            doc.timelines[FORM].metadata = {"BWV": "1", "bwv": "2", "über": "3"}

        opened(capitals)
        window = open_fields(tluis, FORM)

        assert labels(window) == ["BWV", "Bwv", "Über"]

    def test_a_name_is_plain_text(self, opened, tluis):
        def a_name_like_markup(doc):
            doc.timelines[FORM].metadata["<b>x</b>"] = "y"

        opened(a_name_like_markup)
        window = open_fields(tluis, FORM)

        label = window.form_layout.labelForField(window.line_edits["<b>x</b>"])
        assert label.textFormat() == Qt.TextFormat.PlainText

    def test_a_timeline_without_fields_shows_none(self, every_kind, tluis):
        window = open_fields(tluis, BARS)

        assert shown(window) == {}

    def test_a_list_shows_its_texts_separated_by_commas(self, opened, tluis):
        def a_list(doc):
            doc.timelines[FORM].metadata["keys"] = ["D minor", "F major"]

        opened(a_list)
        window = open_fields(tluis, FORM)

        assert shown(window)["keys"] == "D minor, F major"


def press(window, key, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    """Presses a key in the window: whatever has its keyboard gets it."""
    QTest.keyClick(window.windowHandle(), key, modifiers)


def has_the_keyboard(window: TimelineFieldsWindow) -> str | None:
    """The field, or the button, that a key pressed in the window goes to."""
    standard = QDialogButtonBox.StandardButton
    stops = {
        **window.line_edits,
        "Edit fields…": window.edit_names_button,
        "Cancel": window.button_box.button(standard.Cancel),
        "Apply": window.button_box.button(standard.Apply),
    }
    keyboard = window.focusWidget()
    return next((name for name, widget in stops.items() if widget is keyboard), None)


def stops_of(window: TimelineFieldsWindow, key, modifiers) -> list[str | None]:
    """Where the keyboard goes, from where it is, until it is there again."""
    found = [has_the_keyboard(window)]
    while len(found) == 1 or found[-1] != found[0]:
        press(window, key, modifiers)
        found.append(has_the_keyboard(window))
        assert len(found) < 20
    return found


def tab_stops(window: TimelineFieldsWindow) -> list[str | None]:
    return stops_of(window, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)


def put_the_keyboard_on(window: TimelineFieldsWindow, name: str) -> None:
    """Puts it on a field, as a click does. A row made after the window opened shows
    from Qt's event queue, before anyone can click it."""
    QCoreApplication.sendPostedEvents()
    window.line_edits[name].setFocus()


BUTTONS = ["Edit fields…", "Cancel", "Apply"]


class TestTheKeyboard:
    """The window opens on its first field, and Tab goes down the fields, then the
    buttons (TimeLineAnnotator/project-management#692, point 1, b)."""

    def test_the_first_field_has_it_with_its_text_selected(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        assert has_the_keyboard(window) == "role"
        assert window.line_edits["role"].selectedText() == "form"

    def test_typing_at_once_types_over_the_first_field(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        for character in "sections":
            press(window, character)

        assert shown(window) == {**FORM_FIELDS, "role": "sections"}
        assert fields_of(FORM) == FORM_FIELDS

    def test_the_space_bar_at_once_types_a_space(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        press(window, Qt.Key.Key_Space)

        assert TimelineFieldsWindow.of(FORM) is window
        assert shown(window) == {**FORM_FIELDS, "role": " "}

    def test_without_fields_edit_fields_has_it(self, every_kind, tluis):
        window = open_fields(tluis, BARS)

        assert has_the_keyboard(window) == "Edit fields…"
        assert tab_stops(window) == [*BUTTONS, "Edit fields…"]

    def test_tab_goes_down_the_fields_then_the_buttons(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        assert tab_stops(window) == [*FORM_FIELDS, *BUTTONS, "role"]

    def test_shift_tab_goes_back_up(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        back = stops_of(window, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)

        assert back == ["role", *reversed(BUTTONS), *reversed(FORM_FIELDS)]

    @pytest.mark.parametrize(
        "layout, first",
        [(0, "Cancel"), (1, "Apply"), (2, "Apply"), (3, "Apply")],
        ids=["Windows", "macOS", "KDE", "GNOME"],
    )
    def test_the_same_in_whichever_order_the_system_shows_the_buttons(
        self, every_kind, tluis, layout, first
    ):
        made = TimelineFieldsWindow._setup_window_buttons

        def laid_out_as_there(window):
            made(window)
            window.button_box.setStyleSheet(
                f"QDialogButtonBox {{ button-layout: {layout} }}"
            )

        with patch.object(
            TimelineFieldsWindow, "_setup_window_buttons", new=laid_out_as_there
        ):
            window = open_fields(tluis, FORM)

        standard = QDialogButtonBox.StandardButton
        left, _ = sorted(
            ["Cancel", "Apply"],
            key=lambda name: window.button_box.button(standard[name]).x(),
        )
        assert left == first
        assert tab_stops(window) == [*FORM_FIELDS, *BUTTONS, "role"]
        apply(window)
        put_the_keyboard_on(window, "role")
        assert tab_stops(window) == [*FORM_FIELDS, *BUTTONS, "role"]

    def test_the_same_after_apply(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")
        apply(window)
        put_the_keyboard_on(window, "role")

        assert tab_stops(window) == [*FORM_FIELDS, *BUTTONS, "role"]

    def test_the_same_with_a_field_more(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        edit_names(window, "role\nauthor\nsource\nvocabulary\nkey")
        put_the_keyboard_on(window, "role")

        assert tab_stops(window) == [*FORM_FIELDS, "key", *BUTTONS, "role"]

    def test_enter_does_nothing_wherever_it_is(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with (
            patch_question(True) as question,
            patch.object(FieldNamesDialog, "exec", return_value=False) as names,
        ):
            for _ in [*FORM_FIELDS, *BUTTONS]:
                press(window, Qt.Key.Key_Return)
                press(window, Qt.Key.Key_Tab)

        assert has_the_keyboard(window) == "role"
        assert question.asked == []
        names.assert_not_called()
        assert TimelineFieldsWindow.of(FORM) is window
        assert fields_of(FORM) == FORM_FIELDS


LONG = (
    "W. E. Caplin, Classical Form: A Theory of Formal Functions for the Instrumental "
    "Music of Haydn, Mozart, and Beethoven, New York 1998, pp. 97-123"
)


def first_shown(line_edit) -> int:
    """The place, in the text of a box it doesn't fit in, of the first character the
    box shows."""
    assert line_edit.fontMetrics().horizontalAdvance(line_edit.text()) > (
        line_edit.width()
    )
    line_edit.grab()  # a box scrolls as it draws
    return line_edit.cursorPositionAt(QPoint(0, line_edit.height() // 2))


class TestALongValue:
    """A value longer than its box shows its beginning
    (TimeLineAnnotator/project-management#692, point 2, b)."""

    @pytest.fixture(params=["first", "last"])
    def window(self, request, opened, tluis):
        fields = {"role": "form", "source": LONG}
        if request.param == "first":
            fields = dict(reversed(fields.items()))

        def long(doc):
            doc.timelines[FORM].metadata = fields

        opened(long)
        return open_fields(tluis, FORM)

    def test_when_the_window_opens(self, window):
        assert first_shown(window.line_edits["source"]) == 0

    def test_after_apply(self, window):
        window.line_edits["role"].setText("sections")

        apply(window)
        QCoreApplication.sendPostedEvents()

        assert first_shown(window.line_edits["source"]) == 0

    def test_after_apply_when_it_was_just_typed(self, window):
        put_the_keyboard_on(window, "role")
        window.line_edits["role"].selectAll()
        QTest.keyClicks(window.line_edits["role"], LONG)
        assert first_shown(window.line_edits["role"]) > 0

        apply(window)
        QCoreApplication.sendPostedEvents()

        assert first_shown(window.line_edits["role"]) == 0

    def test_the_first_one_s_whole_text_is_selected(self, opened, tluis):
        def long(doc):
            doc.timelines[FORM].metadata = {"source": LONG, "role": "form"}

        opened(long)
        window = open_fields(tluis, FORM)

        assert window.line_edits["source"].selectedText() == LONG
        press(window, "x")
        assert shown(window) == {"source": "x", "role": "form"}


def words_shown(window) -> list[str]:
    """The labels a person sees, but the fields' names."""
    QCoreApplication.sendPostedEvents()  # a row made since shows from Qt's queue
    names = labels(window)
    return [
        label.text()
        for label in window.findChildren(QLabel)
        if label.isVisible() and label.text() not in names
    ]


class TestWords:
    """What says what is what when there is little to see
    (TimeLineAnnotator/project-management#692, point 3, b)."""

    NO_FIELDS = "This timeline has no fields."

    def test_a_timeline_without_fields_says_so_above_its_button(
        self, every_kind, tluis
    ):
        window = open_fields(tluis, BARS)

        assert words_shown(window) == [self.NO_FIELDS]
        layout = window.form_layout
        (words,) = window.findChildren(QLabel)
        assert layout.indexOf(words) < layout.indexOf(window.edit_names_button)

    def test_one_with_fields_doesn_t(self, every_kind, tluis):
        assert words_shown(open_fields(tluis, FORM)) == []

    def test_they_go_with_the_first_field_and_come_back_without_one(
        self, every_kind, tluis
    ):
        window = open_fields(tluis, BARS)

        edit_names(window, "author")
        assert words_shown(window) == []

        edit_names(window, "")
        assert words_shown(window) == [self.NO_FIELDS]

    @pytest.mark.parametrize("timeline_id", [FORM, BARS], ids=["fields", "none"])
    def test_the_names_box_says_one_name_per_line_above_the_names(
        self, every_kind, tluis, timeline_id
    ):
        dialog = edit_names(open_fields(tluis, timeline_id), UNCHANGED)

        (words,) = dialog.findChildren(QLabel)
        assert words.text() == "One name per line."
        layout = dialog.layout()
        assert layout.indexOf(words) < layout.indexOf(dialog.text_edit)


class TestEditing:
    """Adding, changing and removing a field changes those lines, as the same edit
    through the core's API does."""

    def test_changing_a_field_changes_that_line(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with undoable():
            apply(window)

        assert fields_of(FORM)["author"] == "Anne-Marie"
        assert shown(window)["author"] == "Anne-Marie"

        def change(metadata):
            metadata["author"] = "Anne-Marie"

        assert_saved_as_the_core_s(every_kind, FORM, change)

    def test_adding_a_field_changes_those_lines(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        with undoable():
            edit_names(window, "role\nauthor\nsource\nvocabulary\nkey")

        assert list(shown(window)) == [*FORM_FIELDS, "key"]
        assert shown(window)["key"] == ""
        window.line_edits["key"].setText("D minor")
        apply(window)

        def change(metadata):
            metadata["key"] = "D minor"

        assert_saved_as_the_core_s(every_kind, FORM, change)

    def test_removing_a_field_changes_those_lines(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        with undoable():
            edit_names(window, "role\nauthor\nvocabulary")

        assert list(shown(window)) == ["role", "author", "vocabulary"]

        def change(metadata):
            del metadata["source"]

        assert_saved_as_the_core_s(every_kind, FORM, change)

    def test_removing_every_field(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        edit_names(window, "")

        assert fields_of(FORM) == {}

        def change(metadata):
            metadata.clear()

        assert_saved_as_the_core_s(every_kind, FORM, change)

    def test_a_field_added_to_a_timeline_without_any(self, every_kind, tluis):
        window = open_fields(tluis, BARS)

        edit_names(window, "author")
        window.line_edits["author"].setText("Felipe")
        apply(window)

        def change(metadata):
            metadata["author"] = "Felipe"

        assert_saved_as_the_core_s(every_kind, BARS, change)

    def test_a_renamed_field_keeps_its_value_and_goes_last(self, every_kind, tluis):
        # As the document places a field it hasn't held: last.
        window = open_fields(tluis, FORM)

        edit_names(window, "role\nanalyst\nsource\nvocabulary")

        assert list(fields_of(FORM).items()) == [
            ("role", "form"),
            ("source", "Caplin 1998"),
            ("vocabulary", "lcma-form@0.3.0"),
            ("analyst", "Anne"),
        ]

        def change(metadata):
            metadata["analyst"] = metadata.pop("author")

        assert_saved_as_the_core_s(every_kind, FORM, change)

    def test_a_line_typed_over_is_the_name_typed(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        edit_names(window, replace_line(1, "analyst"))

        assert list(fields_of(FORM).items()) == [
            ("role", "form"),
            ("source", "Caplin 1998"),
            ("vocabulary", "lcma-form@0.3.0"),
            ("analyst", "Anne"),
        ]

    def test_the_names_keep_their_order(self, every_kind, tluis):
        # The document keeps each field in its place: reordering the names moves none.
        window = open_fields(tluis, FORM)

        edit_names(window, "vocabulary\nsource\nauthor\nrole")

        assert list(fields_of(FORM)) == list(FORM_FIELDS)
        assert not get(Get.IS_FILE_MODIFIED)

    def test_a_name_twice_is_one_field_and_blank_lines_are_skipped(
        self, every_kind, tluis
    ):
        window = open_fields(tluis, BARS)

        edit_names(window, "author\n\n   \nauthor\n")

        assert fields_of(BARS) == {"author": ""}

    def test_a_name_typed_twice_counts_once_for_a_rename(self, every_kind, tluis):
        # Two fields replaced by one name typed twice is no rename: the list is
        # shorter, and the new field starts empty.
        window = open_fields(tluis, CADENCES)

        edit_names(window, "key\nkey")

        assert fields_of(CADENCES) == {"key": ""}

    def test_cancelled_the_names_change_nothing(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        edit_names(window, None)

        assert fields_of(FORM) == FORM_FIELDS
        assert not get(Get.IS_FILE_MODIFIED)

    def test_names_aren_t_checked(self, every_kind, tluis, tilia_errors):
        # The format takes any name, so TiLiA takes it as typed, unlike the file's
        # Metadata window, which refuses a name that isn't letters, digits and spaces.
        window = open_fields(tluis, BARS)

        edit_names(window, "x_layer\ngénéré-par\nkey (major)")

        assert list(fields_of(BARS)) == ["x_layer", "généré-par", "key (major)"]
        tilia_errors.assert_no_error()

    def test_apply_without_an_edit_changes_nothing(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        apply(window)

        assert not get(Get.IS_FILE_MODIFIED)


class TestAList:
    """A list of texts is kept a list."""

    @pytest.fixture
    def with_keys(self, opened):
        def keys(doc):
            doc.timelines[FORM].metadata["keys"] = ["D minor", "F major, briefly"]

        return opened(keys)

    def test_another_field_s_edit_keeps_it(self, with_keys, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        apply(window)

        assert fields_of(FORM)["keys"] == ["D minor", "F major, briefly"]

        def change(metadata):
            metadata["author"] = "Anne-Marie"

        assert_saved_as_the_core_s(with_keys, FORM, change)

    def test_edited_it_stays_a_list(self, with_keys, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["keys"].setText("D minor,  A major ,")

        with undoable():
            apply(window)

        assert fields_of(FORM)["keys"] == ["D minor", "A major"]

        def change(metadata):
            metadata["keys"] = ["D minor", "A major"]

        assert_saved_as_the_core_s(with_keys, FORM, change)

    def test_with_one_text_it_stays_a_list(self, with_keys, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["keys"].setText("D minor")

        apply(window)

        assert fields_of(FORM)["keys"] == ["D minor"]

    def test_a_text_with_a_comma_stays_a_text(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["source"].setText("Caplin, 1998")

        apply(window)

        assert fields_of(FORM)["source"] == "Caplin, 1998"

    def test_renamed_it_stays_a_list(self, with_keys, tluis):
        window = open_fields(tluis, FORM)

        edit_names(window, "role\nauthor\nsource\nvocabulary\ntonalities")

        assert fields_of(FORM)["tonalities"] == ["D minor", "F major, briefly"]


class TestRoleAndVocabulary:
    """`role` and `vocabulary` are fields like any other, with no check of TiLiA's own:
    what the core warns about on reading, it warns about, and writes."""

    def test_a_second_beat_timeline_s_role_time_map(
        self, every_kind, tluis, tilia_errors
    ):
        window = open_fields(tluis, BARS)
        edit_names(window, "role")
        window.line_edits["role"].setText("time_map")

        apply(window)

        tilia_errors.assert_no_error()
        assert fields_of(BARS) == {"role": "time_map"}

        def change(metadata):
            metadata["role"] = "time_map"

        assert_saved_as_the_core_s(every_kind, BARS, change)

    def test_a_vocabulary_that_isn_t_a_reference(self, every_kind, tluis, tilia_errors):
        window = open_fields(tluis, FORM)
        window.line_edits["vocabulary"].setText("Not a reference!")

        apply(window)

        tilia_errors.assert_no_error()

        def change(metadata):
            metadata["vocabulary"] = "Not a reference!"

        assert_saved_as_the_core_s(every_kind, FORM, change)


class TestUndo:
    """Undo can't run while the window is open: each test closes it first, as a
    person would."""

    def assert_undo_gives_back_the_bytes(self, path: Path, window) -> None:
        before = path.read_bytes()
        cancel(window)

        commands.execute("edit.undo")

        assert fields_of(FORM) == FORM_FIELDS
        assert save()
        assert path.read_bytes() == before

    def test_of_a_change(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["role"].setText("sections")
        apply(window)

        self.assert_undo_gives_back_the_bytes(every_kind, window)

    def test_of_a_rename(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        edit_names(window, "role\nanalyst\nsource\nvocabulary")

        self.assert_undo_gives_back_the_bytes(every_kind, window)

    def test_of_a_removal(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        edit_names(window, "role\nauthor\nvocabulary")

        self.assert_undo_gives_back_the_bytes(every_kind, window)


class TestClosing:
    """A closed window is deleted, so the tests ask whether the timeline's window is
    open rather than ask the window."""

    def test_without_edits_it_closes_without_asking(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        with patch_question(True) as question:
            cancel(window)

        assert question.asked == []
        assert TimelineFieldsWindow.of(FORM) is None

    def test_with_edits_it_asks_and_no_keeps_them(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with patch_question(False) as question:
            cancel(window)

        assert question.asked == [
            ("Save field edits", "Close window without saving changes?")
        ]
        assert TimelineFieldsWindow.of(FORM) is window
        assert window.isVisible()
        assert shown(window)["author"] == "Anne-Marie"
        assert fields_of(FORM) == FORM_FIELDS

    def test_with_edits_yes_drops_them(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with patch_question(True):
            cancel(window)

        assert TimelineFieldsWindow.of(FORM) is None
        assert fields_of(FORM) == FORM_FIELDS
        assert not get(Get.IS_FILE_MODIFIED)

    def test_escape_acts_as_cancel(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with patch_question(False) as question:
            QTest.keyClick(window.line_edits["author"], Qt.Key.Key_Escape)

        assert len(question.asked) == 1
        assert TimelineFieldsWindow.of(FORM) is window

        with patch_question(True):
            QTest.keyClick(window.line_edits["author"], Qt.Key.Key_Escape)

        assert TimelineFieldsWindow.of(FORM) is None
        assert fields_of(FORM) == FORM_FIELDS

    def test_enter_neither_applies_nor_cancels(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with (
            patch_question(True) as question,
            patch.object(FieldNamesDialog, "exec", return_value=False) as names,
        ):
            QTest.keyClick(window.line_edits["author"], Qt.Key.Key_Return)

        assert question.asked == []
        names.assert_not_called()
        assert TimelineFieldsWindow.of(FORM) is window
        assert fields_of(FORM) == FORM_FIELDS

    def test_a_closed_window_is_deleted(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        cancel(window)

        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        assert not shiboken6.isValid(window)

    def test_the_names_box_is_deleted(self, every_kind, tluis):
        dialog = edit_names(open_fields(tluis, FORM), UNCHANGED)

        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        assert not shiboken6.isValid(dialog)

    def test_enter_on_the_question_keeps_the_window_and_the_edits(
        self, every_kind, tluis
    ):
        # No is the default (TimeLineAnnotator/project-management#644, a).
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with answer_with_enter() as question:
            cancel(window)

        assert question.asked == [
            ("Save field edits", "Close window without saving changes?")
        ]
        assert TimelineFieldsWindow.of(FORM) is window
        assert shown(window)["author"] == "Anne-Marie"
        assert fields_of(FORM) == FORM_FIELDS

    def test_other_questions_keep_yes_as_their_default(self, every_kind, tluis):
        with answer_with_enter() as question:
            answer = get(Get.FROM_USER_YES_OR_NO, "Title", "Prompt?")

        assert question.asked == [("Title", "Prompt?")]
        assert answer is True

    def test_it_can_be_opened_again(self, every_kind, tluis):
        cancel(open_fields(tluis, FORM))

        again = open_fields(tluis, FORM)

        assert again.isVisible()
        assert shown(again) == FORM_FIELDS


class TestItsTimelineGoing:
    """Guards: while the window is open, TiLiA takes no input, but a file can still
    be opened, by the system for example, and the window then closes with its
    timeline, without asking."""

    def test_deleted(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with Serve(Get.FROM_USER_YES_OR_NO, True), patch_question(False) as question:
            commands.execute("timeline.delete", tluis.get_timeline_ui(FORM))

        assert question.asked == []
        assert TimelineFieldsWindow.of(FORM) is None

    def test_another_timeline_deleted_leaves_it(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        with Serve(Get.FROM_USER_YES_OR_NO, True):
            commands.execute("timeline.delete", tluis.get_timeline_ui(CADENCES))

        assert TimelineFieldsWindow.of(FORM) is window

    def test_a_new_file(self, every_kind, tluis):
        open_fields(tluis, FORM)

        post(Post.APP_CLEAR)

        assert TimelineFieldsWindow.of(FORM) is None

    def test_another_file_opened(self, every_kind, tluis, tmp_path):
        open_fields(tluis, FORM)
        other = tmp_path / "other"
        other.mkdir()

        assert open_file(written_by_the_core(EVERY_KIND, other))

        assert TimelineFieldsWindow.of(FORM) is None

    def test_an_undo_of_its_creation(self, every_kind, tluis):
        commands.execute("timelines.add.marker", name="Added")
        added = next(tlui.id for tlui in tluis if tlui.get_data("name") == "Added")
        open_fields(tluis, added)

        commands.execute("edit.undo")

        assert TimelineFieldsWindow.of(added) is None


class TestEditFieldsWithEditsNotApplied:
    """It asks, as the Metadata window does, and Yes leaves the edits unapplied
    (TimeLineAnnotator/project-management#640, point 2)."""

    def test_yes_drops_the_edits(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with patch_question(True) as question:
            edit_names(window, "role\nauthor\nsource\nvocabulary\nkey")

        assert question.asked == [
            ("Save field edits", "Leave window without saving changes?")
        ]
        assert fields_of(FORM) == {**FORM_FIELDS, "key": ""}
        assert shown(window) == {**FORM_FIELDS, "key": ""}

    def test_enter_keeps_them_and_opens_nothing(self, every_kind, tluis):
        # No is the default (TimeLineAnnotator/project-management#644, a).
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with (
            answer_with_enter() as question,
            patch.object(FieldNamesDialog, "exec") as exec_,
        ):
            window.edit_names_button.click()

        assert question.asked == [
            ("Save field edits", "Leave window without saving changes?")
        ]
        exec_.assert_not_called()
        assert shown(window)["author"] == "Anne-Marie"
        assert fields_of(FORM) == FORM_FIELDS

    def test_no_keeps_them_and_opens_nothing(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with (
            patch_question(False),
            patch.object(FieldNamesDialog, "exec") as exec_,
        ):
            window.edit_names_button.click()

        exec_.assert_not_called()
        assert shown(window)["author"] == "Anne-Marie"
        assert fields_of(FORM) == FORM_FIELDS


class TestNamesTheBoxCantShowAsTheyAre:
    """A name the box shows changed, such as one with a non-breaking space, is still
    that name; one it can't show on one line, with a line break, or empty or blank,
    isn't in the box and stays as it is (TimeLineAnnotator/project-management#640,
    point 1)."""

    NBSP = "Op.\u00a01"
    # QTextDocument's mark for the start of a frame, where the box starts a line.
    FRAME_MARK = "g" + chr(0xFDD0) + "h"

    @pytest.fixture
    def nbsp(self, opened):
        def names(doc):
            doc.timelines[FORM].metadata = {self.NBSP: "x", "BWV": "y", "bwv": "z"}

        return opened(names)

    @pytest.fixture
    def on_two_lines(self, opened):
        def names(doc):
            doc.timelines[FORM].metadata = {
                "a\nb": "v",
                "c": "w",
                "   ": "blank",
                "": "empty",
                "e\u2028f": "u",
                self.FRAME_MARK: "t",
            }

        return opened(names)

    def test_ok_with_nothing_typed_changes_nothing(self, nbsp, tluis):
        window = open_fields(tluis, FORM)

        edit_names(window, UNCHANGED)

        assert list(fields_of(FORM).items()) == [
            (self.NBSP, "x"),
            ("BWV", "y"),
            ("bwv", "z"),
        ]
        assert not get(Get.IS_FILE_MODIFIED)

    def test_another_line_s_edit_renames_nothing(self, nbsp, tluis):
        window = open_fields(tluis, FORM)

        edit_names(window, delete_line(2))

        assert list(fields_of(FORM).items()) == [(self.NBSP, "x"), ("BWV", "y")]

        def change(metadata):
            del metadata["bwv"]

        assert_saved_as_the_core_s(nbsp, FORM, change)

    def test_names_on_two_lines_or_blank_aren_t_in_the_box(self, on_two_lines, tluis):
        window = open_fields(tluis, FORM)
        given = []

        edit_names(window, lambda box: given.append(box.toPlainText()))

        assert given == ["c\n"]

    def test_their_labels_are_as_the_inspector_shows_them(self, on_two_lines, tluis):
        # A line break is a space, and an empty or blank name gives an empty or
        # blank label (TimeLineAnnotator/project-management#643, a).
        window = open_fields(tluis, FORM)

        assert labels(window) == [
            "A b",
            "C",
            "   ",
            "",
            "E f",
            "G" + self.FRAME_MARK[1:],
        ]

    def test_ok_with_nothing_typed_keeps_them(self, on_two_lines, tluis):
        window = open_fields(tluis, FORM)

        edit_names(window, UNCHANGED)

        assert not get(Get.IS_FILE_MODIFIED)

    def test_they_stay_in_their_place_when_the_others_change(self, on_two_lines, tluis):
        window = open_fields(tluis, FORM)

        edit_names(window, "key")

        assert list(fields_of(FORM).items()) == [
            ("a\nb", "v"),
            ("   ", "blank"),
            ("", "empty"),
            ("e\u2028f", "u"),
            (self.FRAME_MARK, "t"),
            ("key", "w"),
        ]

        def change(metadata):
            metadata["key"] = metadata.pop("c")

        assert_saved_as_the_core_s(on_two_lines, FORM, change)

    @pytest.mark.parametrize(
        "first, second",
        [("a b", "a" + chr(0xA0) + "b"), ("a" + chr(0xA0) + "b", "a b")],
        ids=["space first", "non-breaking space first"],
    )
    def test_of_two_that_look_the_same_the_one_deleted_goes(
        self, opened, tluis, first, second
    ):
        def names(doc):
            doc.timelines[FORM].metadata = {first: "1", second: "2"}

        path = opened(names)
        window = open_fields(tluis, FORM)

        edit_names(window, delete_line(0))

        assert fields_of(FORM) == {second: "2"}

        def change(metadata):
            del metadata[first]

        assert_saved_as_the_core_s(path, FORM, change)

    def test_every_character_the_box_starts_a_line_at_is_caught(self, qtui):
        # The characters at which the box, a QTextEdit, starts a new line, found by
        # putting each through a document, in groups, then one by one.
        document = QTextDocument()

        def starts_a_line(text: str) -> bool:
            document.setPlainText(text)
            return document.blockCount() > 1 or "\n" in document.toPlainText()

        found = []
        for start in range(0, 0x110000, 4096):
            group = [
                chr(code)
                for code in range(start, min(start + 4096, 0x110000))
                if not 0xD800 <= code <= 0xDFFF
            ]
            if starts_a_line("x".join(group)):
                found += [c for c in group if starts_a_line("a" + c + "b")]

        assert chr(0xFDD0) in found and chr(0x2029) in found
        assert [c for c in found if on_one_line("a" + c + "b")] == []


class TestTheInspector:
    """A component's fields show, read only, in its inspector: one line per field,
    and no row without fields (`contracts/controls.md`, row 10)."""

    @pytest.fixture
    def inspect(self, qtui, tluis):
        def _inspect(timeline_id, component_id):
            timeline_ui = tluis.get_timeline_ui(timeline_id)
            timeline_ui.deselect_all_elements()
            timeline_ui.select_element(timeline_ui.get_element(component_id))
            commands.execute("timeline.element.inspect")
            return qtui._windows[WindowKind.INSPECT].field_name_to_widgets["Fields"]

        yield _inspect
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def test_a_hierarchy_s_tags_and_generated_by(self, every_kind, inspect):
        label, value = inspect(FORM, TAGGED_HIERARCHY)

        assert not value.isHidden()
        assert label.text() == "Fields"
        assert value.text() == "tags: check, Satz\ngenerated_by: group/MT"

    def test_a_beat_s_tags(self, every_kind, inspect):
        _, value = inspect(BEATS, TAGGED_BEAT)

        assert not value.isHidden()
        assert value.text() == "tags: check"

    def test_no_row_without_fields(self, every_kind, tluis, inspect):
        marker = next(iter(tluis.get_timeline_ui(CADENCES).elements)).id

        label, value = inspect(CADENCES, marker)

        assert label.isHidden()
        assert value.isHidden()

    def test_the_row_goes_for_one_of_the_same_kind_without_fields(
        self, every_kind, tluis, inspect
    ):
        _, value = inspect(FORM, TAGGED_HIERARCHY)
        assert not value.isHidden()
        other = next(
            element.id
            for element in tluis.get_timeline_ui(FORM).elements
            if element.id != TAGGED_HIERARCHY
        )

        label, value = inspect(FORM, other)

        assert label.isHidden()
        assert value.isHidden()

    def test_a_component_made_in_tilia_has_none(self, every_kind, tluis, inspect):
        commands.execute("timeline.marker.add", time=1.5)
        (marker,) = [
            element
            for element in tluis.get_timeline_ui(CADENCES).elements
            if element.get_data("time") == 1.5
        ]

        _, value = inspect(CADENCES, marker.id)

        assert value.isHidden()

    def test_it_is_read_only(self, every_kind, inspect):
        _, value = inspect(FORM, TAGGED_HIERARCHY)

        assert isinstance(value, QLabel)
        assert not value.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable

    def test_a_value_is_plain_text(self, opened, inspect):
        def tags_like_markup(doc):
            component = doc.timelines[FORM].components[TAGGED_HIERARCHY]
            component.metadata = {"tags": ["<b>check</b>"]}

        opened(tags_like_markup)

        _, value = inspect(FORM, TAGGED_HIERARCHY)

        assert value.textFormat() == Qt.TextFormat.PlainText
        assert value.text() == "tags: <b>check</b>"

    def test_a_line_break_in_a_value_is_a_space(self, opened, inspect):
        def a_value_on_two_lines(doc):
            component = doc.timelines[FORM].components[TAGGED_HIERARCHY]
            component.metadata = {"note": "first\nsecond", "tags": ["a\u2028b"]}

        opened(a_value_on_two_lines)

        _, value = inspect(FORM, TAGGED_HIERARCHY)

        assert value.text() == "note: first second\ntags: a b"
