from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt

from tests.mock import Serve
from tests.ui.timelines.interact import (
    click_timeline_ui,
    click_timeline_ui_view,
    drag_mouse_in_timeline_view,
    press_key,
)
from tests.ui.timelines.range.interact import (
    click_end_handle,
    click_join_separator,
    click_post_end_handle,
    click_pre_start_handle,
    click_range_ui,
    click_start_handle,
)
from tests.utils import (
    assert_timeline_ui_update,
    get_action_by_object_name,
    get_command_action,
    get_command_from_toolbar,
    get_command_names,
    get_context_menu,
    get_main_window_menu,
    get_submenu,
    save_and_reopen,
    undoable,
)
from tilia.requests import Get, Post, post
from tilia.settings import settings
from tilia.ui import commands
from tilia.ui.commands import get_qaction
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.range import RangeTimelineUI
from tilia.ui.timelines.range.context_menu import (
    RangeContextMenu,
)
from tilia.ui.timelines.range.drag import _row_at_y
from tilia.ui.timelines.range.element import RangeCommentsIcon
from tilia.ui.windows.kinds import WindowKind


def get_timeline_context_menu_for_row(range_tlui, row_index=0):
    y = int(range_tlui.default_row_height * (row_index + 1) / 2)
    with patch.object(
        range_tlui, "get_row_by_y", return_value=range_tlui.rows[row_index]
    ):
        return get_context_menu(range_tlui, 0, y)


def add_and_join_ranges(range_tlui, segments):
    """Add ranges at the given (start, end) segments and join them.

    Returns the list of created RangeUI elements. Use this when the join is
    *fixture* for a test — when the test asserts on join behavior itself,
    keep the calls inline so the test reads on its own.
    """
    for start, end in segments:
        commands.execute("timeline.range.add_range", start=start, end=end)
    elements = list(range_tlui)
    for elem in elements:
        range_tlui.select_element(elem)
    commands.execute("timeline.range.join_ranges")
    return elements


class TestCreateDeleteTimeline:
    def test_create_single(self, tluis):
        with undoable():
            commands.execute("timelines.add.range", name="")

        assert len(tluis) == 1

    def test_create_multiple(self, tluis):
        commands.execute("timelines.add.range", name="")
        commands.execute("timelines.add.range", name="")

        assert len(tluis) == 2

    def test_delete(self, tluis):
        commands.execute("timelines.add.range", name="")
        with undoable():
            commands.execute("timeline.delete", tluis[0], confirm=False)

        assert tluis.is_empty


class TestRowLabels:
    def test_labels_displayed_after_row_created(self, range_tlui):
        assert len(range_tlui.row_labels) == 1
        assert range_tlui.rows[0].id in range_tlui.row_labels

        with assert_timeline_ui_update(range_tlui, "rows"):
            commands.execute("timeline.range.add_row")

        assert len(range_tlui.row_labels) == 2
        assert range_tlui.rows[1].id in range_tlui.row_labels

    def test_labels_deleted_after_row_deleted(self, range_tlui):
        commands.execute("timeline.range.add_row")
        assert len(range_tlui.row_labels) == 2

        row_to_delete = range_tlui.rows[1]

        with assert_timeline_ui_update(range_tlui, "rows"):
            commands.execute("timeline.range.remove_row", row=row_to_delete)

        assert len(range_tlui.row_labels) == 1
        assert row_to_delete.id not in range_tlui.row_labels


class TestRenameRow:
    def test_with_command(self, range_tlui):
        row = range_tlui.rows[0]
        with assert_timeline_ui_update(range_tlui, "rows"):
            commands.execute("timeline.range.rename_row", row=row, new_name="New Name")
        assert range_tlui.rows[0].name == "New Name"


def assert_range(range_tlui, index: int, **kwargs):
    for attr, value in kwargs.items():
        assert range_tlui[index].get_data(attr) == value


class TestCreateDeleteComponent:
    def test_create_with_command(self, range_tlui, tluis, tilia_state):
        with undoable():
            commands.execute(
                "timeline.range.add_range", start=1, end=10, row=range_tlui.rows[0]
            )

        assert len(range_tlui) == 1
        assert range_tlui[0].get_data("start") == 1
        assert range_tlui[0].get_data("end") == 10

    def test_create_with_toolbar(self, range_tlui):
        commands.execute("media.seek", 10)
        action = get_command_from_toolbar(range_tlui, "timeline.range.add_range")
        action.trigger()
        assert len(range_tlui) == 1
        assert_range(range_tlui, 0, start=10)

    def test_create_at_selected_time(self, range_tlui, use_test_settings):
        commands.execute("media.seek", 10)
        commands.execute("timeline.range.add_range")
        assert len(range_tlui) == 1
        assert_range(
            range_tlui,
            0,
            start=10,
            end=10 + settings.get("range_timeline", "default_range_size"),
        )

    def test_create_with_shortcut(self, range_tlui):
        click_timeline_ui(range_tlui, 0)
        commands.execute("media.seek", 10)
        press_key("r")
        assert len(range_tlui) == 1
        assert_range(range_tlui, 0, start=10)

    def test_create_at_selected_time_caps_at_media_duration(
        self, range_tlui, use_test_settings, tilia_state
    ):
        tilia_state.set_duration(10, scale_timelines="yes")
        settings.set("range_timeline", "default_range_size", 10)
        commands.execute("media.seek", 9)
        commands.execute("timeline.range.add_range")
        assert_range(range_tlui, 0, start=9, end=10)

    def test_create_at_end_fails(self, range_tlui, tilia_state):
        tilia_state.set_duration(100, scale_timelines="yes")
        commands.execute("media.seek", 100)
        commands.execute("timeline.range.add_range")
        assert len(range_tlui) == 0

    def test_create_overlap_success(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=5, end=15)

        assert len(range_tlui) == 2

    def test_delete(self, range_tlui):
        commands.execute("timeline.range.add_range")
        r1 = range_tlui[0]
        click_range_ui(r1)

        commands.execute("timeline.component.delete")
        assert len(range_tlui) == 0

        commands.execute("edit.undo")
        assert len(range_tlui) == 1

    def test_delete_multiple(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=20, end=30)

        assert len(range_tlui) == 2

        # Select both
        click_range_ui(range_tlui[0])
        click_range_ui(range_tlui[1], modifier="ctrl")

        with undoable():
            commands.execute("timeline.component.delete")
            assert len(range_tlui) == 0


class TestSaveLoad:
    def test_empty_timeline(self, tilia, tluis, tilia_state, tmp_path):
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]

        commands.execute(
            "timeline.range.rename_row", row=range_tlui.rows[0], new_name="row"
        )

        save_and_reopen(tmp_path)

        assert len(tluis) == 2  # Slider timeline + Range timeline
        assert tluis[0].get_data("name") == "range"
        assert tluis[0].rows[0].name == "row"

    def test_single_row_with_components(self, tilia, tluis, tilia_state, tmp_path):
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]

        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=1.0, end=5.0
        )

        save_and_reopen(tmp_path)

        assert len(tluis) == 2
        loaded_range_tlui = tluis[0]

        assert len(loaded_range_tlui.rows) == 1
        assert len(loaded_range_tlui) == 1
        assert loaded_range_tlui[0].get_data("start") == 1.0
        assert loaded_range_tlui[0].get_data("end") == 5.0
        assert loaded_range_tlui[0].get_data("row_id") == loaded_range_tlui.rows[0].id

    def test_multiple_rows_with_components(self, tilia, tluis, tilia_state, tmp_path):
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]

        # Add a second row
        commands.execute("timeline.range.add_row")
        assert len(range_tlui.rows) == 2

        # Add ranges
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=1.0, end=5.0
        )
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[1], start=6.0, end=10.0
        )

        save_and_reopen(tmp_path)

        assert len(tluis) == 2
        loaded_range_tlui = tluis[0]

        # Verify rows
        assert len(loaded_range_tlui.rows) == 2

        # Verify components
        assert len(loaded_range_tlui) == 2

        # Check that one component is in row 0 and another is in row 1
        c1 = [c for c in loaded_range_tlui if c.get_data("start") == 1.0][0]
        c2 = [c for c in loaded_range_tlui if c.get_data("start") == 6.0][0]

        assert c1.get_data("end") == 5.0
        assert c1.get_data("row_id") == loaded_range_tlui.rows[0].id

        assert c2.get_data("end") == 10.0
        assert c2.get_data("row_id") == loaded_range_tlui.rows[1].id

    def test_empty_rows_preserved(self, tilia, tluis, tilia_state, tmp_path):
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]

        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_row")
        assert len(range_tlui.rows) == 3  # rows with no components

        save_and_reopen(tmp_path)

        loaded = tluis[0]
        assert len(loaded.rows) == 3
        assert len(loaded) == 0

    def test_duplicate_row_names_preserved(self, tilia, tluis, tilia_state, tmp_path):
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]

        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.rename_row", row=range_tlui.rows[0], new_name="same"
        )
        commands.execute(
            "timeline.range.rename_row", row=range_tlui.rows[1], new_name="same"
        )

        save_and_reopen(tmp_path)

        loaded = tluis[0]
        assert len(loaded.rows) == 2
        assert loaded.rows[0].name == "same"
        assert loaded.rows[1].name == "same"
        assert loaded.rows[0].id != loaded.rows[1].id

    def test_row_order_preserved(self, tilia, tluis, tilia_state, tmp_path):
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]

        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.rename_row", row=range_tlui.rows[0], new_name="first"
        )
        commands.execute(
            "timeline.range.rename_row", row=range_tlui.rows[1], new_name="second"
        )
        commands.execute(
            "timeline.range.rename_row", row=range_tlui.rows[2], new_name="third"
        )

        save_and_reopen(tmp_path)

        loaded = tluis[0]
        assert [r.name for r in loaded.rows] == ["first", "second", "third"]

    def test_row_color_preserved(self, tilia, tluis, tilia_state, tmp_path):
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]

        commands.execute(
            "timeline.range.set_row_color",
            row=range_tlui.rows[0],
            color="#123456",
        )

        save_and_reopen(tmp_path)

        loaded = tluis[0]
        assert loaded.rows[0].color == "#123456"


class TestJoinRanges:
    def test_join_two_ranges(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=25, end=35)
        r1, r2 = range_tlui[0], range_tlui[1]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        with undoable():
            commands.execute("timeline.range.join_ranges")
            assert r1.get_data("end") == 25  # gap filled

    def test_join_with_shortcut(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=25, end=35)
        r1, r2 = range_tlui[0], range_tlui[1]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        press_key("j")
        assert r1.get_data("joined_right") == r2.id

    def test_join_three_ranges(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=20, end=30)
        commands.execute("timeline.range.add_range", start=40, end=50)
        r1, r2, r3 = range_tlui[0], range_tlui[1], range_tlui[2]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        click_range_ui(r3, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        assert r1.get_data("end") == 20
        assert r2.get_data("end") == 40

    def test_join_adjacent_ranges_is_noop(self, range_tlui):
        # Ranges already touching: join succeeds but nothing changes
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=20, end=30)
        r1, r2 = range_tlui[0], range_tlui[1]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        assert r1.get_data("end") == 20
        assert r2.get_data("start") == 20

    def test_join_fails_with_single_range(self, range_tlui, tilia_errors):
        commands.execute("timeline.range.add_range", start=10, end=20)
        click_range_ui(range_tlui[0])
        commands.execute("timeline.range.join_ranges")
        tilia_errors.assert_error()

    def test_join_fails_across_rows(self, range_tlui, tilia_errors):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute(
            "timeline.range.add_range",
            row=range_tlui.rows[1],
            start=25,
            end=35,
        )
        click_range_ui(range_tlui[0])
        click_range_ui(range_tlui[1], modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        tilia_errors.assert_error()

    def test_join_fails_when_overlapping(self, range_tlui, tilia_errors):
        commands.execute("timeline.range.add_range", start=10, end=25)
        commands.execute("timeline.range.add_range", start=20, end=35)
        click_range_ui(range_tlui[0])
        click_range_ui(range_tlui[1], modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        tilia_errors.assert_error()

    def test_join_fails_with_no_selection(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        result = commands.execute("timeline.range.join_ranges")
        assert not result

    def test_join_sets_joined_right_link(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=25, end=35)
        r1, r2 = range_tlui[0], range_tlui[1]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        assert r1.get_data("joined_right") == r2.id
        assert r2.get_data("joined_right") is None

    def test_join_chain_sets_links(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=20, end=30)
        commands.execute("timeline.range.add_range", start=40, end=50)
        r1, r2, r3 = range_tlui[0], range_tlui[1], range_tlui[2]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        click_range_ui(r3, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        assert r1.get_data("joined_right") == r2.id
        assert r2.get_data("joined_right") == r3.id
        assert r3.get_data("joined_right") is None

    def test_join_already_adjacent_sets_link_without_changing_times(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=20, end=30)
        r1, r2 = range_tlui[0], range_tlui[1]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        assert r1.get_data("joined_right") == r2.id

    def test_join_undo_clears_link(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=25, end=35)
        click_range_ui(range_tlui[0])
        click_range_ui(range_tlui[1], modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        commands.execute("edit.undo")
        assert range_tlui[0].get_data("joined_right") is None
        assert range_tlui[0].get_data("end") == 20  # gap restored

    def test_undo_post_end_change_preserves_join(self, range_tlui):
        # Regression: changing post_end on the right of a joined pair and
        # then undoing used to break the join. The base restore_state
        # deletes-and-recreates the right range (its hash changed), and
        # the range timeline's delete cascade cleared the join on the
        # untouched left range as a side effect.
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=20, end=30)
        r1, r2 = range_tlui[0], range_tlui[1]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        assert r1.get_data("joined_right") == r2.id

        with undoable():
            range_tlui.timeline.set_component_data(r2.id, "post_end", 35)
            post(Post.APP_STATE_RECORD, "post_end change")

    def test_delete_joined_partner_clears_link(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=25, end=35)
        r1, r2 = range_tlui[0], range_tlui[1]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")

        click_range_ui(r2)
        commands.execute("timeline.component.delete")
        assert r1.get_data("joined_right") is None

    def test_delete_middle_of_chain_breaks_both_links(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=20, end=30)
        commands.execute("timeline.range.add_range", start=40, end=50)
        r1, r2, r3 = range_tlui[0], range_tlui[1], range_tlui[2]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        click_range_ui(r3, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")

        click_range_ui(r2)
        commands.execute("timeline.component.delete")
        assert r1.get_data("joined_right") is None
        assert r3.get_data("joined_right") is None

    def test_save_load_preserves_join_state(self, tilia, tluis, tilia_state, tmp_path):
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=10, end=20
        )
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=25, end=35
        )
        range_tlui.select_element(range_tlui[0])
        range_tlui.select_element(range_tlui[1])
        commands.execute("timeline.range.join_ranges")

        save_and_reopen(tmp_path)

        loaded = tluis[0]
        assert loaded[0].get_data("joined_right") == loaded[1].id

        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)

    def test_save_load_preserves_join_with_advanced_id_counter(
        self, tilia, tluis, tilia_state, tmp_path
    ):
        # Regression: joined ranges loaded from a file used to lose their join
        # links because component IDs were re-assigned on deserialize while
        # `joined_right` still held pre-save IDs. The bug was masked when the
        # fresh ID counter happened to land on the same numbers; this test
        # advances the counter so saved IDs and fresh IDs cannot coincide.
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]

        for _ in range(5):
            commands.execute(
                "timeline.range.add_range", row=range_tlui.rows[0], start=0, end=5
            )
            range_tlui.select_element(range_tlui[0])
            commands.execute("timeline.component.delete")

        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=10, end=20
        )
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=25, end=35
        )
        range_tlui.select_element(range_tlui[0])
        range_tlui.select_element(range_tlui[1])
        commands.execute("timeline.range.join_ranges")

        saved_r1_id = range_tlui[0].id
        saved_r2_id = range_tlui[1].id

        save_and_reopen(tmp_path)

        loaded = tluis[0]
        assert loaded[0].id == saved_r1_id
        assert loaded[1].id == saved_r2_id
        assert loaded[0].get_data("joined_right") == loaded[1].id

        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)

    def test_drag_joined_edge_after_file_load_moves_partner(
        self, tilia, tluis, tilia_state, tmp_path
    ):
        # Regression: dragging the shared edge of joined ranges loaded from
        # a file used to leave the partner behind because the partner lookup
        # in drag.py used pre-save IDs that no longer matched the fresh IDs
        # assigned at deserialize.
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]

        # Advance the ID counter so saved IDs and fresh post-load IDs cannot
        # coincide; otherwise the bug above is masked.
        for _ in range(5):
            commands.execute(
                "timeline.range.add_range", row=range_tlui.rows[0], start=0, end=5
            )
            range_tlui.select_element(range_tlui[0])
            commands.execute("timeline.component.delete")

        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=10, end=20
        )
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=20, end=30
        )
        range_tlui.select_element(range_tlui[0])
        range_tlui.select_element(range_tlui[1])
        commands.execute("timeline.range.join_ranges")

        save_and_reopen(tmp_path)

        loaded = tluis[0]
        click_end_handle(loaded[0])
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(15), 0)
        assert loaded[0].get_data("end") == 15
        assert loaded[1].get_data("start") == 15

        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)


class TestSeparateRanges:
    def test_separate_breaks_link(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=25, end=35)
        r1, r2 = range_tlui[0], range_tlui[1]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        assert r1.get_data("joined_right") == r2.id

        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        commands.execute("timeline.range.separate_ranges")
        assert r1.get_data("joined_right") is None

    def test_separate_partial_chain_isolates_selection(self, range_tlui):
        # Chain A→B→C; select only B and separate. All three become independent.
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=20, end=30)
        commands.execute("timeline.range.add_range", start=40, end=50)
        r1, r2, r3 = range_tlui[0], range_tlui[1], range_tlui[2]
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        click_range_ui(r3, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")

        click_range_ui(r2)
        commands.execute("timeline.range.separate_ranges")
        assert r1.get_data("joined_right") is None
        assert r2.get_data("joined_right") is None
        assert r3.get_data("joined_right") is None

    def test_separate_no_selection_returns_false(self, range_tlui):
        result = commands.execute("timeline.range.separate_ranges")
        assert not result

    def test_separate_undo_restores_link(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=25, end=35)
        click_range_ui(range_tlui[0])
        click_range_ui(range_tlui[1], modifier="ctrl")
        commands.execute("timeline.range.join_ranges")

        click_range_ui(range_tlui[0])
        click_range_ui(range_tlui[1], modifier="ctrl")
        commands.execute("timeline.range.separate_ranges")
        commands.execute("edit.undo")
        assert range_tlui[0].get_data("joined_right") == range_tlui[1].id

    def test_separate_nudges_extremities_apart(self, range_tlui):
        # After joining, A.end == B.start. Separating should pull both away
        # from the shared edge by the same amount, leaving a small gap.
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])
        join_point = r1.get_data("end")
        assert join_point == r2.get_data("start")

        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        commands.execute("timeline.range.separate_ranges")

        new_left_end = r1.get_data("end")
        new_right_start = r2.get_data("start")
        assert new_left_end < join_point
        assert new_right_start > join_point
        # Symmetric nudge: midpoint stays at the original join point.
        assert new_left_end + new_right_start == pytest.approx(2 * join_point)


class TestRangeLabel:
    def test_short_label_not_truncated(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=300)
        range_tlui[0].set_data("label", "ok")
        assert range_tlui[0].label.toPlainText() == "ok"

    def test_long_label_elided_into_short_range(self, range_tlui):
        # A 1-second range is a few pixels wide; a long label cannot fit and
        # must be elided ("Word…" rather than overflowing the body).
        commands.execute("timeline.range.add_range", start=0, end=1)
        range_tlui[0].set_data("label", "A label far too long to ever fit")
        rendered = range_tlui[0].label.toPlainText()
        assert rendered != "A label far too long to ever fit"
        assert "…" in rendered or rendered == ""

    def test_label_re_elides_after_resize(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=1)
        long_label = "A label far too long to ever fit"
        range_tlui[0].set_data("label", long_label)
        elided_short = range_tlui[0].label.toPlainText()

        # Widen the range; the label should reflow to show more characters.
        range_tlui[0].set_data("end", 600)
        elided_wide = range_tlui[0].label.toPlainText()
        assert len(elided_wide) > len(elided_short)


class TestJoinedDrag:
    def test_drag_end_of_left_range_moves_partner_start(self, range_tlui, tilia_state):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])

        click_end_handle(r1)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(15), 0)
        assert r1.get_data("end") == 15
        assert r2.get_data("start") == 15

    def test_drag_start_of_right_range_moves_partner_end(self, range_tlui, tilia_state):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])

        click_start_handle(r2)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(25), 0)
        assert r1.get_data("end") == 25
        assert r2.get_data("start") == 25

    def test_drag_joined_edge_clamped_at_left_range_start(
        self, range_tlui, tilia_state
    ):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])

        click_end_handle(r1)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(0), 0)
        assert r1.get_data("end") > r1.get_data("start")
        assert r2.get_data("start") == r1.get_data("end")

    def test_drag_joined_edge_clamped_at_right_range_end(self, range_tlui, tilia_state):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])

        click_end_handle(r1)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(50), 0)
        assert r2.get_data("start") < r2.get_data("end")
        assert r1.get_data("end") == r2.get_data("start")

    def test_drag_unjoined_handle_after_separate_works_normally(
        self, range_tlui, tilia_state
    ):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])
        commands.execute("timeline.range.separate_ranges")

        original_r2_start = r2.get_data("start")
        click_end_handle(r1)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(15), 0)
        assert r1.get_data("end") == 15
        assert r2.get_data("start") == original_r2_start


class TestJoinSeparatorVisibility:
    def test_separator_hidden_by_default(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        assert not range_tlui[0].join_separator.isVisible()

    def test_separator_visible_after_join(self, range_tlui):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (25, 35)])
        assert r1.join_separator.isVisible()
        assert not r2.join_separator.isVisible()  # tail of chain has no outgoing link

    def test_separator_hidden_after_separate(self, range_tlui):
        r1, _ = add_and_join_ranges(range_tlui, [(10, 20), (25, 35)])
        commands.execute("timeline.range.separate_ranges")
        assert not r1.join_separator.isVisible()


class TestJoinedHandleVisibility:
    def test_handles_opaque_by_default(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        r = range_tlui[0]
        assert r.start_handle.brush().color().alpha() == 255
        assert r.end_handle.brush().color().alpha() == 255

    def test_joined_edge_handles_transparent(self, range_tlui):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])
        # The shared edge: r1.end_handle and r2.start_handle.
        assert r1.end_handle.brush().color().alpha() == 0
        assert r2.start_handle.brush().color().alpha() == 0
        # The outer edges remain opaque so users can drag them.
        assert r1.start_handle.brush().color().alpha() == 255
        assert r2.end_handle.brush().color().alpha() == 255

    def test_handles_restored_after_separate(self, range_tlui):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])
        commands.execute("timeline.range.separate_ranges")
        assert r1.end_handle.brush().color().alpha() == 255
        assert r2.start_handle.brush().color().alpha() == 255

    def test_joined_edge_handles_remain_clickable(self, range_tlui, tilia_state):
        # Regression: with NoBrush handles the click was falling through to
        # the body underneath, starting a selection box instead of a drag.
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])

        click_end_handle(r1)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(15), 0)
        # Drag succeeded only if both edges moved together.
        assert r1.get_data("end") == 15
        assert r2.get_data("start") == 15

    def test_click_on_join_separator_starts_drag(self, range_tlui, tilia_state):
        # Regression: clicking exactly on the dashed separator (z=20, on top
        # of the handles) used to miss `left_click_triggers` and fall through
        # to the timeline scene, starting a rubber-band selection. The
        # separator is now treated as a drag trigger for the shared edge.
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])

        click_join_separator(r1)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(15), 0)
        assert r1.get_data("end") == 15
        assert r2.get_data("start") == 15

    def test_handles_transparent_after_file_load(
        self, tilia, tluis, tilia_state, tmp_path
    ):
        # Regression: on file open, the right side of a join could be created
        # before the left side. When that happens, the right side's
        # `has_incoming_join` check found no element pointing to it yet, so
        # its start_handle stayed opaque and covered the dashed separator.
        commands.execute("timelines.add.range", name="range")
        range_tlui = tluis[0]
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=10, end=20
        )
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[0], start=20, end=30
        )
        range_tlui.select_element(range_tlui[0])
        range_tlui.select_element(range_tlui[1])
        commands.execute("timeline.range.join_ranges")

        save_and_reopen(tmp_path)

        loaded = tluis[0]
        assert loaded[0].end_handle.brush().color().alpha() == 0
        assert loaded[1].start_handle.brush().color().alpha() == 0

        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)


class TestCopyPaste:
    def test_paste_single_into_timeline(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=0, end=10)
        range_tlui[0].set_data("label", "copy me")
        click_range_ui(range_tlui[0])
        commands.execute("timeline.component.copy")

        click_timeline_ui(range_tlui, 200)  # deselect
        commands.execute("media.seek", 50)
        commands.execute("timeline.component.paste")

        assert len(range_tlui) == 2
        pasted = range_tlui[1]
        assert pasted.get_data("start") == 50
        assert pasted.get_data("end") == 60
        assert pasted.get_data("label") == "copy me"

    def test_paste_single_into_selected_element(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=20, end=30)
        range_tlui[0].set_data("label", "source")
        click_range_ui(range_tlui[0])
        commands.execute("timeline.component.copy")

        click_range_ui(range_tlui[1])
        commands.execute("timeline.component.paste")

        assert len(range_tlui) == 2
        assert range_tlui[1].get_data("label") == "source"
        # Paste-into-selected does not change start/end.
        assert range_tlui[1].get_data("start") == 20
        assert range_tlui[1].get_data("end") == 30

    def test_paste_multiple_into_timeline(self, range_tlui, tilia_state):
        tilia_state.set_duration(300, scale_timelines="no")
        commands.execute("timeline.range.add_range", start=0, end=5)
        commands.execute("timeline.range.add_range", start=10, end=20)
        range_tlui[0].set_data("label", "first")
        range_tlui[1].set_data("label", "second")
        click_range_ui(range_tlui[0])
        click_range_ui(range_tlui[1], modifier="ctrl")
        commands.execute("timeline.component.copy")

        click_timeline_ui(range_tlui, 400)  # deselect
        commands.execute("media.seek", 100)
        commands.execute("timeline.component.paste")

        assert len(range_tlui) == 4
        # Pasted ranges land relative to selected time, preserving spacing.
        assert range_tlui[2].get_data("start") == 100
        assert range_tlui[2].get_data("end") == 105
        assert range_tlui[2].get_data("label") == "first"
        assert range_tlui[3].get_data("start") == 110
        assert range_tlui[3].get_data("end") == 120
        assert range_tlui[3].get_data("label") == "second"

    def test_pasted_range_alone_drops_external_join(self, range_tlui, tilia_state):
        # If only one side of a join is pasted, the partner is not in the
        # batch, so the pasted range cannot recreate the link.
        r1, r2 = add_and_join_ranges(range_tlui, [(0, 10), (10, 20)])
        click_range_ui(r1)
        commands.execute("timeline.component.copy")

        click_timeline_ui(range_tlui, 400)
        commands.execute("media.seek", 50)
        commands.execute("timeline.component.paste")

        assert range_tlui[2].get_data("joined_right") is None

    def test_paste_joined_pair_into_timeline_keeps_join(self, range_tlui, tilia_state):
        tilia_state.set_duration(300, scale_timelines="no")
        r1, r2 = add_and_join_ranges(range_tlui, [(0, 10), (10, 20)])
        click_range_ui(r1)
        click_range_ui(r2, modifier="ctrl")
        commands.execute("timeline.component.copy")

        click_timeline_ui(range_tlui, 400)
        commands.execute("media.seek", 100)
        commands.execute("timeline.component.paste")

        assert len(range_tlui) == 4
        pasted_left = range_tlui[2]
        pasted_right = range_tlui[3]
        assert pasted_left.get_data("joined_right") == pasted_right.id
        assert pasted_right.get_data("joined_right") is None

    def test_paste_drops_ranges_outside_media_bounds(self, range_tlui, tilia_state):
        # Media is 100s by default. Pasting a 10s-wide range at 95s would
        # push the end past media duration → rejected by validator.
        commands.execute("timeline.range.add_range", start=0, end=10)
        click_range_ui(range_tlui[0])
        commands.execute("timeline.component.copy")

        click_timeline_ui(range_tlui, 400)
        commands.execute("media.seek", 95)
        commands.execute("timeline.component.paste")
        assert len(range_tlui) == 1  # paste rejected, no new component

    def test_paste_drops_only_out_of_bounds_member(self, range_tlui, tilia_state):
        # In a multi-range paste batch, an out-of-bounds member should be
        # skipped without aborting the whole paste — the in-bounds member
        # should still land.
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=80, end=90)
        click_range_ui(range_tlui[0])
        click_range_ui(range_tlui[1], modifier="ctrl")
        commands.execute("timeline.component.copy")

        click_timeline_ui(range_tlui, 400)  # deselect
        # Reference time = 0; pasting at 20 maps the first range to [20, 30]
        # (in bounds) and the second to [100, 110] (end past media duration).
        commands.execute("media.seek", 20)
        commands.execute("timeline.component.paste")

        assert len(range_tlui) == 3  # 2 originals + 1 successfully pasted
        starts = sorted(r.get_data("start") for r in range_tlui)
        assert starts == [0, 20, 80]


class TestMoveToRow:
    def test_move_to_row_above(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_range", start=0, end=10)
        r = range_tlui[0]
        # Created on row 0; move to row 1 first to have somewhere to go up from.
        commands.execute("timeline.range.move_to_row_below", elements=[r])
        target_row_id = r.get_data("row_id")
        commands.execute("timeline.range.move_to_row_above", elements=[r])
        assert r.get_data("row_id") != target_row_id
        assert r.get_data("row_id") == range_tlui.rows[0].id

    def test_move_to_row_below(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_range", start=0, end=10)
        r = range_tlui[0]
        original_row_id = r.get_data("row_id")
        commands.execute("timeline.range.move_to_row_below", elements=[r])
        assert r.get_data("row_id") != original_row_id
        assert r.get_data("row_id") == range_tlui.rows[1].id

    def test_move_to_row_above_at_top_fails(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        r = range_tlui[0]
        original_row_id = r.get_data("row_id")
        result = commands.execute("timeline.range.move_to_row_above", elements=[r])
        assert not result
        assert r.get_data("row_id") == original_row_id

    def test_move_to_row_below_at_bottom_fails(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        r = range_tlui[0]
        original_row_id = r.get_data("row_id")
        result = commands.execute("timeline.range.move_to_row_below", elements=[r])
        assert not result
        assert r.get_data("row_id") == original_row_id

    def test_move_carries_joined_partners(self, range_tlui):
        commands.execute("timeline.range.add_row")
        r1, r2 = add_and_join_ranges(range_tlui, [(0, 10), (10, 20)])
        commands.execute("timeline.range.move_to_row_below", elements=[r1])
        target_row_id = range_tlui.rows[1].id
        assert r1.get_data("row_id") == target_row_id
        assert r2.get_data("row_id") == target_row_id

    def test_move_carries_full_chain_when_middle_selected(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=20, end=30)
        r1, r2, r3 = list(range_tlui)
        for e in (r1, r2, r3):
            range_tlui.select_element(e)
        commands.execute("timeline.range.join_ranges")

        commands.execute("timeline.range.move_to_row_below", elements=[r2])
        target_row_id = range_tlui.rows[1].id
        assert r1.get_data("row_id") == target_row_id
        assert r2.get_data("row_id") == target_row_id
        assert r3.get_data("row_id") == target_row_id

    def test_move_to_row_undo_restores_row(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_range", start=0, end=10)
        original_row_id = range_tlui[0].get_data("row_id")
        commands.execute("timeline.range.move_to_row_below", elements=[range_tlui[0]])
        commands.execute("edit.undo")
        assert range_tlui[0].get_data("row_id") == original_row_id

    def test_move_to_row_above_via_keypress(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_range", start=0, end=10)
        r = range_tlui[0]
        commands.execute("timeline.range.move_to_row_below", elements=[r])
        range_tlui.select_element(r)
        post(Post.TIMELINE_KEY_PRESS_CTRL_UP)
        assert r.get_data("row_id") == range_tlui.rows[0].id

    def test_move_to_row_below_via_keypress(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_range", start=0, end=10)
        r = range_tlui[0]
        range_tlui.select_element(r)
        post(Post.TIMELINE_KEY_PRESS_CTRL_DOWN)
        assert r.get_data("row_id") == range_tlui.rows[1].id


class TestRangeElementContextMenu:
    def test_default_items_present(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        menu = RangeContextMenu(range_tlui[0])
        names = get_command_names(menu)
        for expected in (
            "timeline.element.inspect",
            "timeline.component.set_color",
            "timeline.component.reset_color",
            "timeline.component.copy",
            "timeline.component.paste",
            "timeline.component.delete",
        ):
            assert expected in names

    def test_join_hidden_when_only_one_selected(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=20, end=30)
        range_tlui.select_element(range_tlui[0])
        menu = RangeContextMenu(range_tlui[0])
        assert "timeline.range.join_ranges" not in get_command_names(menu)

    def test_join_shown_when_two_selected_in_same_row(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        commands.execute("timeline.range.add_range", start=20, end=30)
        range_tlui.select_element(range_tlui[0])
        range_tlui.select_element(range_tlui[1])
        menu = RangeContextMenu(range_tlui[0])
        assert "timeline.range.join_ranges" in get_command_names(menu)

    def test_join_hidden_when_selection_spans_rows(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.add_range",
            row=range_tlui.rows[0],
            start=0,
            end=10,
        )
        commands.execute(
            "timeline.range.add_range",
            row=range_tlui.rows[1],
            start=0,
            end=10,
        )
        range_tlui.select_element(range_tlui[0])
        range_tlui.select_element(range_tlui[1])
        menu = RangeContextMenu(range_tlui[0])
        assert "timeline.range.join_ranges" not in get_command_names(menu)

    def test_move_above_hidden_at_top_row(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        menu = RangeContextMenu(range_tlui[0])
        assert "timeline.range.move_to_row_above" not in get_command_names(menu)

    def test_move_below_hidden_at_bottom_row(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        menu = RangeContextMenu(range_tlui[0])
        assert "timeline.range.move_to_row_below" not in get_command_names(menu)

    def test_move_above_shown_when_row_above_exists(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.add_range",
            row=range_tlui.rows[1],
            start=0,
            end=10,
        )
        menu = RangeContextMenu(range_tlui[0])
        assert "timeline.range.move_to_row_above" in get_command_names(menu)

    def test_move_below_shown_when_row_below_exists(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.add_range",
            row=range_tlui.rows[0],
            start=0,
            end=10,
        )
        menu = RangeContextMenu(range_tlui[0])
        assert "timeline.range.move_to_row_below" in get_command_names(menu)

    def test_move_above_via_menu_changes_row(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.add_range",
            row=range_tlui.rows[1],
            start=0,
            end=10,
        )
        r = range_tlui[0]
        range_tlui.select_element(r)
        menu = RangeContextMenu(r)
        action = get_command_action(menu, "timeline.range.move_to_row_above")
        action.trigger()
        assert r.get_data("row_id") == range_tlui.rows[0].id

    def test_is_shown_on_right_click(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        with patch.object(RangeContextMenu, "exec") as mock:
            click_range_ui(range_tlui[0], button="right")
        mock.assert_called_once()


class TestUndoRowOperations:
    def test_undo_add_row_restores_height(self, range_tlui):
        initial_height = range_tlui.view.height()
        commands.execute("timeline.range.add_row")
        assert range_tlui.view.height() > initial_height  # direct path works
        commands.execute("edit.undo")
        assert range_tlui.view.height() == initial_height

    def test_redo_add_row_updates_height(self, range_tlui):
        commands.execute("timeline.range.add_row")
        two_row_height = range_tlui.view.height()
        commands.execute("edit.undo")
        commands.execute("edit.redo")
        assert range_tlui.view.height() == two_row_height

    def test_undo_remove_row_restores_height(self, range_tlui):
        commands.execute("timeline.range.add_row")
        two_row_height = range_tlui.view.height()
        commands.execute("timeline.range.remove_row", row=range_tlui.rows[1])
        commands.execute("edit.undo")
        assert range_tlui.view.height() == two_row_height

    def test_undo_add_row_above_restores_element_positions(self, range_tlui):
        # Range in row 0 (y=0). Add a row above (idx=0) pushes it to row 1.
        # After undo the range must be back at row 0 (y=0).
        commands.execute("timeline.range.add_range", start=10, end=20)
        r = range_tlui[0]
        assert r.body.rect().y() == range_tlui.row_y(0)

        commands.execute("timeline.range.add_row", idx=0)
        assert r.body.rect().y() == range_tlui.row_y(1)  # direct path correct

        commands.execute("edit.undo")
        assert r.body.rect().y() == range_tlui.row_y(0)  # regression

    def test_undo_remove_row_above_restores_element_positions(self, range_tlui):
        # Range in row 1. Remove row 0 (above it) moves it to row 0.
        # After undo the range must be back at row 1.
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[1], start=10, end=20
        )
        r = range_tlui[0]
        assert r.body.rect().y() == range_tlui.row_y(1)

        commands.execute("timeline.range.remove_row", row=range_tlui.rows[0])
        assert r.body.rect().y() == range_tlui.row_y(0)  # direct path correct

        commands.execute("edit.undo")
        assert r.body.rect().y() == range_tlui.row_y(1)  # regression

    def test_undo_remove_row_with_ranges_restores_ranges(self, range_tlui):
        # Removing a row deletes its ranges. Undo must restore them
        # AND associate them with the restored row.
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[1], start=10, end=20
        )
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[1], start=30, end=40
        )
        original_row_id = range_tlui.rows[1].id
        assert len(range_tlui) == 2

        commands.execute("timeline.range.remove_row", row=range_tlui.rows[1])
        assert len(range_tlui) == 0
        assert len(range_tlui.rows) == 1

        commands.execute("edit.undo")
        assert len(range_tlui.rows) == 2
        assert len(range_tlui) == 2
        # Both ranges should be in the restored row
        for r in range_tlui:
            assert r.get_data("row_id") == original_row_id

    def test_redo_remove_row_with_ranges_deletes_ranges(self, range_tlui):
        # Sanity: redo of a row remove must not leave orphan ranges.
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[1], start=10, end=20
        )
        commands.execute("timeline.range.remove_row", row=range_tlui.rows[1])
        commands.execute("edit.undo")
        commands.execute("edit.redo")
        assert len(range_tlui) == 0
        assert len(range_tlui.rows) == 1


class TestRowHighlight:
    @staticmethod
    def assert_is_at_row(range_tlui, row_index: int):
        highlight_y1 = range_tlui.row_highlight.rect().y()
        highlight_y2 = highlight_y1 + range_tlui.row_highlight.rect().height()
        row_y1 = range_tlui.row_y(row_index)
        row_y2 = row_y1 + range_tlui.default_row_height
        assert highlight_y1 == row_y1
        assert highlight_y2 == row_y2

    def test_initial_row_is_highlighted(self, range_tlui):
        assert range_tlui.row_highlight
        self.assert_is_at_row(range_tlui, 0)

    def test_changes_row_when_row_is_clicked(self, range_tlui):
        commands.execute("timeline.range.add_row")
        click_timeline_ui_view(range_tlui.view, "left", 50, range_tlui.row_y(1) + 10)
        self.assert_is_at_row(range_tlui, 1)

    @pytest.mark.skip("not implemented")
    def test_ignores_right_clicks(self, range_tlui):
        # I wasn't able to find a low-level way to simulate a right click.
        # I get a QtWarningMsg: Mouse event "MousePress" not accepted by receiving widget
        # See this: https://github.com/pytest-dev/pytest-qt/issues/428
        # And this: https://github.com/pytest-dev/pytest-qt/pull/429

        # from PySide6.QtTest import QTest
        # QTest.mouseClick(range_tlui.view, Qt.MouseButton.RightButton)
        pass

    def test_creating_other_range_timeline_deletes_highlight(self, tluis):
        commands.execute("timelines.add.range", name="")
        commands.execute("timelines.add.range", name="")
        tlui1, tlui2 = tluis[0], tluis[1]
        assert tlui1.row_highlight is None
        assert tlui2.row_highlight

    def test_clicking_other_range_timeline_deletes_highlight(self, tluis):
        commands.execute("timelines.add.range", name="")
        commands.execute("timelines.add.range", name="")
        tlui1, tlui2 = tluis[0], tluis[1]
        click_timeline_ui(tlui1, 1)
        assert tlui1.row_highlight
        assert tlui2.row_highlight is None


class TestAddRow:
    @staticmethod
    def _trigger_action(range_tlui: RangeTimelineUI, action):
        with undoable():
            with assert_timeline_ui_update(range_tlui, "rows"):
                action.trigger()

    _get_context_menu_for_row_index = staticmethod(get_timeline_context_menu_for_row)

    def test_above_first_row(self, range_tlui: RangeTimelineUI):
        row_to_click = range_tlui.rows[0]
        context_menu = self._get_context_menu_for_row_index(range_tlui, 0)

        action = get_action_by_object_name(context_menu, "add row above")
        assert action

        self._trigger_action(range_tlui, action)

        assert len(range_tlui.rows) == 2
        assert (
            range_tlui.rows[1] == row_to_click
        )  # row was created above, so row_to_click is second

    def test_below_first_row(self, range_tlui: RangeTimelineUI):
        row_to_click = range_tlui.rows[0]
        context_menu = self._get_context_menu_for_row_index(range_tlui, 0)

        action = get_action_by_object_name(context_menu, "add row below")
        assert action

        self._trigger_action(range_tlui, action)

        assert len(range_tlui.rows) == 2
        assert (
            range_tlui.rows[0] == row_to_click
        )  # row was created below, so row_to_click is still first

    def test_above_second_row(self, range_tlui: RangeTimelineUI):
        commands.execute("timeline.range.add_row")

        row_to_click = range_tlui.rows[1]
        context_menu = self._get_context_menu_for_row_index(range_tlui, 1)

        action = get_action_by_object_name(context_menu, "add row above")
        assert action

        self._trigger_action(range_tlui, action)

        assert len(range_tlui.rows) == 3
        assert (
            range_tlui.rows[2] == row_to_click
        )  # row was created above, so row_to_click is now third

    def test_below_second_row(self, range_tlui: RangeTimelineUI):
        commands.execute("timeline.range.add_row")

        row_to_click = range_tlui.rows[1]
        context_menu = self._get_context_menu_for_row_index(range_tlui, 1)

        action = get_action_by_object_name(context_menu, "add row below")
        assert action

        self._trigger_action(range_tlui, action)

        assert len(range_tlui.rows) == 3
        assert (
            range_tlui.rows[1] == row_to_click
        )  # row was created below, so row_to_click is still second


class TestTimelineContextMenu:
    _menu = staticmethod(get_timeline_context_menu_for_row)

    def test_no_set_height_action(self, range_tlui):
        menu = self._menu(range_tlui)
        assert get_qaction("timeline.set_height") not in menu.actions()

    def test_has_set_row_height_action(self, range_tlui):
        menu = self._menu(range_tlui)
        assert get_action_by_object_name(menu, "set default row height") is not None

    def test_set_default_row_height_appears_before_separator(self, range_tlui):
        # "Set default row height" should be in the topmost section, alongside
        # "Set name", before the first separator.
        menu = self._menu(range_tlui)
        names_until_separator = []
        for action in menu.actions():
            if action.isSeparator():
                break
            names_until_separator.append(action.objectName())
        assert "set default row height" in names_until_separator

    def test_move_timeline_up_down_in_top_section(self, tluis):
        # Move up/down should sit with Set name in the top section, before
        # the first separator, and use "Move timeline …" labels.
        commands.execute("timelines.add.range", name="A")
        commands.execute("timelines.add.range", name="B")
        commands.execute("timelines.add.range", name="C")
        ranges = sorted(
            (t for t in tluis if isinstance(t, RangeTimelineUI)),
            key=lambda t: t.get_data("ordinal"),
        )
        # The middle timeline can move both up and down.
        menu = get_timeline_context_menu_for_row(ranges[1], 0)
        labels_until_separator = []
        for action in menu.actions():
            if action.isSeparator():
                break
            labels_until_separator.append(action.text())
        assert "Move timeline up" in labels_until_separator
        assert "Move timeline down" in labels_until_separator

    def test_set_row_height_via_context_menu(self, range_tlui):
        menu = self._menu(range_tlui)
        action = get_action_by_object_name(menu, "set default row height")
        with Serve(Get.FROM_USER_INT, (True, 60)):
            action.trigger()
        assert range_tlui.timeline.default_row_height == 60
        assert range_tlui.default_row_height == 60

    def test_set_row_height_cancel_keeps_value(self, range_tlui):
        menu = self._menu(range_tlui)
        action = get_action_by_object_name(menu, "set default row height")
        with Serve(Get.FROM_USER_INT, (False, 0)):
            action.trigger()
        assert range_tlui.timeline.default_row_height is None

    def test_rename_row_via_context_menu(self, range_tlui):
        menu = self._menu(range_tlui)
        action = get_action_by_object_name(menu, "rename row")
        assert action is not None
        with Serve(Get.FROM_USER_STRING, (True, "Renamed")):
            action.trigger()
        assert range_tlui.rows[0].name == "Renamed"

    def test_rename_row_command_no_kwargs_does_not_error(self, range_tlui):
        # Regression: on_rename_row used to call ask_for_string with only a
        # title, which is a missing-argument error.
        with Serve(Get.FROM_USER_STRING, (True, "OK")):
            commands.execute("timeline.range.rename_row", row=range_tlui.rows[0])
        assert range_tlui.rows[0].name == "OK"

    def test_remove_row_via_context_menu(self, range_tlui):
        commands.execute("timeline.range.add_row")
        assert len(range_tlui.rows) == 2
        menu = self._menu(range_tlui, row_index=1)
        action = get_action_by_object_name(menu, "remove row")
        assert action is not None
        action.trigger()
        assert len(range_tlui.rows) == 1

    def test_set_timeline_name_updates_label(self, range_tlui):
        # Setting timeline name should propagate to the scene label that
        # shows the timeline name in the left margin. (Short name to avoid
        # the label's elide-to-fit behavior.)
        menu = self._menu(range_tlui)
        action = get_command_action(menu, "timeline.set_name")
        with Serve(Get.FROM_USER_STRING, (True, "abc")):
            action.trigger()
        assert range_tlui.get_data("name") == "abc"
        assert range_tlui.scene.text.toPlainText() == "abc"


class TestRowColorPropagation:
    def test_range_inherits_row_color_when_color_is_none(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        assert range_tlui[0].get_data("color") is None
        commands.execute(
            "timeline.range.set_row_color",
            row=range_tlui.rows[0],
            color="#ff0000",
        )
        assert range_tlui[0].body.brush().color().name() == "#ff0000"

    def test_range_with_explicit_color_ignores_row_color(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        range_tlui[0].set_data("color", "#00ff00")
        commands.execute(
            "timeline.range.set_row_color",
            row=range_tlui.rows[0],
            color="#ff0000",
        )
        assert range_tlui[0].body.brush().color().name() == "#00ff00"

    def test_range_inherits_color_after_moving_to_other_row(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.set_row_color",
            row=range_tlui.rows[1],
            color="#0000ff",
        )
        commands.execute(
            "timeline.range.add_range",
            row=range_tlui.rows[0],
            start=0,
            end=10,
        )
        commands.execute("timeline.range.move_to_row_below", elements=[range_tlui[0]])
        assert range_tlui[0].body.brush().color().name() == "#0000ff"


class TestResetRowColor:
    def test_clears_explicit_row_color(self, range_tlui):
        row = range_tlui.rows[0]
        commands.execute("timeline.range.set_row_color", row=row, color="#ff0000")
        assert row.color == "#ff0000"
        commands.execute("timeline.range.reset_row_color", row=row)
        assert row.color is None

    def test_falls_back_to_default_setting(self, range_tlui):
        row = range_tlui.rows[0]
        commands.execute("timeline.range.add_range", row=row, start=0, end=10)
        commands.execute("timeline.range.set_row_color", row=row, color="#ff0000")
        settings.set("range_timeline", "default_range_color", "#123456")
        commands.execute("timeline.range.reset_row_color", row=row)
        # range body color should now reflect the default setting (alpha-applied
        # color names omit alpha when it's 255 by default; just check the rgb part)
        assert range_tlui[0].body.brush().color().name() == "#123456"

    def test_no_op_when_color_already_none(self, range_tlui, tilia_errors):
        row = range_tlui.rows[0]
        assert row.color is None
        commands.execute("timeline.range.reset_row_color", row=row)
        assert row.color is None
        tilia_errors.assert_no_error()

    def test_context_menu_action_present_when_color_set(self, range_tlui):
        row = range_tlui.rows[0]
        commands.execute("timeline.range.set_row_color", row=row, color="#ff0000")
        menu = get_timeline_context_menu_for_row(range_tlui, 0)
        assert "Reset row color" in [a.text() for a in menu.actions()]

    def test_context_menu_action_hidden_when_no_color(self, range_tlui):
        menu = get_timeline_context_menu_for_row(range_tlui, 0)
        assert "Reset row color" not in [a.text() for a in menu.actions()]

    def test_undo_preserves_selected_row(self, range_tlui):
        # Regression: undoing a row-color change used to leave selected_row
        # pointing at a stale Row instance (state restore rebuilds the Row
        # list), so the selection visibly snapped to the first row.
        commands.execute("timeline.range.add_row")
        target_row = range_tlui.rows[1]
        range_tlui.selected_row = target_row
        target_id = target_row.id
        commands.execute(
            "timeline.range.set_row_color", row=target_row, color="#ff0000"
        )
        commands.execute("edit.undo")
        assert range_tlui.selected_row is not None
        assert range_tlui.selected_row.id == target_id
        assert range_tlui.selected_row in range_tlui.timeline.rows


class TestRowHeight:
    def test_default_falls_back_to_settings(self, range_tlui):
        assert range_tlui.timeline.default_row_height is None
        assert range_tlui.default_row_height == settings.get(
            "range_timeline", "default_row_height"
        )

    def test_set_row_height_command(self, range_tlui):
        with Serve(Get.FROM_USER_INT, (True, 60)):
            commands.execute("timeline.range.set_row_height")
        assert range_tlui.default_row_height == 60

    def test_set_row_height_updates_element_position(self, range_tlui):
        # Pin the starting height explicitly so the assertion below holds
        # regardless of whatever value an earlier test left in QSettings.
        settings.set("range_timeline", "default_row_height", 30)
        commands.execute("timeline.range.add_row")
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[1], start=0, end=10
        )
        original_y = range_tlui[0].body.rect().y()
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute("timeline.range.set_row_height")
        assert range_tlui[0].body.rect().y() != original_y

    def test_set_row_height_updates_row_label_position(self, range_tlui):
        settings.set("range_timeline", "default_row_height", 30)
        commands.execute("timeline.range.add_row")
        # The label for row at index 1 sits at row_y(1) - 2; if row_height
        # changes, that y must change too.
        label = range_tlui.row_labels[range_tlui.rows[1].id]
        original_y = label.y()
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute("timeline.range.set_row_height")
        assert label.y() != original_y

    def test_set_row_height_no_crash_when_highlight_cleared(self, range_tlui):
        # Reproduces the AttributeError that surfaced when this timeline's
        # row highlight had been removed (e.g. another range timeline took
        # focus) and the user then changed row height from the context menu.
        range_tlui._delete_row_highlight()
        assert range_tlui.row_highlight is None
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute("timeline.range.set_row_height")
        assert range_tlui.default_row_height == 80

    def test_set_row_height_resizes_range_body(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute("timeline.range.set_row_height")
        assert range_tlui[0].body.rect().height() == 80

    def test_set_row_height_to_same_value_does_not_error(
        self, range_tlui, tilia_errors
    ):
        original = range_tlui.default_row_height
        with Serve(Get.FROM_USER_INT, (True, original)):
            commands.execute("timeline.range.set_row_height")
        assert range_tlui.default_row_height == original
        tilia_errors.assert_no_error()

    def test_save_load_preserves_row_height(self, tilia, tluis, tilia_state, tmp_path):
        commands.execute("timelines.add.range", name="range")
        with Serve(Get.FROM_USER_INT, (True, 75)):
            commands.execute("timeline.range.set_row_height")

        save_and_reopen(tmp_path)

        assert tluis[0].timeline.default_row_height == 75
        assert tluis[0].default_row_height == 75
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)

    def test_label_font_uses_default_size_when_row_height_is_large(self, range_tlui):
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute("timeline.range.set_row_height")
        label = range_tlui.row_labels[range_tlui.rows[0].id]
        assert label.font().pixelSize() == range_tlui.DEFAULT_LABEL_PIXEL_SIZE

    def test_label_font_shrinks_when_row_height_is_small(self, range_tlui):
        with Serve(Get.FROM_USER_INT, (True, 10)):
            commands.execute("timeline.range.set_row_height")
        label = range_tlui.row_labels[range_tlui.rows[0].id]
        assert label.font().pixelSize() < range_tlui.DEFAULT_LABEL_PIXEL_SIZE
        assert label.font().pixelSize() >= range_tlui.MIN_LABEL_PIXEL_SIZE

    def test_label_font_does_not_shrink_below_min(self, range_tlui):
        # Per-row heights bypass the timeline-wide validator's >=10 floor,
        # so they can drop low enough to exercise the MIN clamp.
        range_tlui.timeline.set_row_height(range_tlui.rows[0], 1)
        label = range_tlui.row_labels[range_tlui.rows[0].id]
        assert label.font().pixelSize() == range_tlui.MIN_LABEL_PIXEL_SIZE

    def test_per_row_height_drives_label_font_size(self, range_tlui):
        commands.execute("timeline.range.add_row")
        small_row = range_tlui.rows[1]
        range_tlui.timeline.set_row_height(small_row, 8)
        small_label = range_tlui.row_labels[small_row.id]
        default_label = range_tlui.row_labels[range_tlui.rows[0].id]
        assert small_label.font().pixelSize() < default_label.font().pixelSize()


class TestBodyDrag:
    def test_drag_body_right(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=20, end=40)
        r = range_tlui[0]
        click_range_ui(r)
        # First drag event captures click offset (no movement). Second moves.
        center_x = time_x_converter.get_x_by_time(30)
        target_x = time_x_converter.get_x_by_time(60)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(target_x, 0)
        assert r.get_data("start") == 50
        assert r.get_data("end") == 70

    def test_drag_body_left(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=40, end=60)
        r = range_tlui[0]
        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(50)
        target_x = time_x_converter.get_x_by_time(20)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(target_x, 0)
        # Delta = target - center = -30. Range shifts by -30 in time.
        assert r.get_data("start") == 10
        assert r.get_data("end") == 30

    def test_drag_body_clamped_at_left_margin(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=10, end=20)
        r = range_tlui[0]
        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(15)
        # Drag far past the left margin.
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(-1000, 0)
        assert r.get_data("start") == 0
        assert r.get_data("end") == 10  # duration preserved

    def test_drag_body_clamped_at_right_margin(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=10, end=20)
        r = range_tlui[0]
        duration = r.get_data("end") - r.get_data("start")
        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(15)
        # Drag far past the right margin.
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(100_000, 0)
        media_duration = tilia_state.duration
        assert r.get_data("end") == pytest.approx(media_duration)
        assert r.get_data("start") == pytest.approx(media_duration - duration)

    def test_drag_body_undo(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=20, end=40)
        r = range_tlui[0]
        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(30)
        target_x = time_x_converter.get_x_by_time(60)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(target_x, 0)
        commands.execute("edit.undo")
        assert range_tlui[0].get_data("start") == 20
        assert range_tlui[0].get_data("end") == 40

    def test_drag_body_of_joined_left_carries_partner(self, range_tlui, tilia_state):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])
        click_range_ui(r1)
        ref_x = time_x_converter.get_x_by_time(15)
        target_x = time_x_converter.get_x_by_time(25)
        drag_mouse_in_timeline_view(ref_x, 0, release=False)
        drag_mouse_in_timeline_view(target_x, 0)
        # delta = +10
        assert r1.get_data("start") == 20
        assert r1.get_data("end") == 30
        assert r2.get_data("start") == 30
        assert r2.get_data("end") == 40

    def test_drag_body_of_joined_right_carries_partner(self, range_tlui, tilia_state):
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])
        click_range_ui(r2)
        ref_x = time_x_converter.get_x_by_time(25)
        target_x = time_x_converter.get_x_by_time(15)
        drag_mouse_in_timeline_view(ref_x, 0, release=False)
        drag_mouse_in_timeline_view(target_x, 0)
        # delta = -10
        assert r1.get_data("start") == 0
        assert r1.get_data("end") == 10
        assert r2.get_data("start") == 10
        assert r2.get_data("end") == 20

    def test_joined_chain_clamped_at_left_margin(self, range_tlui, tilia_state):
        # Chain [10,20]→[20,30]; dragging the right range left far enough
        # would push the LEFT range past the left margin. Clamp must keep
        # the chain leftmost (r1) at LEFT_MARGIN.
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])
        click_range_ui(r2)
        ref_x = time_x_converter.get_x_by_time(25)
        drag_mouse_in_timeline_view(ref_x, 0, release=False)
        drag_mouse_in_timeline_view(-10000, 0)
        assert r1.get_data("start") == 0
        assert r2.get_data("end") == 20  # 10 + 10 (chain duration preserved)

    def test_joined_chain_clamped_at_right_margin(self, range_tlui, tilia_state):
        # Chain [10,20]→[20,30]; dragging the left range right far enough
        # would push the RIGHT range past the right margin. Clamp must keep
        # the chain rightmost (r2) at RIGHT_MARGIN.
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])
        click_range_ui(r1)
        ref_x = time_x_converter.get_x_by_time(15)
        drag_mouse_in_timeline_view(ref_x, 0, release=False)
        drag_mouse_in_timeline_view(100_000, 0)
        media_duration = tilia_state.duration
        assert r2.get_data("end") == pytest.approx(media_duration)
        assert r1.get_data("start") == pytest.approx(media_duration - 20)


class TestMultipleRangeTimelines:
    @staticmethod
    def _add_two_range_timelines(tluis):
        commands.execute("timelines.add.range", name="A")
        commands.execute("timelines.add.range", name="B")
        return tluis[0], tluis[1]

    def test_two_independent_timelines(self, tluis):
        a, b = self._add_two_range_timelines(tluis)
        assert a is not b
        assert a.timeline is not b.timeline
        assert len(a.rows) == 1
        assert len(b.rows) == 1

    def test_add_row_only_affects_clicked_timeline(self, tluis):
        a, b = self._add_two_range_timelines(tluis)
        click_timeline_ui(a, 1)
        commands.execute("timeline.range.add_row")
        assert len(a.rows) == 2
        assert len(b.rows) == 1

        click_timeline_ui(b, 1)
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_row")
        assert len(a.rows) == 2
        assert len(b.rows) == 3

    def test_add_range_only_affects_clicked_timeline(self, tluis):
        a, b = self._add_two_range_timelines(tluis)
        click_timeline_ui(a, 1)
        commands.execute("timeline.range.add_range", start=10, end=20)
        assert len(a) == 1
        assert len(b) == 0

        click_timeline_ui(b, 1)
        commands.execute("timeline.range.add_range", start=30, end=40)
        assert len(a) == 1
        assert len(b) == 1
        assert a[0].get_data("start") == 10
        assert b[0].get_data("start") == 30

    def test_clicking_row_in_one_clears_highlight_in_other(self, tluis):
        a, b = self._add_two_range_timelines(tluis)
        # B was created last → b has the highlight, a does not.
        assert a.row_highlight is None
        assert b.row_highlight is not None

        click_timeline_ui(a, 1)
        assert a.row_highlight is not None
        assert b.row_highlight is None

        click_timeline_ui(b, 1)
        assert a.row_highlight is None
        assert b.row_highlight is not None

    def test_save_load_two_range_timelines(self, tilia, tluis, tilia_state, tmp_path):
        a, b = self._add_two_range_timelines(tluis)

        click_timeline_ui(a, 1)
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.rename_row", row=a.rows[0], new_name="a-row-0")
        commands.execute("timeline.range.rename_row", row=a.rows[1], new_name="a-row-1")
        commands.execute("timeline.range.add_range", row=a.rows[0], start=10, end=20)

        click_timeline_ui(b, 1)
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)
        commands.execute("timeline.range.rename_row", row=b.rows[0], new_name="b-row-0")
        commands.execute("timeline.range.add_range", row=b.rows[0], start=30, end=40)
        commands.execute("timeline.range.add_range", row=b.rows[0], start=50, end=60)

        save_and_reopen(tmp_path)

        # Slider + 2 range timelines
        assert len(tluis) == 3
        loaded = [t for t in tluis if isinstance(t, RangeTimelineUI)]
        loaded_a = next(t for t in loaded if t.get_data("name") == "A")
        loaded_b = next(t for t in loaded if t.get_data("name") == "B")

        assert [r.name for r in loaded_a.rows] == ["a-row-0", "a-row-1"]
        assert len(loaded_a) == 1
        assert loaded_a[0].get_data("start") == 10
        assert loaded_a[0].get_data("end") == 20

        assert [r.name for r in loaded_b.rows] == ["b-row-0"]
        assert len(loaded_b) == 2
        starts = sorted(r.get_data("start") for r in loaded_b)
        assert starts == [30, 50]


class TestSettings:
    # use_test_settings (auto-applied via the qtui fixture) routes settings
    # writes to a dedicated test QSettings store, so per-test snapshots are
    # not needed — each test sets the values it relies on explicitly.

    def test_row_height_setting_changes_row_height(self, range_tlui):
        original = range_tlui.default_row_height
        settings.set("range_timeline", "default_row_height", original + 50)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        assert range_tlui.default_row_height == original + 50

    def test_row_height_setting_updates_timeline_height(self, range_tlui):
        original_total = range_tlui.height
        settings.set(
            "range_timeline", "default_row_height", range_tlui.default_row_height + 30
        )
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        assert range_tlui.height == original_total + 30

    def test_row_height_setting_resizes_highlight(self, range_tlui):
        settings.set("range_timeline", "default_row_height", 80)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        assert range_tlui.row_highlight.rect().height() == 80

    def test_per_timeline_row_height_overrides_setting(self, range_tlui):
        commands.execute("timeline.range.set_row_height", height=120)
        settings.set("range_timeline", "default_row_height", 50)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        # Per-timeline override wins.
        assert range_tlui.default_row_height == 120

    def test_default_range_color_setting_updates_element_color(self, range_tlui):
        # New rows store color=None and fall back to the default-range-color
        # setting, so changing it should immediately repaint existing ranges.
        commands.execute("timeline.range.add_range", start=10, end=20)
        new_color = "#112233"
        settings.set("range_timeline", "default_range_color", new_color)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        body_color = range_tlui[0].body.brush().color()
        assert body_color.red() == 0x11
        assert body_color.green() == 0x22
        assert body_color.blue() == 0x33

    def test_range_alpha_setting_updates_element_alpha(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        settings.set("range_timeline", "range_alpha", 200)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        assert range_tlui[0].body.brush().color().alpha() == 200

    def test_handle_color_setting_updates_handle_fill(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        settings.set("range_timeline", "handle_color", "#ff8800")
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        handle_color = range_tlui[0].start_handle.brush().color()
        assert handle_color.red() == 0xFF
        assert handle_color.green() == 0x88
        assert handle_color.blue() == 0x00

    def test_handle_width_setting_updates_handle_rect(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        settings.set("range_timeline", "handle_width", 12)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        assert range_tlui[0].start_handle.rect().width() == 12


class TestVerticalBodyDrag:
    @staticmethod
    def _two_row_setup(range_tlui):
        commands.execute("timeline.range.add_row")
        return range_tlui.rows[0], range_tlui.rows[1]

    def test_drag_body_to_row_below(self, range_tlui):
        row_a, row_b = self._two_row_setup(range_tlui)
        commands.execute("timeline.range.add_range", row=row_a, start=20, end=40)
        r = range_tlui[0]
        assert r.get_data("row_id") == row_a.id

        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(30)
        # First drag captures click offset.
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        # Drag straight down into row_b.
        target_y = range_tlui.row_y(1) + range_tlui.default_row_height // 2
        drag_mouse_in_timeline_view(center_x, target_y)
        assert r.get_data("row_id") == row_b.id

    def test_drag_body_to_row_above(self, range_tlui):
        row_a, row_b = self._two_row_setup(range_tlui)
        commands.execute("timeline.range.add_range", row=row_b, start=20, end=40)
        r = range_tlui[0]
        assert r.get_data("row_id") == row_b.id

        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(30)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        target_y = range_tlui.row_y(0) + range_tlui.default_row_height // 2
        drag_mouse_in_timeline_view(center_x, target_y)
        assert r.get_data("row_id") == row_a.id

    def test_drag_above_top_clamps_to_first_row(self, range_tlui):
        row_a, row_b = self._two_row_setup(range_tlui)
        commands.execute("timeline.range.add_range", row=row_b, start=20, end=40)
        r = range_tlui[0]
        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(30)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(center_x, -1000)
        assert r.get_data("row_id") == row_a.id

    def test_drag_below_bottom_clamps_to_last_row(self, range_tlui):
        row_a, row_b = self._two_row_setup(range_tlui)
        commands.execute("timeline.range.add_range", row=row_a, start=20, end=40)
        r = range_tlui[0]
        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(30)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(center_x, 100_000)
        assert r.get_data("row_id") == row_b.id

    def test_horizontal_drag_keeps_row(self, range_tlui):
        row_a, _ = self._two_row_setup(range_tlui)
        commands.execute("timeline.range.add_range", row=row_a, start=20, end=40)
        r = range_tlui[0]
        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(30)
        target_x = time_x_converter.get_x_by_time(60)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        # Y stays at 0 (within row 0) — row should not change.
        drag_mouse_in_timeline_view(target_x, 0)
        assert r.get_data("row_id") == row_a.id

    def test_undo_restores_row(self, range_tlui):
        row_a, row_b = self._two_row_setup(range_tlui)
        commands.execute("timeline.range.add_range", row=row_a, start=20, end=40)
        r = range_tlui[0]
        click_range_ui(r)
        center_x = time_x_converter.get_x_by_time(30)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        target_y = range_tlui.row_y(1) + range_tlui.default_row_height // 2
        drag_mouse_in_timeline_view(center_x, target_y)
        assert r.get_data("row_id") == row_b.id
        commands.execute("edit.undo")
        assert range_tlui[0].get_data("row_id") == row_a.id

    def test_drag_carries_joined_chain_to_new_row(self, range_tlui):
        row_a, row_b = self._two_row_setup(range_tlui)
        r1, r2 = add_and_join_ranges(range_tlui, [(10, 20), (20, 30)])
        # Both joined ranges live in row_a.
        assert r1.get_data("row_id") == row_a.id
        assert r2.get_data("row_id") == row_a.id

        click_range_ui(r1)
        center_x = time_x_converter.get_x_by_time(15)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        target_y = range_tlui.row_y(1) + range_tlui.default_row_height // 2
        drag_mouse_in_timeline_view(center_x, target_y)
        assert r1.get_data("row_id") == row_b.id
        assert r2.get_data("row_id") == row_b.id


class TestArrowNavigation:
    @staticmethod
    def _add_range(range_tlui, start, end, row=None):
        before = {e.id for e in range_tlui}
        kwargs = {"start": start, "end": end}
        if row is not None:
            kwargs["row"] = row
        commands.execute("timeline.range.add_range", **kwargs)
        new = [e for e in range_tlui if e.id not in before]
        return new[0]

    @staticmethod
    def _press(arrow):
        request = {
            "up": Post.TIMELINE_KEY_PRESS_UP,
            "down": Post.TIMELINE_KEY_PRESS_DOWN,
        }[arrow]
        post(request)

    def test_no_op_without_selection(self, range_tlui):
        commands.execute("timeline.range.add_row")
        self._add_range(range_tlui, 10, 20, range_tlui.rows[0])
        self._add_range(range_tlui, 30, 40, range_tlui.rows[1])
        self._press("down")
        assert not range_tlui.selected_elements

    def test_down_into_overlapping_range_picks_closest_center(self, range_tlui):
        commands.execute("timeline.range.add_row")
        ref = self._add_range(range_tlui, 20, 40, range_tlui.rows[0])
        far = self._add_range(range_tlui, 25, 70, range_tlui.rows[1])
        near = self._add_range(range_tlui, 22, 38, range_tlui.rows[1])
        range_tlui.select_element(ref)
        self._press("down")
        assert near in range_tlui.selected_elements
        assert far not in range_tlui.selected_elements

    def test_down_with_no_overlap_picks_closest_start(self, range_tlui):
        commands.execute("timeline.range.add_row")
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[0])
        before = self._add_range(range_tlui, 1, 5, range_tlui.rows[1])
        after = self._add_range(range_tlui, 50, 60, range_tlui.rows[1])
        range_tlui.select_element(ref)
        self._press("down")
        # |20-50| = 30 vs |20-1| = 19 → before wins.
        assert before in range_tlui.selected_elements
        assert after not in range_tlui.selected_elements

    def test_down_picks_only_candidate_when_after_only(self, range_tlui):
        commands.execute("timeline.range.add_row")
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[0])
        target = self._add_range(range_tlui, 50, 60, range_tlui.rows[1])
        range_tlui.select_element(ref)
        self._press("down")
        assert target in range_tlui.selected_elements

    def test_down_picks_only_candidate_when_before_only(self, range_tlui):
        commands.execute("timeline.range.add_row")
        ref = self._add_range(range_tlui, 50, 60, range_tlui.rows[0])
        target = self._add_range(range_tlui, 10, 20, range_tlui.rows[1])
        range_tlui.select_element(ref)
        self._press("down")
        assert target in range_tlui.selected_elements

    def test_up_into_overlapping_range(self, range_tlui):
        commands.execute("timeline.range.add_row")
        target = self._add_range(range_tlui, 20, 40, range_tlui.rows[0])
        ref = self._add_range(range_tlui, 25, 35, range_tlui.rows[1])
        range_tlui.select_element(ref)
        self._press("up")
        assert target in range_tlui.selected_elements

    def test_up_with_no_overlap(self, range_tlui):
        commands.execute("timeline.range.add_row")
        target = self._add_range(range_tlui, 1, 5, range_tlui.rows[0])
        ref = self._add_range(range_tlui, 50, 60, range_tlui.rows[1])
        range_tlui.select_element(ref)
        self._press("up")
        assert target in range_tlui.selected_elements

    def test_down_skips_empty_row(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_row")
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[0])
        target = self._add_range(range_tlui, 25, 35, range_tlui.rows[2])
        range_tlui.select_element(ref)
        self._press("down")
        assert target in range_tlui.selected_elements

    def test_up_skips_empty_row(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_row")
        target = self._add_range(range_tlui, 25, 35, range_tlui.rows[0])
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[2])
        range_tlui.select_element(ref)
        self._press("up")
        assert target in range_tlui.selected_elements

    def test_down_no_op_when_all_below_empty(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_row")
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[0])
        range_tlui.select_element(ref)
        self._press("down")
        assert ref in range_tlui.selected_elements

    def test_up_no_op_when_all_above_empty(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_row")
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[2])
        range_tlui.select_element(ref)
        self._press("up")
        assert ref in range_tlui.selected_elements

    def test_down_no_op_at_last_row(self, range_tlui):
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[0])
        range_tlui.select_element(ref)
        self._press("down")
        assert ref in range_tlui.selected_elements

    def test_up_no_op_at_first_row(self, range_tlui):
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[0])
        range_tlui.select_element(ref)
        self._press("up")
        assert ref in range_tlui.selected_elements

    def test_down_uses_last_selected_as_reference(self, range_tlui):
        commands.execute("timeline.range.add_row")
        first = self._add_range(range_tlui, 5, 10, range_tlui.rows[0])
        last = self._add_range(range_tlui, 50, 60, range_tlui.rows[0])
        below_first = self._add_range(range_tlui, 5, 10, range_tlui.rows[1])
        below_last = self._add_range(range_tlui, 50, 60, range_tlui.rows[1])
        range_tlui.select_element(first)
        range_tlui.select_element(last)
        self._press("down")
        # Reference is the last-selected component; the partner directly below wins.
        assert below_last in range_tlui.selected_elements
        assert below_first not in range_tlui.selected_elements

    def test_arrow_replaces_selection(self, range_tlui):
        commands.execute("timeline.range.add_row")
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[0])
        target = self._add_range(range_tlui, 25, 35, range_tlui.rows[1])
        range_tlui.select_element(ref)
        self._press("down")
        assert target in range_tlui.selected_elements
        assert ref not in range_tlui.selected_elements

    def test_highlight_follows_arrow(self, range_tlui):
        commands.execute("timeline.range.add_row")
        ref = self._add_range(range_tlui, 20, 30, range_tlui.rows[0])
        self._add_range(range_tlui, 25, 35, range_tlui.rows[1])
        range_tlui.select_element(ref)
        self._press("down")
        assert range_tlui.row_highlight.rect().y() == range_tlui.row_y(1)


class TestSeeking:
    def test_click_seeks_to_start(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=20, end=40)
        click_range_ui(range_tlui[0])
        assert tilia_state.current_time == 20

    def test_click_does_not_seek_when_alt_held(self, range_tlui, tilia_state):
        commands.execute("timeline.range.add_range", start=20, end=40)
        click_range_ui(range_tlui[0], modifier="alt")
        assert tilia_state.current_time == 0

    def test_double_click_seeks_during_playback(self, range_tlui, tilia_state):
        # Single-click seeking is gated with `if_playing=False`, so seeking
        # during playback must be triggered via double-click.
        commands.execute("timeline.range.add_range", start=20, end=40)
        commands.execute("media.toggle_play", True)
        try:
            click_range_ui(range_tlui[0], double=True)
            assert tilia_state.current_time == 20
        finally:
            commands.execute("media.toggle_play", False)


class TestDragHandle:
    @pytest.mark.parametrize(
        "click_fn, target_time, drag_y, attr, expected",
        [
            pytest.param(click_end_handle, 60, 0, "end", 60, id="end-right"),
            pytest.param(click_end_handle, 30, 0, "end", 30, id="end-left"),
            pytest.param(click_start_handle, 10, 0, "start", 10, id="start-left"),
            pytest.param(click_start_handle, 30, 0, "start", 30, id="start-right"),
            pytest.param(click_end_handle, 60, 9999, "end", 60, id="end-ignores-y"),
            pytest.param(
                click_start_handle, 10, 9999, "start", 10, id="start-ignores-y"
            ),
        ],
    )
    def test_drag(
        self, range_tlui, tilia_state, click_fn, target_time, drag_y, attr, expected
    ):
        commands.execute("timeline.range.add_range", start=20, end=40)
        r = range_tlui[0]
        click_fn(r)
        with undoable():
            drag_mouse_in_timeline_view(
                time_x_converter.get_x_by_time(target_time), drag_y
            )
            assert r.get_data(attr) == expected

    @pytest.mark.parametrize(
        "click_fn, target_time, attr, expected",
        [
            pytest.param(click_end_handle, 200, "end", 100, id="end-beyond-right"),
            pytest.param(click_start_handle, -100, "start", 0, id="start-beyond-left"),
        ],
    )
    def test_drag_clamped_at_margin(
        self, range_tlui, tilia_state, click_fn, target_time, attr, expected
    ):
        tilia_state.set_duration(100, scale_timelines="yes")
        commands.execute("timeline.range.add_range", start=20, end=40)
        r = range_tlui[0]
        click_fn(r)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(target_time), 0)
        assert r.get_data(attr) == expected

    @pytest.mark.parametrize(
        "click_fn, target_time",
        [
            pytest.param(click_end_handle, 5, id="end-past-range-start"),
            pytest.param(click_start_handle, 60, id="start-past-range-end"),
        ],
    )
    def test_drag_clamped_at_opposite_edge(
        self, range_tlui, tilia_state, click_fn, target_time
    ):
        commands.execute("timeline.range.add_range", start=20, end=40)
        r = range_tlui[0]
        click_fn(r)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(target_time), 0)
        assert r.get_data("start") < r.get_data("end")


class TestRowDeletionGuard:
    def test_remove_last_row_via_command_is_no_op(self, range_tlui):
        assert len(range_tlui.rows) == 1
        commands.execute("timeline.range.remove_row", row=range_tlui.rows[0])
        assert len(range_tlui.rows) == 1

    def test_remove_row_action_hidden_when_only_one_row(self, range_tlui):
        y = int(range_tlui.default_row_height / 2)
        with patch.object(range_tlui, "get_row_by_y", return_value=range_tlui.rows[0]):
            menu = get_context_menu(range_tlui, 0, y)
        assert get_action_by_object_name(menu, "remove row") is None

    def test_remove_row_action_present_when_multiple_rows(self, range_tlui):
        commands.execute("timeline.range.add_row")
        y = int(range_tlui.default_row_height / 2)
        with patch.object(range_tlui, "get_row_by_y", return_value=range_tlui.rows[0]):
            menu = get_context_menu(range_tlui, 0, y)
        assert get_action_by_object_name(menu, "remove row") is not None

    def test_right_click_on_rowless_timeline_does_not_crash(self, range_tlui):
        # Pre-condition: remove the initial row by going through a state
        # where row_count is 0. We bypass the guard by deleting it from the
        # backend list directly — the bug being regression-tested is the
        # crash, not the guard.
        range_tlui.timeline.rows.clear()
        # If this raises, the test fails.
        get_context_menu(range_tlui, 0, 0)


class TestRemoveRowToolbarEnabled:
    def test_disabled_with_one_row(self, range_tlui):
        assert range_tlui.timeline.row_count == 1
        assert get_qaction("timeline.range.remove_row").isEnabled() is False

    def test_enabled_after_adding_second_row(self, range_tlui):
        commands.execute("timeline.range.add_row")
        assert get_qaction("timeline.range.remove_row").isEnabled() is True

    def test_disabled_again_after_removing_back_to_one(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.remove_row", row=range_tlui.rows[1])
        assert range_tlui.timeline.row_count == 1
        assert get_qaction("timeline.range.remove_row").isEnabled() is False


class TestAddRowAboveBelowCommands:
    def test_add_row_above_uses_selected_row(self, range_tlui):
        commands.execute("timeline.range.add_row")
        # Make row index 1 the selected row.
        range_tlui.selected_row = range_tlui.rows[1]
        before = list(range_tlui.rows)
        commands.execute("timeline.range.add_row_above")
        # New row was inserted above the previously second row → it's the
        # new index-1 row, pushing the old one to index 2.
        assert len(range_tlui.rows) == 3
        assert range_tlui.rows[0] == before[0]
        assert range_tlui.rows[2] == before[1]

    def test_add_row_below_uses_selected_row(self, range_tlui):
        # selected_row defaults to rows[0]; "below" should insert at index 1.
        original = range_tlui.rows[0]
        commands.execute("timeline.range.add_row_below")
        assert len(range_tlui.rows) == 2
        assert range_tlui.rows[0] == original

    def test_add_row_above_with_no_selection_inserts_at_top(self, range_tlui):
        original = range_tlui.rows[0]
        range_tlui.selected_row = None
        commands.execute("timeline.range.add_row_above")
        assert len(range_tlui.rows) == 2
        assert range_tlui.rows[1] == original


class TestMoveRow:
    def _setup_three_rows(self, range_tlui):
        # Use the row ids (stable through reorder) to assert order.
        commands.execute("timeline.range.add_row", name="b")
        commands.execute("timeline.range.add_row", name="c")
        return [r.id for r in range_tlui.rows]

    def test_move_row_up(self, range_tlui):
        a, b, c = self._setup_three_rows(range_tlui)
        commands.execute("timeline.range.move_row_up", row=range_tlui.rows[1])
        assert [r.id for r in range_tlui.rows] == [b, a, c]

    def test_move_row_down(self, range_tlui):
        a, b, c = self._setup_three_rows(range_tlui)
        commands.execute("timeline.range.move_row_down", row=range_tlui.rows[1])
        assert [r.id for r in range_tlui.rows] == [a, c, b]

    def test_move_row_up_at_top_is_noop(self, range_tlui):
        a, b, c = self._setup_three_rows(range_tlui)
        commands.execute("timeline.range.move_row_up", row=range_tlui.rows[0])
        assert [r.id for r in range_tlui.rows] == [a, b, c]

    def test_move_row_down_at_bottom_is_noop(self, range_tlui):
        a, b, c = self._setup_three_rows(range_tlui)
        commands.execute("timeline.range.move_row_down", row=range_tlui.rows[2])
        assert [r.id for r in range_tlui.rows] == [a, b, c]

    def test_move_row_uses_selected_when_arg_omitted(self, range_tlui):
        a, b, c = self._setup_three_rows(range_tlui)
        range_tlui.selected_row = range_tlui.rows[2]
        commands.execute("timeline.range.move_row_up")
        assert [r.id for r in range_tlui.rows] == [a, c, b]

    def test_move_row_repositions_existing_ranges(self, range_tlui):
        self._setup_three_rows(range_tlui)
        commands.execute(
            "timeline.range.add_range", row=range_tlui.rows[2], start=0, end=10
        )
        elem = range_tlui[0]
        original_y = elem.body.rect().y()
        commands.execute("timeline.range.move_row_up", row=range_tlui.rows[2])
        # The range's row moved from idx 2 to idx 1, so its y must change.
        assert elem.body.rect().y() != original_y

    def test_move_row_undoable(self, range_tlui):
        self._setup_three_rows(range_tlui)
        with undoable():
            commands.execute("timeline.range.move_row_up", row=range_tlui.rows[2])

    def test_move_row_via_context_menu_up_action(self, range_tlui):
        a, b, c = self._setup_three_rows(range_tlui)
        menu = get_timeline_context_menu_for_row(range_tlui, 1)
        action = get_action_by_object_name(menu, "move row up")
        assert action is not None
        action.trigger()
        assert [r.id for r in range_tlui.rows] == [b, a, c]

    def test_move_row_up_action_hidden_at_top(self, range_tlui):
        self._setup_three_rows(range_tlui)
        menu = get_timeline_context_menu_for_row(range_tlui, 0)
        assert get_action_by_object_name(menu, "move row up") is None
        assert get_action_by_object_name(menu, "move row down") is not None

    def test_move_row_down_action_hidden_at_bottom(self, range_tlui):
        self._setup_three_rows(range_tlui)
        menu = get_timeline_context_menu_for_row(range_tlui, 2)
        assert get_action_by_object_name(menu, "move row down") is None
        assert get_action_by_object_name(menu, "move row up") is not None


class TestVerticalDragLive:
    def test_row_id_updates_during_drag(self, range_tlui):
        commands.execute("timeline.range.add_row")
        row_a, row_b = range_tlui.rows[0], range_tlui.rows[1]
        commands.execute("timeline.range.add_range", row=row_a, start=20, end=40)
        r = range_tlui[0]
        click_range_ui(r)

        center_x = time_x_converter.get_x_by_time(30)
        # First drag captures click offset.
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        assert r.get_data("row_id") == row_a.id

        target_y = range_tlui.row_y(1) + range_tlui.default_row_height // 2
        # Mid-drag (no release): row_id should already update to row_b.
        drag_mouse_in_timeline_view(center_x, target_y, release=False)
        assert r.get_data("row_id") == row_b.id

        # Release elsewhere: row_id stays.
        drag_mouse_in_timeline_view(center_x, target_y)
        assert r.get_data("row_id") == row_b.id


class TestHorizontalArrowNavigation:
    @staticmethod
    def _add(range_tlui, start, end, row=None):
        before = {e.id for e in range_tlui}
        kwargs = {"start": start, "end": end}
        if row is not None:
            kwargs["row"] = row
        commands.execute("timeline.range.add_range", **kwargs)
        new = [e for e in range_tlui if e.id not in before]
        return new[0]

    def test_no_op_without_selection_does_not_crash(self, range_tlui):
        self._add(range_tlui, 10, 20)
        # Selection empty: should not raise.
        post(Post.TIMELINE_KEY_PRESS_RIGHT)
        post(Post.TIMELINE_KEY_PRESS_LEFT)

    def test_right_selects_next_in_same_row(self, range_tlui):
        a = self._add(range_tlui, 10, 20)
        b = self._add(range_tlui, 30, 40)
        range_tlui.select_element(a)
        post(Post.TIMELINE_KEY_PRESS_RIGHT)
        assert range_tlui.selected_elements == [b]

    def test_left_selects_previous_in_same_row(self, range_tlui):
        a = self._add(range_tlui, 10, 20)
        b = self._add(range_tlui, 30, 40)
        range_tlui.select_element(b)
        post(Post.TIMELINE_KEY_PRESS_LEFT)
        assert range_tlui.selected_elements == [a]

    def test_right_at_last_keeps_selection(self, range_tlui):
        self._add(range_tlui, 10, 20)
        self._add(range_tlui, 30, 40)
        last_in_row = sorted(range_tlui)[-1]
        range_tlui.select_element(last_in_row)
        post(Post.TIMELINE_KEY_PRESS_RIGHT)
        assert range_tlui.selected_elements == [last_in_row]

    def test_horizontal_navigation_stays_in_row(self, range_tlui):
        commands.execute("timeline.range.add_row")
        row_a, row_b = range_tlui.rows[0], range_tlui.rows[1]
        a = self._add(range_tlui, 10, 20, row=row_a)
        # Range b is in a different row but later in time.
        b = self._add(range_tlui, 30, 40, row=row_b)
        range_tlui.select_element(a)
        post(Post.TIMELINE_KEY_PRESS_RIGHT)
        # Should stay on `a` because there's nothing else in row_a.
        assert range_tlui.selected_elements == [a]
        assert b is not a


class TestMultiRowCopyError:
    def test_copy_from_two_rows_displays_error(self, range_tlui):
        commands.execute("timeline.range.add_row")
        row_a, row_b = range_tlui.rows[0], range_tlui.rows[1]
        commands.execute("timeline.range.add_range", row=row_a, start=10, end=20)
        commands.execute("timeline.range.add_range", row=row_b, start=30, end=40)
        for e in range_tlui:
            range_tlui.select_element(e)
        # use the tilia_errors fixture for this assert instead
        with patch("tilia.errors.display") as display:
            commands.execute("timeline.component.copy")
        display.assert_called()
        # First positional arg should be the COMPONENTS_COPY_ERROR descriptor.
        import tilia.errors as errors

        assert display.call_args.args[0] == errors.COMPONENTS_COPY_ERROR

    def test_copy_from_single_row_succeeds(self, range_tlui):
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=30, end=40)
        for e in range_tlui:
            range_tlui.select_element(e)
        # idem, and see if there are any other instance of this that could also be adjusted
        with patch("tilia.errors.display") as display:
            commands.execute("timeline.component.copy")
        display.assert_not_called()


class TestSettingsCrashRegression:
    def test_settings_update_after_highlight_deleted_does_not_crash(self, range_tlui):
        # Reproduce the state where another range timeline was clicked and
        # this one's highlight was removed. Updating settings while in this
        # state used to crash on row_highlight.set_height.
        range_tlui._delete_row_highlight()
        assert range_tlui.row_highlight is None
        post(Post.SETTINGS_UPDATED, ["range_timeline"])


class TestRemoveRowToolbarPerSelectedTimeline:
    @staticmethod
    def _make_two(tluis):
        commands.execute("timelines.add.range", name="A")
        commands.execute("timelines.add.range", name="B")
        ranges = [t for t in tluis if isinstance(t, RangeTimelineUI)]
        a = next(t for t in ranges if t.get_data("name") == "A")
        b = next(t for t in ranges if t.get_data("name") == "B")
        return a, b

    def test_disabled_when_selected_timeline_has_one_row(self, tluis):
        a, b = self._make_two(tluis)
        click_timeline_ui(b, 1)
        commands.execute("timeline.range.add_row")
        assert b.timeline.row_count == 2
        assert a.timeline.row_count == 1
        click_timeline_ui(a, 1)
        assert get_qaction("timeline.range.remove_row").isEnabled() is False

    def test_enabled_when_selected_timeline_has_more_than_one_row(self, tluis):
        a, _ = self._make_two(tluis)
        click_timeline_ui(a, 1)
        commands.execute("timeline.range.add_row")
        assert get_qaction("timeline.range.remove_row").isEnabled() is True


class TestPreStartPostEnd:
    def _make_range(self, range_tlui, start=10, end=20):
        commands.execute("timeline.range.add_range", start=start, end=end)
        elem = range_tlui[0]
        range_tlui.select_element(elem)
        return elem

    def test_default_pre_start_equals_start(self, range_tlui):
        elem = self._make_range(range_tlui)
        assert elem.get_data("pre_start") == elem.get_data("start")

    def test_default_post_end_equals_end(self, range_tlui):
        elem = self._make_range(range_tlui)
        assert elem.get_data("post_end") == elem.get_data("end")

    def test_add_pre_start_command(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        assert elem.get_data("pre_start") == 6.0

    def test_add_post_end_command(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 5.0)):
            commands.execute("timeline.range.add_post_end")
        assert elem.get_data("post_end") == 25.0

    def test_add_pre_start_clamps_at_zero(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 50.0)):
            commands.execute("timeline.range.add_pre_start")
        assert elem.get_data("pre_start") == 0.0

    def test_add_post_end_clamps_at_media_duration(self, range_tlui, tilia_state):
        # The default fixture duration is 100; ask for an extension that
        # would push post_end past it.
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 200.0)):
            commands.execute("timeline.range.add_post_end")
        assert elem.get_data("post_end") == tilia_state.duration

    def test_add_pre_start_cancel_does_nothing(self, range_tlui):
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (False, 0.0)):
            commands.execute("timeline.range.add_pre_start")
        assert elem.get_data("pre_start") == elem.get_data("start")

    def test_add_pre_start_zero_or_negative_does_nothing(self, range_tlui):
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 0.0)):
            commands.execute("timeline.range.add_pre_start")
        assert elem.get_data("pre_start") == 10

    def test_delete_pre_start(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        assert elem.get_data("pre_start") == 6.0
        commands.execute("timeline.range.delete_pre_start")
        assert elem.get_data("pre_start") == elem.get_data("start")

    def test_delete_post_end(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_post_end")
        commands.execute("timeline.range.delete_post_end")
        assert elem.get_data("post_end") == elem.get_data("end")

    def test_add_pre_start_applies_to_all_selected(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=30, end=40)
        for e in range_tlui:
            range_tlui.select_element(e)
        with Serve(Get.FROM_USER_FLOAT, (True, 3.0)):
            commands.execute("timeline.range.add_pre_start")
        ranges = sorted(range_tlui)
        assert ranges[0].get_data("pre_start") == 7.0
        assert ranges[1].get_data("pre_start") == 27.0

    def test_whiskers_hidden_when_not_extended(self, range_tlui):
        elem = self._make_range(range_tlui)
        # No pre_start / post_end set, so whiskers stay hidden even though
        # the range is selected.
        assert elem.pre_start_handle.isVisible() is False
        assert elem.post_end_handle.isVisible() is False

    def test_whiskers_visible_when_selected_and_extended(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        assert elem.pre_start_handle.isVisible()

    def test_whiskers_hidden_when_deselected(self, range_tlui, tilia_state):
        settings.set("range_timeline", "always_show_extensions", False)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        assert elem.pre_start_handle.isVisible()
        range_tlui.deselect_element(elem)
        assert elem.pre_start_handle.isVisible() is False

    def test_whiskers_hide_after_delete(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        assert elem.pre_start_handle.isVisible()
        commands.execute("timeline.range.delete_pre_start")
        assert elem.pre_start_handle.isVisible() is False

    def test_always_show_extensions_keeps_whiskers_visible_when_deselected(
        self, range_tlui, tilia_state
    ):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        settings.set("range_timeline", "always_show_extensions", True)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        range_tlui.deselect_element(elem)
        assert elem.pre_start_handle.isVisible() is True

    def test_toggle_always_show_extensions_command_flips_setting(self, range_tlui):
        settings.set("range_timeline", "always_show_extensions", False)
        commands.execute("timeline.range.toggle_always_show_extensions")
        assert bool(settings.get("range_timeline", "always_show_extensions"))
        commands.execute("timeline.range.toggle_always_show_extensions")
        assert not bool(settings.get("range_timeline", "always_show_extensions"))

    def test_context_menu_offers_add_when_unset(self, range_tlui):
        elem = self._make_range(range_tlui, start=10, end=20)
        menu = RangeContextMenu(elem)
        action_names = [a.text() for a in menu.actions()]
        assert "Add pre-start" in action_names
        assert "Add post-end" in action_names
        assert "Delete pre-start" not in action_names
        assert "Delete post-end" not in action_names

    def test_context_menu_offers_delete_when_set(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        with Serve(Get.FROM_USER_FLOAT, (True, 5.0)):
            commands.execute("timeline.range.add_post_end")
        menu = RangeContextMenu(elem)
        action_names = [a.text() for a in menu.actions()]
        assert "Delete pre-start" in action_names
        assert "Delete post-end" in action_names
        assert "Add pre-start" not in action_names
        assert "Add post-end" not in action_names

    def test_inspector_shows_pre_post(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        # When neither is set, it just shows "-"
        assert elem.get_inspector_dict()["Pre-start / post-end"] == "-"
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        # Now pre is set, post is not
        value = elem.get_inspector_dict()["Pre-start / post-end"]
        assert " / -" in value
        assert "-" != value

    def test_body_drag_carries_pre_start_and_post_end(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=20, end=40)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        with Serve(Get.FROM_USER_FLOAT, (True, 5.0)):
            commands.execute("timeline.range.add_post_end")
        # pre_start = 16, post_end = 45.
        click_range_ui(elem)
        center_x = time_x_converter.get_x_by_time(30)
        target_x = time_x_converter.get_x_by_time(60)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(target_x, 0)
        # delta = +30; offsets to body extremities preserved.
        assert elem.get_data("start") == 50
        assert elem.get_data("end") == 70
        assert elem.get_data("pre_start") == 46
        assert elem.get_data("post_end") == 75

    def test_body_drag_clamped_by_pre_start_at_left_margin(
        self, range_tlui, tilia_state
    ):
        # Without extensions, a [10,20] range can drag down to start=0.
        # With pre_start=7 (3 of pre-extension), the leftmost reachable
        # start is 3 (so pre_start lands at 0).
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 3.0)):
            commands.execute("timeline.range.add_pre_start")
        click_range_ui(elem)
        center_x = time_x_converter.get_x_by_time(15)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(-100_000, 0)
        assert elem.get_data("pre_start") == pytest.approx(0)
        assert elem.get_data("start") == pytest.approx(3)

    def test_drag_pre_start_handle_left(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=20, end=40)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        # pre_start at 16; drag handle to time 10.
        click_pre_start_handle(elem)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(10), 0)
        assert elem.get_data("pre_start") == pytest.approx(10)
        # body untouched
        assert elem.get_data("start") == 20

    def test_drag_post_end_handle_right(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=20, end=40)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_post_end")
        click_post_end_handle(elem)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(60), 0)
        assert elem.get_data("post_end") == pytest.approx(60)
        assert elem.get_data("end") == 40

    def test_drag_pre_start_handle_clamped_at_body(self, range_tlui, tilia_state):
        # Dragging the pre_start whisker into / past the body should clamp
        # at the body's start (pre_start can't exceed start).
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=20, end=40)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        click_pre_start_handle(elem)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(80), 0)
        assert elem.get_data("pre_start") == 20  # == start, clamped

    def test_drag_post_end_handle_clamped_at_body(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=20, end=40)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_post_end")
        click_post_end_handle(elem)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(0), 0)
        assert elem.get_data("post_end") == 40  # == end, clamped

    def test_whisker_stays_visible_during_drag(self, range_tlui, tilia_state):
        # Regression: clicking the whisker used to deselect the range
        # (vertical_line wasn't in selection_triggers), so the whisker —
        # visible only when selected — vanished mid-drag.
        settings.set("range_timeline", "always_show_extensions", False)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=20, end=40)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        click_pre_start_handle(elem)
        drag_mouse_in_timeline_view(
            time_x_converter.get_x_by_time(10), 0, release=False
        )
        assert elem.pre_start_handle.isVisible()
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)

    def test_whisker_vline_has_resize_cursor(self, range_tlui, tilia_state):
        # CursorMixIn now sets the cursor directly on the item (via
        # QGraphicsItem.setCursor) instead of push/pop-ing a global
        # override cursor on hover — Qt applies/restores it automatically,
        # so there's no more manual hover/hide bookkeeping to regression
        # test here (see tilia/ui/timelines/cursors.py).
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=20, end=40)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        vline = elem.pre_start_handle.vertical_line
        assert vline.cursor().shape() == Qt.CursorShape.SizeHorCursor

    def test_drag_pre_start_handle_undoable(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        elem = self._make_range(range_tlui, start=20, end=40)
        with Serve(Get.FROM_USER_FLOAT, (True, 4.0)):
            commands.execute("timeline.range.add_pre_start")
        click_pre_start_handle(elem)
        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(10), 0)
        commands.execute("edit.undo")
        assert range_tlui[0].get_data("pre_start") == 16

    def test_save_load_preserves_pre_start_post_end(
        self, range_tlui, tilia, tluis, tilia_state, tmp_path
    ):
        tilia_state.duration = 100
        self._make_range(range_tlui, start=10, end=20)
        with Serve(Get.FROM_USER_FLOAT, (True, 3.0)):
            commands.execute("timeline.range.add_pre_start")
        with Serve(Get.FROM_USER_FLOAT, (True, 5.0)):
            commands.execute("timeline.range.add_post_end")

        save_and_reopen(tmp_path)

        new_tlui = next(t for t in tluis if isinstance(t, RangeTimelineUI))
        rng = list(new_tlui)[0]
        assert rng.get_data("pre_start") == 7.0
        assert rng.get_data("post_end") == 25.0
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)


class TestMergeRanges:
    def _add(self, range_tlui, start, end, **kwargs):
        commands.execute("timeline.range.add_range", start=start, end=end, **kwargs)
        return range_tlui[len(range_tlui) - 1]

    def test_merge_two_non_overlapping(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 20, 30)
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        assert len(range_tlui) == 1
        survivor = list(range_tlui)[0]
        assert survivor.get_data("start") == 0
        assert survivor.get_data("end") == 30

    def test_merge_with_shortcut(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 20, 30)
        click_range_ui(a)
        click_range_ui(b, modifier="ctrl")
        press_key("e")
        assert len(range_tlui) == 1
        survivor = list(range_tlui)[0]
        assert survivor.get_data("start") == 0
        assert survivor.get_data("end") == 30

    def test_merge_two_overlapping(self, range_tlui):
        a = self._add(range_tlui, 0, 15)
        b = self._add(range_tlui, 10, 25)
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        assert len(range_tlui) == 1
        survivor = list(range_tlui)[0]
        assert survivor.get_data("start") == 0
        assert survivor.get_data("end") == 25

    def test_merge_joined_chain(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        c = self._add(range_tlui, 20, 30)
        for e in (a, b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.join_ranges")
        for e in (a, b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        assert len(range_tlui) == 1
        survivor = list(range_tlui)[0]
        assert survivor.get_data("start") == 0
        assert survivor.get_data("end") == 30
        assert survivor.get_data("joined_right") is None

    def test_merge_rewires_external_join_into_merged_range(self, range_tlui):
        # Chain of three, then merge only the latter two. The first
        # range's join (originally pointing at b) must rewire to the
        # surviving range covering b..c's span.
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        c = self._add(range_tlui, 20, 30)
        for e in (a, b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.join_ranges")

        for e in (a, b, c):
            range_tlui.deselect_element(e)
        for e in (b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")

        survivor_ids = {e.id for e in range_tlui if e.id != a.id}
        assert a.get_data("joined_right") in survivor_ids

    def test_merge_multi_row_selection_errors(self, range_tlui, tilia_errors):
        commands.execute("timeline.range.add_row")
        a = self._add(range_tlui, 0, 10, row=range_tlui.rows[0])
        b = self._add(range_tlui, 0, 10, row=range_tlui.rows[1])
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        assert len(range_tlui) == 2
        tilia_errors.assert_error()

    def test_merge_fewer_than_two_errors(self, range_tlui, tilia_errors):
        a = self._add(range_tlui, 0, 10)
        range_tlui.select_element(a)
        commands.execute("timeline.range.merge_ranges")
        assert len(range_tlui) == 1
        tilia_errors.assert_error()

    def test_undo_restores_originals(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 20, 30)
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        assert len(range_tlui) == 1
        commands.execute("edit.undo")
        assert len(range_tlui) == 2
        starts = sorted(e.get_data("start") for e in range_tlui)
        ends = sorted(e.get_data("end") for e in range_tlui)
        assert starts == [0, 20]
        assert ends == [10, 30]

    def test_merge_joins_non_empty_labels_with_separator(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        range_tlui.timeline.set_component_data(a.id, "label", "alpha")
        range_tlui.timeline.set_component_data(b.id, "label", "beta")
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        sep = settings.get("range_timeline", "merge_separator")
        assert survivor.get_data("label") == f"alpha{sep}beta"

    def test_merge_skips_empty_labels(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        c = self._add(range_tlui, 20, 30)
        range_tlui.timeline.set_component_data(a.id, "label", "alpha")
        range_tlui.timeline.set_component_data(c.id, "label", "gamma")
        for e in (a, b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        sep = settings.get("range_timeline", "merge_separator")
        assert survivor.get_data("label") == f"alpha{sep}gamma"

    def test_merge_joins_non_empty_comments_with_separator(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        range_tlui.timeline.set_component_data(a.id, "comments", "first note")
        range_tlui.timeline.set_component_data(b.id, "comments", "second note")
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        sep = settings.get("range_timeline", "merge_separator")
        assert survivor.get_data("comments") == f"first note{sep}second note"

    def test_merge_label_empty_when_all_empty(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        assert survivor.get_data("label") == ""
        assert survivor.get_data("comments") == ""

    def test_merge_identical_labels_kept_without_separator(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        c = self._add(range_tlui, 20, 30)
        for e in (a, b, c):
            range_tlui.timeline.set_component_data(e.id, "label", "theme")
        for e in (a, b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        assert survivor.get_data("label") == "theme"

    def test_merge_identical_comments_kept_without_separator(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        for e in (a, b):
            range_tlui.timeline.set_component_data(e.id, "comments", "same note")
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        assert survivor.get_data("comments") == "same note"

    def test_merge_identical_labels_with_empties_mixed_not_joined(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        c = self._add(range_tlui, 20, 30)
        range_tlui.timeline.set_component_data(a.id, "label", "theme")
        range_tlui.timeline.set_component_data(c.id, "label", "theme")
        for e in (a, b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        assert survivor.get_data("label") == "theme"

    def test_merge_identical_colors_preserved(self, range_tlui):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        for e in (a, b):
            range_tlui.timeline.set_component_data(e.id, "color", "#aabbcc")
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        assert survivor.get_data("color") == "#aabbcc"

    def test_merge_separator_setting_is_respected(self, range_tlui):
        settings.set("range_timeline", "merge_separator", " / ")
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        range_tlui.timeline.set_component_data(a.id, "label", "alpha")
        range_tlui.timeline.set_component_data(b.id, "label", "beta")
        for e in (a, b):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        assert survivor.get_data("label") == "alpha / beta"

    def test_merge_preserves_first_pre_start_and_last_post_end(self, range_tlui):
        a = self._add(range_tlui, 10, 20)
        b = self._add(range_tlui, 30, 40)
        c = self._add(range_tlui, 50, 60)
        # a has pre_start=5, c has post_end=70; b has neither.
        range_tlui.timeline.set_component_data(a.id, "pre_start", 5)
        range_tlui.timeline.set_component_data(c.id, "post_end", 70)
        for e in (a, b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        assert survivor.get_data("pre_start") == 5
        assert survivor.get_data("post_end") == 70

    def test_merge_label_persists_through_save_load(
        self, range_tlui, tilia, tluis, tilia_state, tmp_path
    ):
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        c = self._add(range_tlui, 20, 30)
        for e, lbl, cmt in (
            (a, "alpha", "first note"),
            (b, "beta", "second note"),
            (c, "gamma", "third note"),
        ):
            range_tlui.timeline.set_component_data(e.id, "label", lbl)
            range_tlui.timeline.set_component_data(e.id, "comments", cmt)
        for e in (a, b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        sep = settings.get("range_timeline", "merge_separator")
        survivor = list(range_tlui)[0]
        assert survivor.get_data("label") == f"alpha{sep}beta{sep}gamma"
        assert (
            survivor.get_data("comments")
            == f"first note{sep}second note{sep}third note"
        )

        save_and_reopen(tmp_path)

        new_tlui = next(t for t in tluis if isinstance(t, RangeTimelineUI))
        assert len(new_tlui) == 1
        loaded = list(new_tlui)[0]
        assert loaded.get_data("label") == f"alpha{sep}beta{sep}gamma"
        assert (
            loaded.get_data("comments") == f"first note{sep}second note{sep}third note"
        )
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)

    def test_merge_with_inspector_open_does_not_clobber_label(self, range_tlui, qtui):
        # Regression: the inspector's deselect cascade re-displays the
        # previous stack entry's stale snapshot, and setText fired
        # textChanged → INSPECTOR_FIELD_EDITED → write-back, clobbering
        # the merged label/comments. Fixed by blocking widget signals
        # during programmatic value updates in
        # tilia.ui.windows.inspect.Inspect.set_widget_value.
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        c = self._add(range_tlui, 20, 30)
        for e, lbl, cmt in (
            (a, "alpha", "first"),
            (b, "beta", "second"),
            (c, "gamma", "third"),
        ):
            range_tlui.timeline.set_component_data(e.id, "label", lbl)
            range_tlui.timeline.set_component_data(e.id, "comments", cmt)

        for e in (a, b, c):
            range_tlui.select_element(e)
        # Open the inspector: this is the path that builds the
        # inspected_objects_stack from the live selection.
        commands.execute("timeline.element.inspect")
        try:
            commands.execute("timeline.range.merge_ranges")
            sep = settings.get("range_timeline", "merge_separator")
            survivor = list(range_tlui)[0]
            assert survivor.get_data("label") == f"alpha{sep}beta{sep}gamma"
            assert survivor.get_data("comments") == f"first{sep}second{sep}third"
        finally:
            post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def test_merge_via_inspector_set_labels(self, range_tlui):
        # Mimic the user flow: set label/comments through Post.INSPECTOR_FIELD_EDITED
        # (the path triggered when typing into the Inspector dock).
        a = self._add(range_tlui, 0, 10)
        b = self._add(range_tlui, 10, 20)
        c = self._add(range_tlui, 20, 30)
        for e in (a, b, c):
            range_tlui.select_element(e)
        # element listeners are registered by select_element, so the inspector
        # post will route to the right component.
        for e, lbl, cmt in (
            (a, "first", "alpha"),
            (b, "second", "beta"),
            (c, "third", "gamma"),
        ):
            post(Post.INSPECTOR_FIELD_EDITED, "Label", lbl, e.id, 0)
            post(Post.INSPECTOR_FIELD_EDITED, "Comments", cmt, e.id, 0)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        sep = settings.get("range_timeline", "merge_separator")
        assert survivor.get_data("label") == f"first{sep}second{sep}third"
        assert survivor.get_data("comments") == f"alpha{sep}beta{sep}gamma"

    def test_clearing_comments_via_inspector_is_undoable(self, range_tlui):
        # Regression: clearing the Comments field in the inspector did not
        # produce an undo entry for some users. Asserts the round-trip
        # set-then-clear-then-undo restores the original value. Use a
        # different inspector_id for each edit so the no_repeat collapse
        # in the undo manager doesn't fold them into a single entry.
        # Check via `timeline.get_component(eid)` rather than holding the
        # original element reference (it becomes stale across the restore).
        e = self._add(range_tlui, 0, 10)
        eid = e.id
        range_tlui.select_element(e)
        post(Post.INSPECTOR_FIELD_EDITED, "Comments", "abc", eid, 0)
        post(Post.INSPECTOR_FIELD_EDITED, "Comments", "", eid, 1)
        assert range_tlui.timeline.get_component(eid).comments == ""
        commands.execute("edit.undo")
        assert range_tlui.timeline.get_component(eid).comments == "abc"
        commands.execute("edit.redo")
        assert range_tlui.timeline.get_component(eid).comments == ""

    def test_comments_no_repeat_collapse_does_not_lose_clear(self, range_tlui):
        # Same flow as a real user typing characters then clearing the
        # field — every textChanged in the same inspector dock fires with
        # the same `inspector_id`, so the no_repeat collapse rolls them
        # all up into a single undo entry. The cleared value should still
        # be the *current* state — not lost behind the previous "abc".
        e = self._add(range_tlui, 0, 10)
        eid = e.id
        range_tlui.select_element(e)
        for value in ("a", "ab", "abc", ""):
            post(Post.INSPECTOR_FIELD_EDITED, "Comments", value, eid, 0)
        assert range_tlui.timeline.get_component(eid).comments == ""
        commands.execute("edit.undo")
        # Undoing the whole roll-up should bring comments back to its
        # original value (the empty initial state, not "abc").
        assert range_tlui.timeline.get_component(eid).comments == ""

    def test_merge_drops_middle_pre_post_extensions(self, range_tlui):
        # The middle range's pre_start / post_end should not influence the
        # survivor — only the first range's pre_start and the last range's
        # post_end are preserved.
        a = self._add(range_tlui, 10, 20)
        b = self._add(range_tlui, 30, 40)
        c = self._add(range_tlui, 50, 60)
        range_tlui.timeline.set_component_data(b.id, "pre_start", 25)
        range_tlui.timeline.set_component_data(b.id, "post_end", 45)
        for e in (a, b, c):
            range_tlui.select_element(e)
        commands.execute("timeline.range.merge_ranges")
        survivor = list(range_tlui)[0]
        # No extension on the first/last ranges, so pre_start == start and
        # post_end == end.
        assert survivor.get_data("pre_start") == 10
        assert survivor.get_data("post_end") == 60


class TestPerRowHeight:
    def test_default_row_height_is_none(self, range_tlui):
        assert range_tlui.rows[0].height is None

    def test_row_height_for_falls_back_to_timeline(self, range_tlui):
        # No explicit per-row height -> uses timeline's row_height.
        row = range_tlui.rows[0]
        assert range_tlui.row_height_for(row) == range_tlui.default_row_height

    def test_set_row_height_for_row_command(self, range_tlui):
        row = range_tlui.rows[0]
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute("timeline.range.set_row_height_for_row", row=row)
        assert row.height == 80
        assert range_tlui.row_height_for(row) == 80

    def test_reset_row_height_command(self, range_tlui):
        row = range_tlui.rows[0]
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute("timeline.range.set_row_height_for_row", row=row)
        commands.execute("timeline.range.reset_row_height_for_row", row=row)
        assert row.height is None

    def test_row_y_is_cumulative(self, range_tlui):
        # Two extra rows: row[0] = default, row[1] = 80, row[2] = default.
        commands.execute("timeline.range.add_row", name="middle")
        commands.execute("timeline.range.add_row", name="bottom")
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute(
                "timeline.range.set_row_height_for_row", row=range_tlui.rows[1]
            )

        default = range_tlui.default_row_height
        assert range_tlui.row_y(0) == 0
        assert range_tlui.row_y(1) == default
        assert range_tlui.row_y(2) == default + 80

    def test_total_height_is_sum_of_row_heights(self, range_tlui):
        commands.execute("timeline.range.add_row", name="bottom")
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute(
                "timeline.range.set_row_height_for_row", row=range_tlui.rows[1]
            )

        default = range_tlui.default_row_height
        assert range_tlui.height == default + 80 + 20

    def test_get_row_by_y_handles_per_row_heights(self, range_tlui):
        # Pin the default so the assertions don't depend on whatever value
        # earlier tests in this module wrote to the QSettings store.
        settings.set("range_timeline", "default_row_height", 30)
        commands.execute("timeline.range.add_row", name="bottom")
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute(
                "timeline.range.set_row_height_for_row", row=range_tlui.rows[1]
            )
        # row 0 occupies 0..30 (default); row 1 occupies 30..110 (80 tall).
        assert range_tlui.get_row_by_y(5) is range_tlui.rows[0]
        assert range_tlui.get_row_by_y(50) is range_tlui.rows[1]

    def test_element_position_uses_per_row_height(self, range_tlui):
        commands.execute("timeline.range.add_row", name="bottom")
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute(
                "timeline.range.set_row_height_for_row", row=range_tlui.rows[1]
            )
        commands.execute(
            "timeline.range.add_range",
            row=range_tlui.rows[1],
            start=0,
            end=10,
        )
        elem = range_tlui[0]
        # Element body height should match the per-row height of row[1].
        assert elem.row_height == 80
        assert elem.body.rect().height() == 80

    def test_save_load_preserves_per_row_height(
        self, range_tlui, tilia, tluis, tilia_state, tmp_path
    ):
        commands.execute("timeline.range.add_row", name="extra")
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute(
                "timeline.range.set_row_height_for_row", row=range_tlui.rows[1]
            )

        save_and_reopen(tmp_path)

        new_tlui = next(t for t in tluis if isinstance(t, RangeTimelineUI))
        assert new_tlui.timeline.rows[1].height == 80
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)

    def test_undo_restores_per_row_height(self, range_tlui):
        row = range_tlui.rows[0]
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute("timeline.range.set_row_height_for_row", row=row)
        assert row.height == 80
        commands.execute("edit.undo")
        # The row instance was rebuilt by the state restore; resolve by id.
        restored = range_tlui.timeline.rows[0]
        assert restored.height is None

    def test_highlight_resizes_to_active_row(self, range_tlui):
        commands.execute("timeline.range.add_row", name="tall")
        with Serve(Get.FROM_USER_INT, (True, 80)):
            commands.execute(
                "timeline.range.set_row_height_for_row", row=range_tlui.rows[1]
            )
        range_tlui.selected_row = range_tlui.rows[1]
        range_tlui.update_highlight_position()
        assert range_tlui.row_highlight._height == 80

    def test_click_selects_row_under_per_row_heights(self, range_tlui):
        # Regression: on_left_click used to divide y by the global row_height,
        # so a click that visually landed on row 0 (which had been resized
        # taller) was attributed to row 1.
        settings.set("range_timeline", "default_row_height", 30)
        commands.execute("timeline.range.add_row", name="below")
        with Serve(Get.FROM_USER_INT, (True, 100)):
            commands.execute(
                "timeline.range.set_row_height_for_row", row=range_tlui.rows[0]
            )
        # row 0 occupies y ∈ [0, 100); row 1 occupies [100, 130).
        # y=70 lies within row 0 visually; the buggy uniform division would
        # have classed it as row 2 (out of range, falling through).
        click_timeline_ui_view(range_tlui.view, "left", 50, 70)
        assert range_tlui.selected_row is range_tlui.rows[0]

        click_timeline_ui_view(range_tlui.view, "left", 50, 110)
        assert range_tlui.selected_row is range_tlui.rows[1]

    def test_row_at_y_in_drag_uses_per_row_heights(self, range_tlui):
        settings.set("range_timeline", "default_row_height", 30)
        commands.execute("timeline.range.add_row", name="tall")
        with Serve(Get.FROM_USER_INT, (True, 100)):
            commands.execute(
                "timeline.range.set_row_height_for_row", row=range_tlui.rows[1]
            )
        # row 0 occupies 0..30, row 1 occupies 30..130
        assert _row_at_y(range_tlui, 10) is range_tlui.rows[0]
        assert _row_at_y(range_tlui, 100) is range_tlui.rows[1]
        # Beyond the last row clamps to it.
        assert _row_at_y(range_tlui, 999) is range_tlui.rows[1]
        # Above row 0 clamps to row 0.
        assert _row_at_y(range_tlui, -50) is range_tlui.rows[0]


class TestLabelAlignment:
    def _make_range(self, range_tlui, start=10, end=20, label="example"):
        commands.execute("timeline.range.add_range", start=start, end=end)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "label", label)
        return elem

    def _set_alignment(self, alignment):
        settings.set("range_timeline", "default_label_alignment", alignment)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])

    def test_reads_from_setting(self, range_tlui):
        self._set_alignment("center")
        assert range_tlui.label_alignment == "center"

    def test_left_alignment_label_x(self, range_tlui):
        self._set_alignment("left")
        elem = self._make_range(range_tlui)
        elem.update_position()
        assert elem.label.x() == elem.start_x + elem.label.LEFT_PADDING

    def test_right_alignment_label_x(self, range_tlui):
        self._set_alignment("right")
        elem = self._make_range(range_tlui)
        elem.update_position()
        # Right edge of the label should be at end_x - RIGHT_PADDING.
        text_width = elem.label.boundingRect().width()
        assert elem.label.x() == elem.end_x - text_width - elem.label.RIGHT_PADDING

    def test_center_alignment_label_x(self, range_tlui):
        self._set_alignment("center")
        elem = self._make_range(range_tlui)
        elem.update_position()
        text_width = elem.label.boundingRect().width()
        assert elem.label.x() == (elem.start_x + elem.end_x - text_width) / 2

    @pytest.mark.parametrize("alignment", ["left", "center", "right"])
    def test_align_command_sets_alignment(self, range_tlui, alignment):
        # Start from a different known value so the assertion proves the
        # command changed the state rather than matching the default.
        other = "right" if alignment != "right" else "left"
        self._set_alignment(other)
        commands.execute(f"timeline.range.align_labels_{alignment}")
        assert range_tlui.label_alignment == alignment

    def test_alignment_is_global_across_timelines(self, tluis):
        # Two independent range timelines should reflect the same setting.
        commands.execute("timelines.add.range", name="A")
        commands.execute("timelines.add.range", name="B")
        ranges = [t for t in tluis if isinstance(t, RangeTimelineUI)]
        assert len(ranges) == 2
        self._set_alignment("right")
        assert ranges[0].label_alignment == "right"
        assert ranges[1].label_alignment == "right"

    @pytest.mark.parametrize("alignment", ["left", "center", "right"])
    def test_toolbar_button_checked_state(self, range_tlui, alignment):
        self._set_alignment(alignment)
        for opt in ("left", "center", "right"):
            action = get_qaction(f"timeline.range.align_labels_{opt}")
            assert action.isChecked() == (opt == alignment)

    @pytest.mark.parametrize("alignment", ["center", "right"])
    def test_label_alignment_after_typing_text(self, range_tlui, alignment):
        # Regression: typing into an empty label (e.g. through the inspector)
        # used to leave the label x at the position computed for the empty
        # string, so center/right alignment looked off until something else
        # forced an update_position.
        self._set_alignment(alignment)
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        # Simulate a text edit (the path the inspector takes).
        range_tlui.timeline.set_component_data(elem.id, "label", "hello")
        text_width = elem.label.boundingRect().width()
        if alignment == "center":
            expected_x = (elem.start_x + elem.end_x - text_width) / 2
        else:
            expected_x = elem.end_x - text_width - elem.label.RIGHT_PADDING
        assert elem.label.x() == expected_x

    @pytest.mark.parametrize("alignment", ["left", "center", "right"])
    def test_long_label_remains_elided(self, range_tlui, alignment):
        self._set_alignment(alignment)
        long_text = "x" * 200
        elem = self._make_range(range_tlui, start=0, end=10, label=long_text)
        elem.update_position()
        # The displayed text must be elided (not the original 200-character
        # string). The exact pixel-width check is delegated to elide_text.
        assert elem.label.toPlainText() != long_text
        assert len(elem.label.toPlainText()) < len(long_text)


class TestSplitRange:
    def _seek(self, time: float) -> None:
        commands.execute("media.seek", time)

    def test_split_mid_range(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=30)
        original = range_tlui[0]
        original_id = original.id
        self._seek(20)
        commands.execute("timeline.range.split_range")
        ranges = sorted(range_tlui)
        assert len(ranges) == 2
        left, right = ranges
        assert left.id == original_id  # left half kept the original id
        assert left.get_data("end") == 20
        assert right.get_data("start") == 20
        assert right.get_data("end") == 30
        assert left.get_data("joined_right") == right.id

    def test_split_with_shortcut(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=30)
        click_range_ui(range_tlui[0])
        self._seek(20)
        press_key("s")
        ranges = sorted(range_tlui)
        assert len(ranges) == 2
        assert ranges[0].get_data("end") == 20
        assert ranges[1].get_data("start") == 20

    def test_split_inherits_attributes(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=30)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "label", "lbl")
        range_tlui.timeline.set_component_data(elem.id, "color", "#abcdef")
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        self._seek(20)
        commands.execute("timeline.range.split_range")
        ranges = sorted(range_tlui)
        for r in ranges:
            assert r.get_data("label") == "lbl"
            assert r.get_data("color") == "#abcdef"
            assert r.get_data("comments") == "note"

    def test_split_preserves_pre_start_on_left_and_post_end_on_right(
        self, range_tlui, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=30)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "pre_start", 5)
        range_tlui.timeline.set_component_data(elem.id, "post_end", 35)
        self._seek(20)
        commands.execute("timeline.range.split_range")
        ranges = sorted(range_tlui)
        left, right = ranges
        assert left.get_data("pre_start") == 5
        assert right.get_data("post_end") == 35

    def test_split_preserves_outgoing_join(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=0, end=20)
        commands.execute("timeline.range.add_range", start=20, end=30)
        a, b = sorted(range_tlui)
        click_range_ui(a)
        click_range_ui(b, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        assert a.get_data("joined_right") == b.id

        self._seek(10)
        commands.execute("timeline.range.split_range")
        ranges = sorted(range_tlui)
        # A_left → A_right → B; the new range carries A's old joined_right.
        assert ranges[0].get_data("joined_right") == ranges[1].id
        assert ranges[1].get_data("joined_right") == ranges[2].id

    def test_split_separates_join_at_exact_boundary(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=20)
        commands.execute("timeline.range.add_range", start=20, end=30)
        a, b = sorted(range_tlui)
        click_range_ui(a)
        click_range_ui(b, modifier="ctrl")
        commands.execute("timeline.range.join_ranges")
        assert a.get_data("joined_right") == b.id

        self._seek(20)
        commands.execute("timeline.range.split_range")
        assert len(list(range_tlui)) == 2
        assert a.get_data("joined_right") is None
        # Splitting at the join boundary should also push the two halves
        # apart, the same way the Separate ranges command does.
        assert a.get_data("end") < 20
        assert b.get_data("start") > 20

    def test_split_at_time_outside_any_range_is_noop(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=20)
        self._seek(50)
        commands.execute("timeline.range.split_range")
        assert len(list(range_tlui)) == 1

    def test_split_at_range_end_without_join_is_noop(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=20)
        self._seek(20)
        commands.execute("timeline.range.split_range")
        assert len(list(range_tlui)) == 1

    def test_split_only_affects_selected_row(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_row")
        rows = range_tlui.rows
        commands.execute("timeline.range.add_range", row=rows[0], start=10, end=30)
        commands.execute("timeline.range.add_range", row=rows[1], start=10, end=30)
        settings.set("range_timeline", "split_all_rows", False)
        range_tlui.selected_row = rows[1]
        self._seek(20)
        commands.execute("timeline.range.split_range")
        row_0_ranges = [r for r in range_tlui if r.get_data("row_id") == rows[0].id]
        row_1_ranges = [r for r in range_tlui if r.get_data("row_id") == rows[1].id]
        assert len(row_0_ranges) == 1
        assert len(row_1_ranges) == 2

    def test_split_undoable(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=30)
        self._seek(20)
        with undoable():
            commands.execute("timeline.range.split_range")

    def test_split_via_context_menu(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=10, end=30)
        elem = range_tlui[0]
        self._seek(20)
        menu = RangeContextMenu(elem)
        action = get_command_action(menu, "timeline.range.split_range")
        assert action is not None
        action.trigger()
        assert len(list(range_tlui)) == 2

    def test_split_all_rows_setting_splits_every_row(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_row")
        rows = range_tlui.rows
        commands.execute("timeline.range.add_range", row=rows[0], start=10, end=30)
        commands.execute("timeline.range.add_range", row=rows[1], start=10, end=30)
        commands.execute("timeline.range.add_range", row=rows[2], start=10, end=30)
        settings.set("range_timeline", "split_all_rows", True)
        self._seek(20)
        commands.execute("timeline.range.split_range")
        for row in rows:
            row_ranges = [r for r in range_tlui if r.get_data("row_id") == row.id]
            assert len(row_ranges) == 2

    def test_split_all_rows_skips_rows_without_match(self, range_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_row")
        rows = range_tlui.rows
        commands.execute("timeline.range.add_range", row=rows[0], start=10, end=30)
        commands.execute("timeline.range.add_range", row=rows[1], start=50, end=70)
        settings.set("range_timeline", "split_all_rows", True)
        self._seek(20)
        commands.execute("timeline.range.split_range")
        row_0_ranges = [r for r in range_tlui if r.get_data("row_id") == rows[0].id]
        row_1_ranges = [r for r in range_tlui if r.get_data("row_id") == rows[1].id]
        assert len(row_0_ranges) == 2
        assert len(row_1_ranges) == 1

    def test_split_all_rows_off_uses_selected_row(self, range_tlui, tilia_state):
        # The toggle off should still be the default behaviour: only the
        # selected row gets split.
        tilia_state.duration = 100
        commands.execute("timeline.range.add_row")
        rows = range_tlui.rows
        commands.execute("timeline.range.add_range", row=rows[0], start=10, end=30)
        commands.execute("timeline.range.add_range", row=rows[1], start=10, end=30)
        settings.set("range_timeline", "split_all_rows", False)
        range_tlui.selected_row = rows[1]
        self._seek(20)
        commands.execute("timeline.range.split_range")
        row_0_ranges = [r for r in range_tlui if r.get_data("row_id") == rows[0].id]
        row_1_ranges = [r for r in range_tlui if r.get_data("row_id") == rows[1].id]
        assert len(row_0_ranges) == 1
        assert len(row_1_ranges) == 2

    def test_split_mode_commands_set_setting(self, range_tlui, tilia_state):
        settings.set("range_timeline", "split_all_rows", False)
        commands.execute("timeline.range.set_split_mode_all_rows")
        assert settings.get("range_timeline", "split_all_rows") is True
        commands.execute("timeline.range.set_split_mode_selected_row")
        assert settings.get("range_timeline", "split_all_rows") is False


class TestCommentsIndicator:
    def test_hidden_when_comments_empty(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        assert elem.comments_icon.isVisible() is False

    def test_shown_when_comments_added(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        assert elem.comments_icon.isVisible() is True

    def test_hidden_again_when_comments_cleared(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        range_tlui.timeline.set_component_data(elem.id, "comments", "")
        assert elem.comments_icon.isVisible() is False

    def test_hidden_when_range_too_narrow(self, range_tlui, tilia_state):
        # A very short range can't fit the icon — keep it hidden even when
        # comments are set so it doesn't render outside the body.
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=0, end=0.01)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        assert elem.comments_icon.isVisible() is False

    def test_repositions_on_end_change(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        original_x = elem.comments_icon.x()
        range_tlui.timeline.set_component_data(elem.id, "end", 30)
        assert elem.comments_icon.x() != original_x

    def test_clicking_icon_selects_range(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        click_timeline_ui_view(range_tlui.view, "left", 0, 0, elem.comments_icon)
        assert elem.is_selected()

    def test_dragging_icon_moves_range(self, range_tlui, tilia_state):
        # Regression: clicking the comments icon used to fall through to
        # `start_drag`, which couldn't classify the icon as a handle and
        # bailed with "unrecognised drag handle". The icon should behave
        # like the body — start a body drag.
        commands.execute("timeline.range.add_range", start=20, end=40)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        click_timeline_ui_view(range_tlui.view, "left", 0, 0, elem.comments_icon)
        center_x = time_x_converter.get_x_by_time(30)
        target_x = time_x_converter.get_x_by_time(60)
        drag_mouse_in_timeline_view(center_x, 0, release=False)
        drag_mouse_in_timeline_view(target_x, 0)
        assert elem.get_data("start") == 50
        assert elem.get_data("end") == 70

    def test_icon_font_uses_default_size_at_default_row_height(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        assert (
            elem.comments_icon.font().pixelSize()
            == RangeCommentsIcon.DEFAULT_PIXEL_SIZE
        )

    def test_icon_font_shrinks_with_small_row_height(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        with Serve(Get.FROM_USER_INT, (True, 10)):
            commands.execute("timeline.range.set_row_height")
        size = elem.comments_icon.font().pixelSize()
        assert size < RangeCommentsIcon.DEFAULT_PIXEL_SIZE
        assert size >= RangeCommentsIcon.MIN_PIXEL_SIZE

    def test_icon_font_floors_at_min(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        # Per-row height bypasses the timeline-wide >=10 validator.
        range_tlui.timeline.set_row_height(range_tlui.rows[0], 1)
        assert elem.comments_icon.font().pixelSize() == RangeCommentsIcon.MIN_PIXEL_SIZE

    def test_icon_visible_when_it_fits_in_row(self, range_tlui):
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        icon = elem.comments_icon
        row_height = range_tlui.row_height_for(range_tlui.rows[0])
        assert icon.fits_in_height(row_height)
        assert icon.isVisible()

    def test_icon_hidden_when_row_too_short_for_icon(self, range_tlui):
        # Once shrinking the font has hit its floor, the icon is hidden so
        # it can't spill into the next row. Per-row heights bypass the
        # >=10 timeline-wide validator.
        commands.execute("timeline.range.add_range", start=0, end=10)
        elem = range_tlui[0]
        range_tlui.timeline.set_component_data(elem.id, "comments", "note")
        range_tlui.timeline.set_row_height(range_tlui.rows[0], 1)
        assert elem.comments_icon.isVisible() is False


def test_timeline_menu_has_range_submenu(tluis, qtui, range_tlui, tilia_state):
    expected_actions = ["timelines.import.range"]
    menu = get_main_window_menu(qtui, "Timelines")
    submenu = get_submenu(menu, "Range")
    assert submenu

    for a in expected_actions:
        assert get_qaction(a) in submenu.actions()


class TestSharedShortcuts:
    """`e` (merge) and `s` (split) are bound to both range and hierarchy
    commands. The dispatcher in TimelineUIs picks exactly one command based
    on whichever timeline was clicked most recently, then fires it; the
    other bound command is not invoked. Regression coverage for Qt's
    "Ambiguous shortcut overload" warning."""

    def _seek(self, time: float) -> None:
        commands.execute("media.seek", time)

    def test_s_splits_only_range_when_range_clicked_last(
        self, range_tlui, hierarchy_tlui, tluis, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=0, end=30)
        self._add_hierarchy(hierarchy_tlui, 0, 30, 1)
        # Ctrl-click on empty space bumps range to the top of select order
        # without disturbing the (empty) selection state.
        click_timeline_ui(range_tlui, time=20, modifier="ctrl")
        self._seek(15)

        press_key("s")

        assert len(range_tlui) == 2
        assert len(hierarchy_tlui) == 1

    def test_s_splits_only_hierarchy_when_hierarchy_clicked_last(
        self, range_tlui, hierarchy_tlui, tluis, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute("timeline.range.add_range", start=0, end=30)
        self._add_hierarchy(hierarchy_tlui, 0, 30, 1)
        click_timeline_ui(hierarchy_tlui, time=20, modifier="ctrl")
        self._seek(15)

        press_key("s")

        assert len(hierarchy_tlui) == 2
        assert len(range_tlui) == 1

    def test_e_merges_only_range_when_range_clicked_last(
        self, range_tlui, hierarchy_tlui, tluis, tilia_state
    ):
        tilia_state.duration = 100
        a = self._add_range(range_tlui, 0, 10)
        b = self._add_range(range_tlui, 20, 30)
        range_tlui.select_element(a)
        range_tlui.select_element(b)

        h1 = self._add_hierarchy(hierarchy_tlui, 0, 10, 1)
        h2 = self._add_hierarchy(hierarchy_tlui, 10, 20, 1)
        hierarchy_tlui.select_element(h1)
        hierarchy_tlui.select_element(h2)

        click_timeline_ui(range_tlui, time=15, modifier="ctrl")

        press_key("e")

        assert len(range_tlui) == 1
        assert len(hierarchy_tlui) == 2

    def test_e_merges_only_hierarchy_when_hierarchy_clicked_last(
        self, range_tlui, hierarchy_tlui, tluis, tilia_state
    ):
        tilia_state.duration = 100
        a = self._add_range(range_tlui, 0, 10)
        b = self._add_range(range_tlui, 20, 30)
        range_tlui.select_element(a)
        range_tlui.select_element(b)

        h1 = self._add_hierarchy(hierarchy_tlui, 0, 10, 1)
        h2 = self._add_hierarchy(hierarchy_tlui, 10, 20, 1)
        hierarchy_tlui.select_element(h1)
        hierarchy_tlui.select_element(h2)

        click_timeline_ui(hierarchy_tlui, time=25, modifier="ctrl")

        press_key("e")

        assert len(hierarchy_tlui) == 1
        assert len(range_tlui) == 2

    def test_no_ambiguous_shortcut_warning_when_both_timelines_visible(
        self, range_tlui, hierarchy_tlui, tilia_state, tilia_errors
    ):
        tilia_state.duration = 100
        self._add_range(range_tlui, 0, 10)
        self._add_hierarchy(hierarchy_tlui, 0, 10, 1)
        self._seek(5)

        press_key("s")
        press_key("e")

        # If Qt had warned, qtui would have surfaced it via
        # tilia.errors.AMBIGUOUS_SHORTCUT.
        for err in tilia_errors.errors:
            assert "Ambiguous" not in err["title"]

    def test_non_timeline_collision_surfaces_error(self, tluis, tilia_errors):
        # If the bound commands don't follow the timeline.{kind}.{action}
        # convention, the dispatcher can't pick a winner — surface as an
        # error rather than dropping silently.
        post(Post.SHARED_SHORTCUT_FIRED, ("file.open", "edit.undo"))
        assert any("Ambiguous" in err["title"] for err in tilia_errors.errors)

    def test_same_kind_collision_surfaces_error(
        self, range_tlui, tilia_state, tilia_errors
    ):
        # Two commands of the *same* kind bound to the same shortcut is a
        # registration bug (there's no "most recently clicked" signal to
        # resolve between two actions on one kind) — surface an error and
        # don't silently dispatch to whichever name happens to come first.
        tilia_state.duration = 100
        self._add_range(range_tlui, 0, 10)

        post(
            Post.SHARED_SHORTCUT_FIRED,
            ("timeline.range.split_range", "timeline.range.merge_ranges"),
        )

        assert any("Ambiguous" in err["title"] for err in tilia_errors.errors)
        assert len(range_tlui) == 1

    def test_ambiguous_shortcut_warning_surfaces_to_user(self, qtui, tilia_errors):
        from PySide6.QtCore import QtMsgType

        from tilia.boot import handle_qt_log_message

        # Mimic the Qt log call: handle_qt_log_message receives type, context,
        # message. We construct a minimal context-like object with the two
        # attributes the handler reads.
        class _Ctx:
            file = "test_file"
            line = 0

        handle_qt_log_message(
            QtMsgType.QtWarningMsg,
            _Ctx(),
            "QAction::eventFilter: Ambiguous shortcut overload: S",
        )

        assert any("Ambiguous" in err["title"] for err in tilia_errors.errors)

    @staticmethod
    def _add_range(range_tlui, start, end):
        commands.execute("timeline.range.add_range", start=start, end=end)
        return range_tlui[len(range_tlui) - 1]

    @staticmethod
    def _add_hierarchy(hierarchy_tlui, start, end, level):
        commands.execute("timeline.hierarchy.add", start=start, end=end, level=level)
        return hierarchy_tlui[len(hierarchy_tlui) - 1]
