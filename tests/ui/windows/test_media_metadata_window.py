from unittest.mock import patch

import pytest

from tests.mock import patch_yes_or_no_dialog
from tilia.requests import Post, post
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
