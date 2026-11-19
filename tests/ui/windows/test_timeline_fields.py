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
from PySide6.QtCore import Qt
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
from tilia.ui.windows.timeline_fields import FieldNamesDialog, TimelineFieldsWindow

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


def edit_names(window: TimelineFieldsWindow, text: str | None) -> None:
    """Clicks "Edit fields…", types `text` in its box and clicks OK, or Cancel
    for None."""

    def exec_(dialog) -> bool:
        if text is None:
            return False
        dialog.text_edit.setPlainText(text)
        return True

    with patch.object(FieldNamesDialog, "exec", new=exec_):
        window.edit_names_button.click()


class patch_question:
    """Answers TiLiA's yes-or-no questions with `answer`, and keeps each question's
    title and text."""

    def __init__(self, answer: bool):
        self.answer = answer
        self.asked: list[tuple[str, str]] = []

    def __enter__(self):
        def exec_(box):
            self.asked.append((box.windowTitle(), box.text()))
            return (
                QMessageBox.StandardButton.Yes
                if self.answer
                else QMessageBox.StandardButton.No
            )

        self._patch = patch.object(YesOrNoMessageBox, "exec", new=exec_)
        self._patch.__enter__()
        return self

    def __exit__(self, *args):
        self._patch.__exit__(*args)


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
        window = open_fields(tluis, FORM)

        assert open_fields(tluis, FORM) is window
        assert list(TimelineFieldsWindow.open_windows()) == [window]

    def test_another_timeline_s_has_its_own(self, every_kind, tluis):
        form = open_fields(tluis, FORM)
        cadences = open_fields(tluis, CADENCES)

        assert cadences is not form
        assert cadences.windowTitle() == "Fields of Cadences"
        assert shown(form) == FORM_FIELDS


class TestTheWindow:
    def test_it_shows_each_field_with_its_value_in_order(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        assert list(shown(window).items()) == list(FORM_FIELDS.items())

    def test_like_the_metadata_window_a_name_is_capitalised(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        assert labels(window) == ["Role", "Author", "Source", "Vocabulary"]

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
    def test_undo_gives_back_the_fields_and_the_file_s_bytes(self, every_kind, tluis):
        before = every_kind.read_bytes()
        window = open_fields(tluis, FORM)
        window.line_edits["role"].setText("sections")
        apply(window)

        commands.execute("edit.undo")

        assert fields_of(FORM) == FORM_FIELDS
        assert save()
        assert every_kind.read_bytes() == before


class TestClosing:
    def test_without_edits_it_closes_without_asking(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        with patch_question(True) as question:
            cancel(window)

        assert question.asked == []
        assert TimelineFieldsWindow.of(FORM) is None
        assert not window.isVisible()

    def test_with_edits_it_asks_and_no_keeps_them(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with patch_question(False) as question:
            cancel(window)

        assert question.asked == [
            ("Save field edits", "Close window without saving changes?")
        ]
        assert window.isVisible()
        assert shown(window)["author"] == "Anne-Marie"
        assert fields_of(FORM) == FORM_FIELDS

    def test_with_edits_yes_drops_them(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with patch_question(True):
            cancel(window)

        assert not window.isVisible()
        assert fields_of(FORM) == FORM_FIELDS
        assert not get(Get.IS_FILE_MODIFIED)

    def test_escape_acts_as_cancel(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with patch_question(False) as question:
            QTest.keyClick(window.line_edits["author"], Qt.Key.Key_Escape)

        assert len(question.asked) == 1
        assert window.isVisible()

        with patch_question(True):
            QTest.keyClick(window.line_edits["author"], Qt.Key.Key_Escape)

        assert not window.isVisible()
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
        assert window.isVisible()
        assert fields_of(FORM) == FORM_FIELDS

    def test_it_can_be_opened_again(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        cancel(window)

        again = open_fields(tluis, FORM)

        assert again.isVisible()
        assert shown(again) == FORM_FIELDS

    def test_it_closes_without_asking_when_its_timeline_goes(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")

        with Serve(Get.FROM_USER_YES_OR_NO, True), patch_question(False) as question:
            commands.execute("timeline.delete", tluis.get_timeline_ui(FORM))

        assert question.asked == []
        assert not window.isVisible()
        assert TimelineFieldsWindow.of(FORM) is None

    def test_another_timeline_s_going_leaves_it(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        with Serve(Get.FROM_USER_YES_OR_NO, True):
            commands.execute("timeline.delete", tluis.get_timeline_ui(CADENCES))

        assert window.isVisible()

    def test_a_new_file_closes_it(self, every_kind, tluis):
        window = open_fields(tluis, FORM)

        post(Post.APP_CLEAR)

        assert not window.isVisible()


class TestEditFieldsWithEditsNotApplied:
    """It asks, as the Metadata window does, and Yes leaves the edits unapplied."""

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


class TestWhileItIsOpen:
    """The window isn't modal: the rest of TiLiA can change the timeline meanwhile."""

    def test_apply_writes_only_the_values_edited(self, every_kind, tluis):
        window = open_fields(tluis, FORM)
        window.line_edits["author"].setText("Anne-Marie")
        commands.execute(
            "timeline.set_fields",
            tluis.get_timeline_ui(FORM),
            {**FORM_FIELDS, "role": "sections"},
        )

        apply(window)

        assert fields_of(FORM) == {
            **FORM_FIELDS,
            "role": "sections",
            "author": "Anne-Marie",
        }
        assert shown(window)["role"] == "sections"


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
            component.metadata = {"note": "first\nsecond", "tags": ["a b"]}

        opened(a_value_on_two_lines)

        _, value = inspect(FORM, TAGGED_HIERARCHY)

        assert value.text() == "note: first second\ntags: a b"
