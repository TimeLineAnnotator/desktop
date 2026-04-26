import pytest
from PySide6.QtGui import QColor

from tests.mock import Serve, patch_yes_or_no_dialog
from tilia.requests import Get, Post, post
from tilia.settings import settings
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.ui import commands
from tilia.ui.timelines.hierarchy import HierarchyUI


@pytest.fixture
def tlui(hierarchy_tlui):
    return hierarchy_tlui


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
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)
        tlui.create_hierarchy(3, 4, 1)

        tlui.select_element(tlui[0])
        commands.execute("timeline.hierarchy.increase_level")

        assert tlui[2].get_data("level") == 2
        assert tlui[2].get_data("start") == 0
        assert tlui[2].get_data("end") == 1
        assert tlui[0].get_data("level") == 1
        assert tlui[1].get_data("level") == 1

    def test_increase_level_multiple_hierarchies(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)
        tlui.create_hierarchy(3, 4, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.select_element(tlui[2])
        commands.execute("timeline.hierarchy.increase_level")

        assert tlui[0].get_data("level") == 2
        assert tlui[1].get_data("level") == 2
        assert tlui[2].get_data("level") == 2

    def test_decrease_level(self, tlui):
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 2, 2)
        tlui.create_hierarchy(3, 4, 2)

        tlui.select_element(tlui[0])
        commands.execute("timeline.hierarchy.decrease_level")

        assert tlui[0].get_data("level") == 1
        assert tlui[1].get_data("level") == 2
        assert tlui[2].get_data("level") == 2

    def test_decrease_level_multiple_hierarchies(self, tlui):
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 2, 2)
        tlui.create_hierarchy(3, 4, 2)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.select_element(tlui[2])
        commands.execute("timeline.hierarchy.decrease_level")

        assert tlui[0].get_data("level") == 1
        assert tlui[1].get_data("level") == 1
        assert tlui[2].get_data("level") == 1

    def test_set_color(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_COLOR, (True, QColor("#000"))):
            commands.execute("timeline.component.set_color")

        assert tlui[0].get_data("color") == "#000000"

    def test_reset_color(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_COLOR, (True, QColor("#000"))):
            commands.execute("timeline.component.set_color")

        commands.execute("timeline.component.reset_color")

        assert tlui[0].get_data("color") is None

    def test_add_pre_start(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_FLOAT, (True, 0.1)):
            commands.execute("timeline.hierarchy.add_pre_start")

        assert tlui[0].get_data("pre_start") != tlui[0].get_data("start")
        assert tlui[0].pre_start_handle

    def test_add_post_end(self, tlui, tilia_state):
        tlui.create_hierarchy(0, 1, 1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_FLOAT, (True, 0.1)):
            commands.execute("timeline.hierarchy.add_post_end")

        assert tlui[0].get_data("post_end") != tlui[0].get_data("end")
        assert tlui[0].post_end_handle

    def test_split(self, tlui, tilia_state):
        tlui.create_hierarchy(0, 1, 1)
        assert len(tlui) == 1
        tilia_state.current_time = 0.5
        commands.execute("timeline.hierarchy.split")

        assert len(tlui) == 2

    def test_merge(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        commands.execute("timeline.hierarchy.merge")

        assert len(tlui) == 1

    def test_group(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        commands.execute("timeline.hierarchy.group")

        assert len(tlui) == 3

    def test_group_no_units_selected_does_nothing(self, tlui, tilia_errors):
        tlui.create_hierarchy(0, 1, 1)

        commands.execute("timeline.hierarchy.group")

        assert len(tlui) == 1
        tilia_errors.assert_no_error()

    def test_delete_elements(self, tlui):
        tlui.create_hierarchy(0, 1, 1)

        tlui.select_element(tlui[0])

        commands.execute("timeline.component.delete")

        assert len(tlui) == 0

    def test_create_hierarchy_below(self, tlui):
        tlui.create_hierarchy(0, 1, 2)

        tlui.select_element(tlui[0])

        commands.execute("timeline.hierarchy.create_child")

        assert len(tlui) == 2


class TestCopyPaste:
    def test_paste(self, tlui):
        tlui.create_hierarchy(0, 1, 1, label="paste test")
        tlui.create_hierarchy(0, 1, 2)

        tlui.select_element(tlui[0])
        commands.execute("timeline.component.copy")
        tlui.deselect_element(tlui[0])

        tlui.select_element(tlui[1])
        commands.execute("timeline.component.paste")

        assert tlui[1].get_data("label") == "paste test"

    def test_paste_without_children_into_selected_elements(self, tlui):
        tlui.create_hierarchy(0, 0.5, 1, color="#000000")
        set_dummy_copy_attributes(tlui[0])
        tlui.select_element(tlui[0])
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()

        tlui.create_hierarchy(0.5, 1, 1, color="#000000")
        hrc1, hrc2 = tlui.timeline[0], tlui.timeline[1]  # order will change with paste

        tlui.select_element(tlui[1])
        commands.execute("timeline.component.paste")

        assert_are_copies(hrc1, hrc2)

    def test_paste_with_children_into_selected_elements_without_rescaling(
        self, tlui, tilia_state
    ):
        tlui.create_hierarchy(0, 0.5, 1)
        tlui.create_hierarchy(0.5, 1, 1)
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 2, 2)

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
        tlui.create_hierarchy(0, 0.5, 1)
        tlui.create_hierarchy(0.5, 1, 1)
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 1.5, 2)

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
        tlui.create_hierarchy(0, 0.5, 1)  # grandchild
        tlui.create_hierarchy(0.5, 1, 1)  # grandchild
        tlui.create_hierarchy(1, 1.5, 1)  # grandchild
        tlui.create_hierarchy(1.5, 2, 1)  # grandchild
        tlui.create_hierarchy(0, 1, 2)  # child
        tlui.create_hierarchy(1, 2, 2)  # child
        destination, _ = tlui.create_hierarchy(0, 2, 3)  # grandparent

        tlui.create_hierarchy(2, 2.25, 2)  # child
        tlui.create_hierarchy(2.25, 2.5, 2)  # child
        tlui.create_hierarchy(2.5, 2.75, 2)  # child
        tlui.create_hierarchy(2.75, 3, 2)  # child
        source, _ = tlui.create_hierarchy(2, 3, 3)  # parent

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
        tlui.create_hierarchy(0, 0.5, 1)
        tlui.create_hierarchy(0.5, 1, 1)
        tlui.create_hierarchy(0, 0.5, 2)
        tlui.create_hierarchy(0.5, 1, 2)
        tlui.create_hierarchy(0, 1, 3)
        hrc6, _ = tlui.create_hierarchy(1, 2, 3)

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
        tlui.create_hierarchy(0, 0.5, 1)
        tlui.create_hierarchy(0.5, 1, 1)
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 1.5, 3)

        tlui.select_element(tlui[2])
        commands.execute("timeline.component.copy")
        tlui.deselect_all_elements()

        tlui.select_element(tlui[1])
        component_state1 = tlui.timeline.components
        commands.execute("timeline.component.paste_complete")
        component_state2 = tlui.timeline.components

        assert component_state1 == component_state2


class TestCreateHierarchy:
    def test_create_single(self, tlui):
        tlui.create_hierarchy(0, 1, 1)

        assert len(tlui.elements) == 1

    def test_create_multiple(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(0.1, 1, 1)
        tlui.create_hierarchy(0.2, 1, 1)
        assert len(tlui.elements) == 3


class TestUndoRedo:
    def test_split(self, tlui, tluis):
        tlui.create_hierarchy(0, 1, 1)

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.split", time=0.5)

        commands.execute("edit.undo")
        assert len(tlui) == 1

        commands.execute("edit.redo")
        assert len(tlui) == 2

    def test_merge(self, tlui, tluis):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.merge")

        commands.execute("edit.undo")
        assert len(tlui) == 2

        commands.execute("edit.redo")
        assert len(tlui) == 1

    def test_increase_level(self, tlui, tluis):
        tlui.create_hierarchy(0, 1, 1)
        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.increase_level")

        commands.execute("edit.undo")
        assert tlui.elements[0].get_data("level") == 1

        commands.execute("edit.redo")
        assert tlui.elements[0].get_data("level") == 2

    def test_decrease_level(self, tlui, tluis):
        tlui.create_hierarchy(0, 1, 2)
        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.decrease_level")

        commands.execute("edit.undo")
        assert tlui.elements[0].get_data("level") == 2

        commands.execute("edit.redo")
        assert tlui.elements[0].get_data("level") == 1

    def test_group(self, tlui, tluis):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.group")

        commands.execute("edit.undo")
        assert len(tlui) == 2

        commands.execute("edit.redo")
        assert len(tlui) == 3

    def test_delete(self, tlui, tluis):
        tlui.create_hierarchy(0, 1, 1)

        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")
        assert len(tlui) == 1

        commands.execute("edit.redo")
        assert len(tlui) == 0

    def test_delete_parent_and_child(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(0, 1, 2)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")
        assert len(tlui) == 2

        commands.execute("edit.redo")
        assert len(tlui) == 0

    def test_create_unit_below(self, tlui, tluis):
        tlui.create_hierarchy(0, 1, 2)

        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.create_child")

        commands.execute("edit.undo")
        assert len(tlui) == 1

        commands.execute("edit.redo")
        assert len(tlui) == 2

    def test_paste(self, tlui, tluis):
        tlui.create_hierarchy(0, 1, 1, label="paste test")
        tlui.create_hierarchy(0, 1, 2)
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
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)
        tlui.create_hierarchy(0, 2, 2)
        tlui.create_hierarchy(2, 3, 2)

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
        tlui.create_hierarchy(0, 1, 2)

        tlui.select_element(tlui[0])

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.hierarchy.create_child")

        commands.execute("edit.undo")
        assert len(tlui) == 1

        commands.execute("edit.redo")
        assert len(tlui) == 2

    def test_at_lowest_level_user_declines_new_level(self, tlui):
        tlui.create_hierarchy(0, 1, 1)

        tlui.select_element(tlui[0])

        settings.set("hierarchy_timeline", "prompt_create_level_below", True)
        with patch_yes_or_no_dialog(False):
            commands.execute("timeline.hierarchy.create_child")

        assert len(tlui) == 1
        assert tlui[0].get_data("level") == 1

    class TestUserAcceptsNewLevel:
        def test_single_hierarchy(self, tlui):
            tlui.create_hierarchy(0, 1, 1)

            tlui.select_element(tlui[0])

            settings.set("hierarchy_timeline", "prompt_create_level_below", True)
            with patch_yes_or_no_dialog(True):
                commands.execute("timeline.hierarchy.create_child")

            assert len(tlui) == 2
            assert tlui[0].get_data("level") == 1
            assert tlui[1].get_data("level") == 2

        def test_with_parent(self, tlui):
            tlui.create_hierarchy(0, 1, 1)
            tlui.create_hierarchy(0, 1, 2)

            tlui.select_element(tlui[0])

            settings.set("hierarchy_timeline", "prompt_create_level_below", True)
            with patch_yes_or_no_dialog(True):
                commands.execute("timeline.hierarchy.create_child")

            assert len(tlui) == 3
            assert tlui[0].get_data("level") == 1
            assert tlui[1].get_data("level") == 2
            assert tlui[2].get_data("level") == 3

        def test_with_siblings(self, tlui):
            tlui.create_hierarchy(0, 1, 1)
            tlui.create_hierarchy(1, 2, 1)
            tlui.create_hierarchy(2, 3, 1)

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
            tlui.create_hierarchy(0, 1, 1)

            tlui.select_element(tlui[0])

            settings.set("hierarchy_timeline", "prompt_create_level_below", False)
            commands.execute("timeline.hierarchy.create_child")

            assert len(tlui) == 2


class TestClear:
    def test_initial_hierarchy_doesnt_trigger_confirmation(self, tlui, tilia_state):
        tlui.create_hierarchy(0, tilia_state.duration, 1)

        commands.execute("timeline.clear", tlui)

        assert tlui.is_empty

    def test_initial_hierarchy_with_edited_label_triggers_confirmation(
        self, tlui, tilia_state
    ):
        tlui.create_hierarchy(0, tilia_state.duration, 1, label="I WAS EDITED")

        with patch_yes_or_no_dialog(False):
            commands.execute("timeline.clear", tlui)

        # we must test explictly for len, to ensure the component was not deleted
        assert len(tlui) == 1

    def test_not_empty(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)
        tlui.create_hierarchy(2, 3, 1)

        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", tlui)

        assert tlui.is_empty
