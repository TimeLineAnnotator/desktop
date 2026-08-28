from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import tilia.errors
from tests.mock import Serve, patch_yes_or_no_dialog
from tests.utils import get_command_names
from tilia.requests import Get, Post, post
from tilia.settings import settings
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.ui import commands
from tilia.ui.timelines.hierarchy import HierarchyUI
from tilia.ui.timelines.hierarchy.context_menu import HierarchyContextMenu


@pytest.fixture
def tlui(hierarchy_tlui):
    return hierarchy_tlui


def get_hierarchy(tlui, start: float, level: int) -> Hierarchy:
    """Look a hierarchy up by its data, for setups that aren't in sorted order."""
    return next(c for c in tlui.timeline if c.start == start and c.level == level)


def set_dummy_copy_attributes(hierarchy: Hierarchy) -> None:
    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.values:
        if attr == "color":
            hierarchy.set_data(attr, "#FFFFFF")
        else:
            hierarchy.set_data(attr, f"test {attr} - {id(hierarchy)}")


def assert_are_copies(hierarchy1: Hierarchy, hierarchy2: Hierarchy):
    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.values:
        assert getattr(hierarchy1, attr) == getattr(hierarchy2, attr)


def assert_is_copy_data_of(copy_data: dict, hierarchy_ui: HierarchyUI):
    for attr, value in copy_data.items():
        assert hierarchy_ui.get_data(attr) == value

    if children := hierarchy_ui.get_data("children"):
        for index, child in enumerate(children):
            assert_is_copy_data_of(child, copy_data["children"][index])


class TestActions:
    def test_increase_level(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)
        commands.execute("timeline.hierarchy.add", start=3, end=4, level=1)

        tlui.select_element(tlui[0])
        commands.execute("timeline.hierarchy.increase_level")

        assert tlui[2].get_data("level") == 2
        assert tlui[2].get_data("start") == 0
        assert tlui[2].get_data("end") == 1
        assert tlui[0].get_data("level") == 1
        assert tlui[1].get_data("level") == 1

    def test_increase_level_multiple_hierarchies(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)
        commands.execute("timeline.hierarchy.add", start=3, end=4, level=1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.select_element(tlui[2])
        commands.execute("timeline.hierarchy.increase_level")

        assert tlui[0].get_data("level") == 2
        assert tlui[1].get_data("level") == 2
        assert tlui[2].get_data("level") == 2

    def test_decrease_level(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=2)
        commands.execute("timeline.hierarchy.add", start=3, end=4, level=2)

        tlui.select_element(tlui[0])
        commands.execute("timeline.hierarchy.decrease_level")

        assert tlui[0].get_data("level") == 1
        assert tlui[1].get_data("level") == 2
        assert tlui[2].get_data("level") == 2

    def test_decrease_level_multiple_hierarchies(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=2)
        commands.execute("timeline.hierarchy.add", start=3, end=4, level=2)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.select_element(tlui[2])
        commands.execute("timeline.hierarchy.decrease_level")

        assert tlui[0].get_data("level") == 1
        assert tlui[1].get_data("level") == 1
        assert tlui[2].get_data("level") == 1

    def test_increase_level_via_keypress(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        tlui.select_element(tlui[0])
        post(Post.TIMELINE_KEY_PRESS_CTRL_UP)
        assert tlui[0].get_data("level") == 2

    def test_decrease_level_via_keypress(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)
        tlui.select_element(tlui[0])
        post(Post.TIMELINE_KEY_PRESS_CTRL_DOWN)
        assert tlui[0].get_data("level") == 1

    def test_set_color(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_COLOR, (True, QColor("#000"))):
            commands.execute("timeline.component.set_color")

        assert tlui[0].get_data("color") == "#000000"

    def test_reset_color(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_COLOR, (True, QColor("#000"))):
            commands.execute("timeline.component.set_color")

        commands.execute("timeline.component.reset_color")

        assert tlui[0].get_data("color") is None

    def test_add_pre_start(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0.1, end=1, level=1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_FLOAT, (True, 0.1)):
            commands.execute("timeline.hierarchy.add_pre_start")

        assert tlui[0].get_data("pre_start") != tlui[0].get_data("start")
        assert tlui[0].pre_start_handle

    def test_add_post_end(self, tlui, tilia_state):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_FLOAT, (True, 0.1)):
            commands.execute("timeline.hierarchy.add_post_end")

        assert tlui[0].get_data("post_end") != tlui[0].get_data("end")
        assert tlui[0].post_end_handle

    def test_whisker_vline_has_resize_cursor(self, tlui):
        # CursorMixIn sets the cursor directly on the item (via
        # QGraphicsItem.setCursor) instead of push/pop-ing a global
        # override cursor on hover — Qt applies/restores it automatically,
        # so there's no more manual hover/hide bookkeeping to regression
        # test here (see tilia/ui/timelines/cursors.py).
        commands.execute("timeline.hierarchy.add", start=0.1, end=1, level=1)
        tlui.select_element(tlui[0])
        with Serve(Get.FROM_USER_FLOAT, (True, 0.05)):
            commands.execute("timeline.hierarchy.add_pre_start")
        vline = tlui[0].pre_start_handle.vertical_line
        assert vline.cursor().shape() == Qt.CursorShape.SizeHorCursor

    def test_split(self, tlui, tilia_state):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        assert len(tlui) == 1
        commands.execute("media.seek", 0.5)
        commands.execute("timeline.hierarchy.split")

        assert len(tlui) == 2

    def test_merge(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        commands.execute("timeline.hierarchy.merge")

        assert len(tlui) == 1

    def test_group(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        commands.execute("timeline.hierarchy.group")

        assert len(tlui) == 3

    def test_group_no_units_selected_does_nothing(self, tlui, tilia_errors):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)

        commands.execute("timeline.hierarchy.group")

        assert len(tlui) == 1
        tilia_errors.assert_no_error()

    def test_delete_elements(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)

        tlui.select_element(tlui[0])

        commands.execute("timeline.component.delete")

        assert len(tlui) == 0

    def test_create_hierarchy_below(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)

        tlui.select_element(tlui[0])

        commands.execute("timeline.hierarchy.create_child")

        assert len(tlui) == 2


class TestAddFrameValidation:
    """Pre-start / post-end add is offered only when a frame fits (issue #495).

    Pre-start extends left of ``start`` (toward 0); post-end extends right of
    ``end`` (toward the media duration). When there isn't room for at least the
    minimum length, the context menu must not offer the add.
    """

    PRE_START = "timeline.hierarchy.add_pre_start"
    POST_END = "timeline.hierarchy.add_post_end"

    # Context-menu presence.

    def test_pre_start_in_menu_when_room_before_start(self, tlui):
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)
        menu = HierarchyContextMenu(tlui[0])
        assert self.PRE_START in get_command_names(menu)

    def test_pre_start_not_in_menu_when_start_at_zero(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        menu = HierarchyContextMenu(tlui[0])
        assert self.PRE_START not in get_command_names(menu)

    def test_post_end_in_menu_when_room_after_end(self, tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.hierarchy.add", start=0, end=50, level=1)
        menu = HierarchyContextMenu(tlui[0])
        assert self.POST_END in get_command_names(menu)

    def test_post_end_not_in_menu_when_end_at_duration(self, tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.hierarchy.add", start=0, end=100, level=1)
        menu = HierarchyContextMenu(tlui[0])
        assert self.POST_END not in get_command_names(menu)

    # Too little room for a valid frame: the menu must not offer the add.

    def test_pre_start_not_in_menu_when_room_below_min_length(self, tlui):
        commands.execute(
            "timeline.hierarchy.add",
            start=HierarchyUI.MIN_FRAME_LENGTH / 2,
            end=1,
            level=1,
        )
        menu = HierarchyContextMenu(tlui[0])
        assert self.PRE_START not in get_command_names(menu)

    def test_post_end_not_in_menu_when_room_below_min_length(self, tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute(
            "timeline.hierarchy.add",
            start=0,
            end=tilia_state.duration - HierarchyUI.MIN_FRAME_LENGTH / 2,
            level=1,
        )
        menu = HierarchyContextMenu(tlui[0])
        assert self.POST_END not in get_command_names(menu)


class TestCopyPaste:
    def test_paste(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=1, level=1, label="paste test"
        )
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)

        tlui.select_element(tlui[0])
        commands.execute("timeline.component.copy")
        tlui.deselect_element(tlui[0])

        tlui.select_element(tlui[1])
        commands.execute("timeline.component.paste")

        assert tlui[1].get_data("label") == "paste test"

    def test_paste_without_children_into_selected_elements(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=0.5, level=1, color="#000000"
        )
        set_dummy_copy_attributes(tlui[0])
        tlui.select_element(tlui[0])
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()

        commands.execute(
            "timeline.hierarchy.add", start=0.5, end=1, level=1, color="#000000"
        )
        hrc1, hrc2 = tlui.timeline[0], tlui.timeline[1]  # order will change with paste

        tlui.select_element(tlui[1])
        commands.execute("timeline.component.paste")

        assert_are_copies(hrc1, hrc2)

    def test_paste_with_children_into_selected_elements_without_rescaling(
        self, tlui, tilia_state
    ):
        commands.execute("timeline.hierarchy.add", start=0, end=0.5, level=1)
        commands.execute("timeline.hierarchy.add", start=0.5, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=2)

        # order will change with paste
        hrc1 = tlui.timeline[0]
        hrc2 = tlui.timeline[1]
        _ = tlui.timeline[2]
        hrc4 = tlui.timeline[3]

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        tlui.select_element(tlui[2])
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()

        tlui.select_element(tlui[3])
        commands.execute("timeline.component.paste_complete")

        assert len(tlui.elements) == 6
        assert len(hrc4.children) == 2

        copied_children_1, copied_children_2 = sorted(hrc4.children)

        assert copied_children_1.parent == hrc4
        assert copied_children_1.start == 1.0
        assert copied_children_1.end == 1.5

        assert copied_children_2.parent == hrc4
        assert copied_children_2.start == 1.5
        assert copied_children_2.end == 2.0

        assert_are_copies(copied_children_1, hrc1)
        assert_are_copies(copied_children_2, hrc2)

    def test_paste_with_children_into_selected_elements_with_rescaling(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=0.5, level=1)
        commands.execute("timeline.hierarchy.add", start=0.5, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)
        commands.execute("timeline.hierarchy.add", start=1, end=1.5, level=2)

        # order will change with paste
        hrc1 = tlui.timeline[0]
        hrc2 = tlui.timeline[1]
        _ = tlui.timeline[2]
        hrc4 = tlui.timeline[3]

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        tlui.select_element(tlui[2])
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()

        tlui.select_element(tlui[3])
        commands.execute("timeline.component.paste_complete")

        copied_children_1, copied_children_2 = sorted(hrc4.children)

        assert copied_children_1.parent == hrc4
        assert copied_children_1.start == 1.0
        assert copied_children_1.end == 1.25

        assert copied_children_2.parent == hrc4
        assert copied_children_2.start == 1.25
        assert copied_children_2.end == 1.5

    def test_paste_into_hierarchy_that_has_grandchildren(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=0.5, level=1
        )  # grandchild
        commands.execute(
            "timeline.hierarchy.add", start=0.5, end=1, level=1
        )  # grandchild
        commands.execute(
            "timeline.hierarchy.add", start=1, end=1.5, level=1
        )  # grandchild
        commands.execute(
            "timeline.hierarchy.add", start=1.5, end=2, level=1
        )  # grandchild
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)  # child
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=2)  # child
        commands.execute(
            "timeline.hierarchy.add", start=0, end=2, level=3
        )  # grandparent
        destination = tlui.timeline[6]

        commands.execute("timeline.hierarchy.add", start=2, end=2.25, level=2)  # child
        commands.execute(
            "timeline.hierarchy.add", start=2.25, end=2.5, level=2
        )  # child
        commands.execute(
            "timeline.hierarchy.add", start=2.5, end=2.75, level=2
        )  # child
        commands.execute("timeline.hierarchy.add", start=2.75, end=3, level=2)  # child
        commands.execute("timeline.hierarchy.add", start=2, end=3, level=3)  # parent
        source = tlui.timeline[11]

        tlui.select_element(tlui.get_element(source.id))
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()
        tlui.select_element(tlui.get_element(destination.id))
        commands.execute("timeline.component.paste_complete")

        assert len(destination.children) == 4
        for i, child in enumerate(sorted(destination.children)):
            assert child.parent == destination
            assert child.start == i * 0.5
            assert child.end == (i + 1) * 0.5

    def test_paste_from_hierarchy_with_grandchildren(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=0.5, level=1)
        commands.execute("timeline.hierarchy.add", start=0.5, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=0, end=0.5, level=2)
        commands.execute("timeline.hierarchy.add", start=0.5, end=1, level=2)
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=3)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=3)
        hrc6 = tlui.timeline[5]

        set_dummy_copy_attributes(tlui.timeline[0])
        set_dummy_copy_attributes(tlui.timeline[1])

        tlui.select_element(tlui[4])
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()

        tlui.select_element(tlui[5])
        commands.execute("timeline.component.paste_complete")

        copied_children_1, copied_children_2 = sorted(hrc6.children)

        assert len(copied_children_1.children) == 1
        assert copied_children_1.children[0].start == 1
        assert copied_children_1.children[0].end == 1.5

        assert len(copied_children_2.children) == 1
        assert copied_children_2.children[0].start == 1.5
        assert copied_children_2.children[0].end == 2.0

    def test_paste_with_children_into_different_level_fails(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=0.5, level=1)
        commands.execute("timeline.hierarchy.add", start=0.5, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)
        commands.execute("timeline.hierarchy.add", start=1, end=1.5, level=3)

        tlui.select_element(tlui[2])
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()

        tlui.select_element(tlui[1])
        component_state1 = tlui.timeline.components
        commands.execute("timeline.component.paste_complete")
        component_state2 = tlui.timeline.components

        assert component_state1 == component_state2

    def test_paste_complete_reports_child_creation_failure(self, tlui):
        commands.execute("timeline.hierarchy.add", start=40, end=45, level=1)
        commands.execute("timeline.hierarchy.add", start=45, end=70, level=1)
        commands.execute("timeline.hierarchy.add", start=40, end=70, level=2)
        commands.execute("timeline.hierarchy.add", start=0, end=23.4, level=2)
        root = get_hierarchy(tlui, 40, 2)
        target = get_hierarchy(tlui, 0, 2)

        tlui.select_element(tlui.get_element(root.id))
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()
        tlui.select_element(tlui.get_element(target.id))

        with (
            patch.object(
                tlui.timeline, "create_component", return_value=(None, "no room")
            ),
            patch("tilia.errors.display") as display,
        ):
            commands.execute("timeline.component.paste_complete")

        display.assert_called_once()
        assert display.call_args.args[0] == tilia.errors.COMPONENTS_PASTE_ERROR
        assert "no room" in display.call_args.args[1]
        assert not target.children

    def test_paste_complete_reports_no_error_when_children_are_created(self, tlui):
        commands.execute("timeline.hierarchy.add", start=40, end=45, level=1)
        commands.execute("timeline.hierarchy.add", start=45, end=70, level=1)
        commands.execute("timeline.hierarchy.add", start=40, end=70, level=2)
        commands.execute("timeline.hierarchy.add", start=0, end=23.4, level=2)
        root = get_hierarchy(tlui, 40, 2)
        target = get_hierarchy(tlui, 0, 2)

        tlui.select_element(tlui.get_element(root.id))
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()
        tlui.select_element(tlui.get_element(target.id))

        with patch("tilia.errors.display") as display:
            commands.execute("timeline.component.paste_complete")

        display.assert_not_called()
        assert len(target.children) == 2

    def test_paste_complete_keeps_shared_boundaries_exact(self, tlui):
        # Siblings sharing a boundary in the source must still share it exactly
        # after being rescaled into the target. Scaling each component
        # independently would leave the two a few ulps apart, which later
        # operations read as an overlap.
        commands.execute("timeline.hierarchy.add", start=40, end=45, level=3)
        commands.execute("timeline.hierarchy.add", start=45, end=70, level=3)
        commands.execute("timeline.hierarchy.add", start=40, end=70, level=4)
        commands.execute("timeline.hierarchy.add", start=0, end=23.4, level=4)
        root = get_hierarchy(tlui, 40, 4)
        target = get_hierarchy(tlui, 0, 4)

        tlui.select_element(tlui.get_element(root.id))
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()
        tlui.select_element(tlui.get_element(target.id))
        commands.execute("timeline.component.paste_complete")

        left, right = sorted(target.children)

        assert left.end == right.start
        # the subtree must also line up exactly with the target it was pasted into
        assert left.start == target.start
        assert right.end == target.end

    def test_paste_complete_keeps_grandchild_boundaries_exact(self, tlui):
        # Nesting compounds any per-component error, since each level would
        # re-derive its scale factor from the already-rounded bounds of the
        # level above. One map for the whole subtree avoids that.
        commands.execute("timeline.hierarchy.add", start=40, end=45, level=1)
        commands.execute("timeline.hierarchy.add", start=45, end=52.5, level=1)
        commands.execute("timeline.hierarchy.add", start=40, end=52.5, level=2)
        commands.execute("timeline.hierarchy.add", start=52.5, end=70, level=2)
        commands.execute("timeline.hierarchy.add", start=40, end=70, level=3)
        commands.execute("timeline.hierarchy.add", start=0, end=23.4, level=3)
        root = get_hierarchy(tlui, 40, 3)
        target = get_hierarchy(tlui, 0, 3)

        tlui.select_element(tlui.get_element(root.id))
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()
        tlui.select_element(tlui.get_element(target.id))
        commands.execute("timeline.component.paste_complete")

        left_child, right_child = sorted(target.children)
        grandchild_1, grandchild_2 = sorted(left_child.children)

        assert grandchild_1.end == grandchild_2.start
        # grandchildren must align exactly with their parent's bounds, and the
        # children with each other
        assert grandchild_1.start == left_child.start
        assert grandchild_2.end == left_child.end == right_child.start

    def test_paste_complete_into_same_timespan_is_exact(self, tlui):
        # An identity rescale must not perturb any boundary.
        commands.execute("timeline.hierarchy.add", start=40, end=45.55, level=1)
        commands.execute("timeline.hierarchy.add", start=45.55, end=70, level=1)
        commands.execute("timeline.hierarchy.add", start=40, end=70, level=2)
        commands.execute("timeline.hierarchy.add", start=70, end=100, level=2)
        root = get_hierarchy(tlui, 40, 2)
        target = get_hierarchy(tlui, 70, 2)

        tlui.select_element(tlui.get_element(root.id))
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()
        tlui.select_element(tlui.get_element(target.id))
        commands.execute("timeline.component.paste_complete")

        left, right = sorted(target.children)

        assert left.start == 70
        assert left.end == right.start == 75.55
        assert right.end == 100

    def test_group_split_child_of_pasted_hierarchy(self, tlui):
        # End-to-end guard over a whole editing flow that runs on rescaled
        # boundaries: paste a subtree into a shorter target, then create a
        # child inside one of the pasted units, lower its level, split it and
        # group the halves. Every step compares boundaries the paste produced,
        # so any drift between a pasted unit and its neighbour surfaces here as
        # a spurious overlap.
        # Source subtree lives at [40, 70]; the two level-3 children share the
        # boundary 45, pasted into the shorter target [0, 23.4].
        commands.execute("timeline.hierarchy.add", start=40, end=45, level=3)
        # the right child is left childless, so it is the one that gets split
        commands.execute("timeline.hierarchy.add", start=45, end=70, level=3)
        commands.execute("timeline.hierarchy.add", start=40, end=70, level=4)
        commands.execute("timeline.hierarchy.add", start=0, end=23.4, level=4)
        root = get_hierarchy(tlui, 40, 4)
        target = get_hierarchy(tlui, 0, 4)

        tlui.select_element(tlui.get_element(root.id))
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()
        tlui.select_element(tlui.get_element(target.id))
        commands.execute("timeline.component.paste_complete")

        # the pasted right child. Components with end <= 30 are the pasted
        # target subtree; the source subtree lives at >= 40.
        pasted_right_child = max(
            (c for c in tlui.timeline if c.level == 3 and c.end <= 30),
            key=lambda c: c.start,
        )

        tlui.deselect_all_elements()
        tlui.select_element(tlui.get_element(pasted_right_child.id))
        commands.execute("timeline.hierarchy.create_child")  # -> level 2 child

        child = max(c for c in tlui.timeline if c.level == 2 and c.end <= 30)
        tlui.deselect_all_elements()
        tlui.select_element(tlui.get_element(child.id))
        commands.execute("timeline.hierarchy.decrease_level")  # level 2 -> 1

        commands.execute(
            "timeline.hierarchy.split",
            time=(pasted_right_child.start + pasted_right_child.end) / 2,
        )

        halves = sorted(
            (c for c in tlui.timeline if c.level == 1 and c.end <= 30),
            key=lambda c: c.start,
        )
        assert len(halves) == 2
        tlui.deselect_all_elements()
        for half in halves:
            tlui.select_element(tlui.get_element(half.id))
        commands.execute("timeline.hierarchy.group")

        grouped = [c for c in tlui.timeline if c.level == 2 and c.end <= 30]
        assert len(grouped) == 1
        assert halves[0].parent == halves[1].parent == grouped[0]


class TestCreateHierarchy:
    def test_create_single(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)

        assert len(tlui.elements) == 1

    def test_create_multiple(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=0.1, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=0.2, end=1, level=1)
        assert len(tlui.elements) == 3

    def test_add_command_creates_component(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)

        assert len(tlui.elements) == 1
        component = tlui.timeline[0]
        assert component.start == 0
        assert component.end == 1
        assert component.level == 2

    def test_add_command_passes_kwargs(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=1, level=1, label="my label"
        )

        component = tlui.timeline[0]
        assert component.get_data("label") == "my label"


class TestUndoRedo:
    def test_split(self, tlui, tluis):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.split", time=0.5)

        commands.execute("edit.undo")
        assert len(tlui) == 1

        commands.execute("edit.redo")
        assert len(tlui) == 2

    def test_merge(self, tlui, tluis):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.merge")

        commands.execute("edit.undo")
        assert len(tlui) == 2

        commands.execute("edit.redo")
        assert len(tlui) == 1

    def test_increase_level(self, tlui, tluis):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.increase_level")

        commands.execute("edit.undo")
        assert tlui.elements[0].get_data("level") == 1

        commands.execute("edit.redo")
        assert tlui.elements[0].get_data("level") == 2

    def test_decrease_level(self, tlui, tluis):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)
        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.decrease_level")

        commands.execute("edit.undo")
        assert tlui.elements[0].get_data("level") == 2

        commands.execute("edit.redo")
        assert tlui.elements[0].get_data("level") == 1

    def test_group(self, tlui, tluis):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.group")

        commands.execute("edit.undo")
        assert len(tlui) == 2

        commands.execute("edit.redo")
        assert len(tlui) == 3

    def test_delete(self, tlui, tluis):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)

        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")
        assert len(tlui) == 1

        commands.execute("edit.redo")
        assert len(tlui) == 0

    def test_delete_parent_and_child(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")
        assert len(tlui) == 2

        commands.execute("edit.redo")
        assert len(tlui) == 0

    def test_create_unit_below(self, tlui, tluis):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)

        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.create_child")

        commands.execute("edit.undo")
        assert len(tlui) == 1

        commands.execute("edit.redo")
        assert len(tlui) == 2

    def test_paste(self, tlui, tluis):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=1, level=1, label="paste test"
        )
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)
        post(Post.APP_STATE_RECORD, "test state")

        tlui.select_element(tlui[0])
        commands.execute("timeline.component.copy")
        tlui.deselect_element(tlui[0])

        tlui.select_element(tlui[1])
        commands.execute("timeline.component.paste")

        assert tlui[1].get_data("label") == "paste test"

        commands.execute("edit.undo")
        assert tlui[1].get_data("label") == ""

        commands.execute("edit.redo")
        assert tlui[1].get_data("label") == "paste test"

    def test_paste_with_children(self, tlui, tluis):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)
        commands.execute("timeline.hierarchy.add", start=0, end=2, level=2)
        commands.execute("timeline.hierarchy.add", start=2, end=3, level=2)

        # Must record state explicitly, as we have not executed any command
        post(Post.APP_STATE_RECORD, "test state")

        tlui.select_element(tlui[2])
        commands.execute("timeline.component.copy")
        tlui.deselect_element(tlui[2])

        tlui.select_element(tlui[3])

        commands.execute("timeline.component.paste_complete")

        commands.execute("edit.undo")
        assert len(tlui) == 4

        commands.execute("edit.redo")
        assert len(tlui) == 6


class TestCreateChild:
    def test_create_child(self, tlui, tluis):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)

        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.create_child")

        commands.execute("edit.undo")
        assert len(tlui) == 1

        commands.execute("edit.redo")
        assert len(tlui) == 2

    def test_at_lowest_level_user_declines_new_level(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)

        tlui.select_element(tlui[0])

        settings.set("hierarchy_timeline", "prompt_create_level_below", True)
        with patch_yes_or_no_dialog(False):
            commands.execute("timeline.hierarchy.create_child")

        assert len(tlui) == 1
        assert tlui[0].get_data("level") == 1

    class TestUserAcceptsNewLevel:
        def test_single_hierarchy(self, tlui):
            commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)

            tlui.select_element(tlui[0])

            settings.set("hierarchy_timeline", "prompt_create_level_below", True)
            with patch_yes_or_no_dialog(True):
                commands.execute("timeline.hierarchy.create_child")

            assert len(tlui) == 2
            assert tlui[0].get_data("level") == 1
            assert tlui[1].get_data("level") == 2

        def test_with_parent(self, tlui):
            commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
            commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)

            tlui.select_element(tlui[0])

            settings.set("hierarchy_timeline", "prompt_create_level_below", True)
            with patch_yes_or_no_dialog(True):
                commands.execute("timeline.hierarchy.create_child")

            assert len(tlui) == 3
            assert tlui[0].get_data("level") == 1
            assert tlui[1].get_data("level") == 2
            assert tlui[2].get_data("level") == 3

        def test_with_siblings(self, tlui):
            commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
            commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)
            commands.execute("timeline.hierarchy.add", start=2, end=3, level=1)

            tlui.select_element(tlui[0])

            settings.set("hierarchy_timeline", "prompt_create_level_below", True)
            with patch_yes_or_no_dialog(True):
                commands.execute("timeline.hierarchy.create_child")

            assert len(tlui) == 4
            assert tlui[0].get_data("level") == 1
            assert tlui[1].get_data("level") == 2
            assert tlui[2].get_data("level") == 2
            assert tlui[3].get_data("level") == 2

        def test_prompt_create_level_below_is_false(self, tlui):
            commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)

            tlui.select_element(tlui[0])

            settings.set("hierarchy_timeline", "prompt_create_level_below", False)
            commands.execute("timeline.hierarchy.create_child")

            assert len(tlui) == 2


class TestClear:
    def test_initial_hierarchy_doesnt_trigger_confirmation(self, tlui, tilia_state):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=tilia_state.duration, level=1
        )

        commands.execute("timeline.clear", tlui)

        assert tlui.is_empty

    def test_initial_hierarchy_with_edited_label_triggers_confirmation(
        self, tlui, tilia_state
    ):
        commands.execute(
            "timeline.hierarchy.add",
            start=0,
            end=tilia_state.duration,
            level=1,
            label="I WAS EDITED",
        )

        with patch_yes_or_no_dialog(False):
            commands.execute("timeline.clear", tlui)

        # we must test explictly for len, to ensure the component was not deleted
        assert len(tlui) == 1

    def test_not_empty(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        commands.execute("timeline.hierarchy.add", start=1, end=2, level=1)
        commands.execute("timeline.hierarchy.add", start=2, end=3, level=1)

        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", tlui)

        assert tlui.is_empty
