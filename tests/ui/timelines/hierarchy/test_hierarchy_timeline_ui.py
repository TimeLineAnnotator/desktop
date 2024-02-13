from unittest.mock import patch
import pytest
from PyQt6.QtGui import QColor

from tests.mock import PatchGet
from tilia.requests import Post, Get, post, get
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.hierarchy import HierarchyUI


def set_dummy_copy_attributes(hierarchy: Hierarchy) -> None:
    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.by_component_value:
        if attr == "color":
            hierarchy.set_data(attr, "#FFFFFF")
        else:
            hierarchy.set_data(attr, f"test {attr} - {id(hierarchy)}")


def assert_are_copies(hierarchy1: Hierarchy, hierarchy2: Hierarchy):
    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.by_component_value:
        assert getattr(hierarchy1, attr) == getattr(hierarchy2, attr)


def assert_is_copy_data_of(copy_data: dict, hierarchy_ui: HierarchyUI):
    for attr, value in copy_data.items():
        assert hierarchy_ui.get_data(attr) == value

    if children := hierarchy_ui.get_data("children"):
        for index, child in enumerate(children):
            assert_is_copy_data_of(child, copy_data["children"][index])


class TestActions:
    def test_increase_level(self, hierarchy_tlui, actions):
        hrc, ui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(ui)
        actions.trigger(TiliaAction.HIERARCHY_INCREASE_LEVEL)

        assert hrc.level == 2

    def test_decrease_level(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hierarchy_tlui.select_element(ui1)
        actions.trigger(TiliaAction.HIERARCHY_DECREASE_LEVEL)

        assert hrc1.level == 1

    def test_set_color(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(ui1)

        with patch("tilia.ui.dialogs.basic.ask_for_color", lambda _: QColor("#000")):
            actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_SET)

        assert hrc1.color == "#000000"

    def test_reset_color(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(ui1)

        with patch("tilia.ui.dialogs.basic.ask_for_color", lambda _: QColor("#000")):
            actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_SET)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_RESET)

        assert hrc1.color is None

    def test_add_pre_start(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0.1, 1, 1)
        hierarchy_tlui.select_element(ui1)

        with patch("tilia.ui.dialogs.basic.ask_for_float", lambda *_: (0.1, True)):
            actions.trigger(TiliaAction.HIERARCHY_ADD_PRE_START)

        assert hrc1.pre_start != hrc1.start
        assert ui1.pre_start_handle

    def test_add_post_end(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(ui1)

        with patch("tilia.ui.dialogs.basic.ask_for_float", lambda *_: (0.1, True)):
            actions.trigger(TiliaAction.HIERARCHY_ADD_POST_END)

        assert hrc1.post_end != hrc1.end
        assert ui1.post_end_handle

    def test_split(self, hierarchy_tlui, actions):
        hierarchy_tlui.create_hierarchy(0, 1, 1)
        assert len(hierarchy_tlui) == 1
        with PatchGet(
            "tilia.ui.timelines.hierarchy.request_handlers", Get.MEDIA_CURRENT_TIME, 0.5
        ):
            actions.trigger(TiliaAction.HIERARCHY_SPLIT)

        assert len(hierarchy_tlui) == 2

    def test_merge(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(1, 2, 1)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.select_element(ui2)

        actions.trigger(TiliaAction.HIERARCHY_MERGE)

        assert len(hierarchy_tlui) == 1

    def test_group(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(1, 2, 1)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.select_element(ui2)

        actions.trigger(TiliaAction.HIERARCHY_GROUP)

        assert len(hierarchy_tlui) == 3

    def test_delete_elements(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)

        hierarchy_tlui.select_element(ui1)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(hierarchy_tlui) == 0

    def test_create_hierarchy_below(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        hierarchy_tlui.select_element(ui1)

        actions.trigger(TiliaAction.HIERARCHY_CREATE_CHILD)

        assert len(hierarchy_tlui) == 2


class TestCopyPaste:
    def test_paste(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1, label="paste test")
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        hierarchy_tlui.select_element(ui1)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        hierarchy_tlui.deselect_element(ui1)

        hierarchy_tlui.select_element(ui2)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert hrc2.get_data("label") == "paste test"

    def test_paste_without_children_into_selected_elements(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1, color="#000000")
        set_dummy_copy_attributes(hrc1)
        hierarchy_tlui.select_element(ui1)
        post(Post.TIMELINE_ELEMENT_COPY)
        hierarchy_tlui.deselect_all_elements()

        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1, color="#000000")
        hierarchy_tlui.select_element(ui2)
        post(Post.TIMELINE_ELEMENT_PASTE)

        assert_are_copies(hrc1, hrc2)

    def test_paste_with_children_into_selected_elements_without_rescaling(
        self, hierarchy_tlui, actions, tilia_state
    ):
        hrc1, _ = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, _ = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3, ui3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hrc4, ui4 = hierarchy_tlui.create_hierarchy(1, 2, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        hierarchy_tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        hierarchy_tlui.select_element(ui3)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        hierarchy_tlui.deselect_all_elements()

        hierarchy_tlui.select_element(ui4)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)

        assert len(hierarchy_tlui.elements) == 6
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

    def test_paste_with_children_into_selected_elements_with_rescaling(
        self, hierarchy_tlui, actions
    ):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3, ui3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hrc4, ui4 = hierarchy_tlui.create_hierarchy(1, 1.5, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        hierarchy_tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        hierarchy_tlui.select_element(ui3)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        hierarchy_tlui.deselect_all_elements()

        hierarchy_tlui.select_element(ui4)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)

        copied_children_1, copied_children_2 = sorted(hrc4.children)

        assert copied_children_1.parent == hrc4
        assert copied_children_1.start == 1.0
        assert copied_children_1.end == 1.25

        assert copied_children_2.parent == hrc4
        assert copied_children_2.start == 1.25
        assert copied_children_2.end == 1.5

    def test_paste_with_children_that_have_children(self, hierarchy_tlui, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3, ui3 = hierarchy_tlui.create_hierarchy(0, 0.5, 2)
        hrc4, ui4 = hierarchy_tlui.create_hierarchy(0.5, 1, 2)
        hrc5, ui5 = hierarchy_tlui.create_hierarchy(0, 1, 3)
        hrc6, ui6 = hierarchy_tlui.create_hierarchy(1, 2, 3)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        hierarchy_tlui.relate_hierarchies(parent=hrc3, children=[hrc1])
        hierarchy_tlui.relate_hierarchies(parent=hrc4, children=[hrc2])
        hierarchy_tlui.relate_hierarchies(parent=hrc5, children=[hrc3, hrc4])

        hierarchy_tlui.select_element(ui5)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        hierarchy_tlui.deselect_all_elements()

        hierarchy_tlui.select_element(ui6)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)

        copied_children_1, copied_children_2 = sorted(hrc6.children)

        assert len(copied_children_1.children) == 1
        assert copied_children_1.children[0].start == 1
        assert copied_children_1.children[0].end == 1.5

        assert len(copied_children_2.children) == 1
        assert copied_children_2.children[0].start == 1.5
        assert copied_children_2.children[0].end == 2.0

    def test_paste_with_children_into_different_level_fails(
        self, hierarchy_tlui, actions
    ):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3, ui3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        _, _ = hierarchy_tlui.create_hierarchy(1, 1.5, 3)

        hierarchy_tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        hierarchy_tlui.select_element(ui3)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        hierarchy_tlui.deselect_all_elements()

        hierarchy_tlui.select_element(ui2)
        component_state1 = hierarchy_tlui.timeline.components
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)
        component_state2 = hierarchy_tlui.timeline.components

        assert component_state1 == component_state2


class TestCreateHierarchy:
    def test_create_single(self, hierarchy_tlui):
        hierarchy_tlui.create_hierarchy(0, 1, 1)

        assert len(hierarchy_tlui.elements) == 1

    def test_create_multiple(self, hierarchy_tlui):
        hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.create_hierarchy(0.1, 1, 1)
        hierarchy_tlui.create_hierarchy(0.2, 1, 1)
        assert len(hierarchy_tlui.elements) == 3


class TestUndoRedo:
    def test_split(self, hierarchy_tlui, tluis, actions):
        hierarchy_tlui.create_hierarchy(0, 1, 1)

        post(Post.APP_RECORD_STATE, "test state")

        with PatchGet(
            "tilia.ui.timelines.hierarchy.request_handlers", Get.MEDIA_CURRENT_TIME, 0.5
        ):
            actions.trigger(TiliaAction.HIERARCHY_SPLIT)

        post(Post.EDIT_UNDO)
        assert len(hierarchy_tlui) == 1

        post(Post.EDIT_REDO)
        assert len(hierarchy_tlui) == 2

    def test_merge(self, hierarchy_tlui, tluis, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(1, 2, 1)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.select_element(ui2)

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_MERGE)

        post(Post.EDIT_UNDO)
        assert len(hierarchy_tlui) == 2

        post(Post.EDIT_REDO)
        assert len(hierarchy_tlui) == 1

    def test_increase_level(self, hierarchy_tlui, tluis, actions):
        hrc, ui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(ui)

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_INCREASE_LEVEL)

        post(Post.EDIT_UNDO)
        assert hierarchy_tlui.elements[0].get_data("level") == 1

        post(Post.EDIT_REDO)
        assert hierarchy_tlui.elements[0].get_data("level") == 2

    def test_decrease_level(self, hierarchy_tlui, tluis, actions):
        hrc, ui = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hierarchy_tlui.select_element(ui)

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_DECREASE_LEVEL)

        post(Post.EDIT_UNDO)
        assert hierarchy_tlui.elements[0].get_data("level") == 2

        post(Post.EDIT_REDO)
        assert hierarchy_tlui.elements[0].get_data("level") == 1

    def test_group(self, hierarchy_tlui, tluis, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(1, 2, 1)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.select_element(ui2)

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_GROUP)

        post(Post.EDIT_UNDO)
        assert len(hierarchy_tlui) == 2

        post(Post.EDIT_REDO)
        assert len(hierarchy_tlui) == 3

    def test_delete(self, hierarchy_tlui, tluis, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)

        hierarchy_tlui.select_element(ui1)

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        post(Post.EDIT_UNDO)
        assert len(hierarchy_tlui) == 1

        post(Post.EDIT_REDO)
        assert len(hierarchy_tlui) == 0

    def test_create_unit_below(self, hierarchy_tlui, tluis, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        hierarchy_tlui.select_element(ui1)

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_CREATE_CHILD)

        post(Post.EDIT_UNDO)
        assert len(hierarchy_tlui) == 1

        post(Post.EDIT_REDO)
        assert len(hierarchy_tlui) == 2

    def test_paste(self, hierarchy_tlui, tluis, actions):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1, label="paste test")
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        post(Post.APP_RECORD_STATE, "test state")

        hierarchy_tlui.select_element(ui1)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        hierarchy_tlui.deselect_element(ui1)

        hierarchy_tlui.select_element(ui2)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert hierarchy_tlui[1].get_data("label") == "paste test"

        actions.trigger(TiliaAction.EDIT_UNDO)
        assert hierarchy_tlui[1].get_data("label") == ""

        actions.trigger(TiliaAction.EDIT_REDO)
        assert hierarchy_tlui[1].get_data("label") == "paste test"

    def test_paste_with_children(self, hierarchy_tlui, tluis, actions):
        parent, parent_ui = hierarchy_tlui.create_hierarchy(0, 2, 2)
        child1, _ = hierarchy_tlui.create_hierarchy(0, 1, 1)
        child2, _ = hierarchy_tlui.create_hierarchy(1, 2, 1)
        receptor, receptor_ui = hierarchy_tlui.create_hierarchy(2, 3, 2)

        hierarchy_tlui.relate_hierarchies(parent, [child1, child2])

        post(Post.APP_RECORD_STATE, "test state")

        hierarchy_tlui.select_element(parent_ui)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        hierarchy_tlui.deselect_element(parent_ui)

        hierarchy_tlui.select_element(receptor_ui)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)

        post(Post.EDIT_UNDO)
        assert len(hierarchy_tlui) == 4

        post(Post.EDIT_REDO)
        assert len(hierarchy_tlui) == 6
