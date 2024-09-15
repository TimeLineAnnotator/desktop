import pytest
from PyQt6.QtGui import QColor

from tests.mock import PatchGet, Serve
from tilia.requests import Post, Get, post
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.hierarchy import HierarchyUI


@pytest.fixture
def tlui(hierarchy_tlui):
    return hierarchy_tlui


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
    def test_increase_level(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)
        tlui.create_hierarchy(3, 4, 1)

        tlui.select_element(tlui[0])
        actions.trigger(TiliaAction.HIERARCHY_INCREASE_LEVEL)

        assert tlui[2].get_data('level') == 2
        assert tlui[2].get_data('start') == 0
        assert tlui[2].get_data('end') == 1
        assert tlui[0].get_data('level') == 1
        assert tlui[1].get_data('level') == 1

    def test_increase_level_multiple_hierarchies(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)
        tlui.create_hierarchy(3, 4, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.select_element(tlui[2])
        actions.trigger(TiliaAction.HIERARCHY_INCREASE_LEVEL)

        assert tlui[0].get_data('level') == 2
        assert tlui[1].get_data('level') == 2
        assert tlui[2].get_data('level') == 2

    def test_decrease_level(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 2, 2)
        tlui.create_hierarchy(3, 4, 2)

        tlui.select_element(tlui[0])
        actions.trigger(TiliaAction.HIERARCHY_DECREASE_LEVEL)

        assert tlui[0].get_data('level') == 1
        assert tlui[1].get_data('level') == 2
        assert tlui[2].get_data('level') == 2

    def test_decrease_level_multiple_hierarchies(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 2, 2)
        tlui.create_hierarchy(3, 4, 2)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.select_element(tlui[2])
        actions.trigger(TiliaAction.HIERARCHY_DECREASE_LEVEL)

        assert tlui[0].get_data('level') == 1
        assert tlui[1].get_data('level') == 1
        assert tlui[2].get_data('level') == 1

    def test_set_color(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_COLOR, (True, QColor("#000"))):
            actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_SET)

        assert tlui[0].get_data('color') == "#000000"

    def test_reset_color(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_COLOR, (True, QColor("#000"))):
            actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_SET)

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COLOR_RESET)

        assert tlui[0].get_data('color') is None

    def test_add_pre_start(self, tlui, actions):
        tlui.create_hierarchy(0.1, 1, 1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_FLOAT, (True, 0.1)):
            actions.trigger(TiliaAction.HIERARCHY_ADD_PRE_START)

        assert tlui[0].get_data('pre_start') != tlui[0].get_data('start')
        assert tlui[0].pre_start_handle

    def test_add_post_end(self, tlui, actions, tilia_state):
        tlui.create_hierarchy(0, 1, 1)
        tlui.select_element(tlui[0])

        with Serve(Get.FROM_USER_FLOAT, (True, 0.1)):
            actions.trigger(TiliaAction.HIERARCHY_ADD_POST_END)

        assert tlui[0].get_data('post_end') != tlui[0].get_data('end')
        assert tlui[0].post_end_handle

    def test_split(self, tlui, actions, tilia_state):
        tlui.create_hierarchy(0, 1, 1)
        assert len(tlui) == 1
        tilia_state.current_time = 0.5
        actions.trigger(TiliaAction.HIERARCHY_SPLIT)

        assert len(tlui) == 2

    def test_merge(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        actions.trigger(TiliaAction.HIERARCHY_MERGE)

        assert len(tlui) == 1

    def test_group(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        actions.trigger(TiliaAction.HIERARCHY_GROUP)

        assert len(tlui) == 3

    def test_delete_elements(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 1)

        tlui.select_element(tlui[0])

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(tlui) == 0

    def test_create_hierarchy_below(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 2)

        tlui.select_element(tlui[0])

        actions.trigger(TiliaAction.HIERARCHY_CREATE_CHILD)

        assert len(tlui) == 2


class TestCopyPaste:
    def test_paste(self, tlui, actions):
        tlui.create_hierarchy(0, 1, 1, label="paste test")
        tlui.create_hierarchy(0, 1, 2)

        tlui.select_element(tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        tlui.deselect_element(tlui[0])

        tlui.select_element(tlui[1])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert tlui[1].get_data("label") == "paste test"

    def test_paste_without_children_into_selected_elements(self, tlui):
        tlui.create_hierarchy(0, 0.5, 1, color="#000000")
        set_dummy_copy_attributes(tlui[0])
        tlui.select_element(tlui[0])
        post(Post.TIMELINE_ELEMENT_COPY)
        tlui.deselect_all_elements()

        tlui.create_hierarchy(0.5, 1, 1, color="#000000")
        hrc1, hrc2 = tlui.timeline[0], tlui.timeline[1]  # order will change with paste

        tlui.select_element(tlui[1])
        post(Post.TIMELINE_ELEMENT_PASTE)

        assert_are_copies(hrc1, hrc2)

    def test_paste_with_children_into_selected_elements_without_rescaling(
        self, tlui, actions, tilia_state
    ):
        tlui.create_hierarchy(0, 0.5, 1)
        tlui.create_hierarchy(0.5, 1, 1)
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 2, 2)

        # order will change with paste
        hrc1 = tlui.timeline[0]
        hrc2 = tlui.timeline[1]
        hrc3 = tlui.timeline[2]
        hrc4 = tlui.timeline[3]

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        tlui.select_element(tlui[2])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        tlui.deselect_all_elements()

        tlui.select_element(tlui[3])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)

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

    def test_paste_with_children_into_selected_elements_with_rescaling(
        self, tlui, actions
    ):
        tlui.create_hierarchy(0, 0.5, 1)
        tlui.create_hierarchy(0.5, 1, 1)
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 1.5, 2)

        # order will change with paste
        hrc1 = tlui.timeline[0]
        hrc2 = tlui.timeline[1]
        hrc3 = tlui.timeline[2]
        hrc4 = tlui.timeline[3]

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        tlui.select_element(tlui[2])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        tlui.deselect_all_elements()

        tlui.select_element(tlui[3])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)

        copied_children_1, copied_children_2 = sorted(hrc4.children)

        assert copied_children_1.parent == hrc4
        assert copied_children_1.start == 1.0
        assert copied_children_1.end == 1.25

        assert copied_children_2.parent == hrc4
        assert copied_children_2.start == 1.25
        assert copied_children_2.end == 1.5

    def test_paste_with_children_that_have_children(self, tlui, actions):
        tlui.create_hierarchy(0, 0.5, 1)
        tlui.create_hierarchy(0.5, 1, 1)
        tlui.create_hierarchy(0, 0.5, 2)
        tlui.create_hierarchy(0.5, 1, 2)
        tlui.create_hierarchy(0, 1, 3)
        tlui.create_hierarchy(1, 2, 3)

        # order will change with paste
        hrc1 = tlui.timeline[0]
        hrc2 = tlui.timeline[1]
        hrc3 = tlui.timeline[2]
        hrc4 = tlui.timeline[3]
        hrc5 = tlui.timeline[4]
        hrc6 = tlui.timeline[5]

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        tlui.relate_hierarchies(parent=hrc3, children=[hrc1])
        tlui.relate_hierarchies(parent=hrc4, children=[hrc2])
        tlui.relate_hierarchies(parent=hrc5, children=[hrc3, hrc4])

        tlui.select_element(tlui[4])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        tlui.deselect_all_elements()

        tlui.select_element(tlui[5])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)

        copied_children_1, copied_children_2 = sorted(hrc6.children)

        assert len(copied_children_1.children) == 1
        assert copied_children_1.children[0].start == 1
        assert copied_children_1.children[0].end == 1.5

        assert len(copied_children_2.children) == 1
        assert copied_children_2.children[0].start == 1.5
        assert copied_children_2.children[0].end == 2.0

    def test_paste_with_children_into_different_level_fails(
        self, tlui, actions
    ):
        tlui.create_hierarchy(0, 0.5, 1)
        tlui.create_hierarchy(0.5, 1, 1)
        tlui.create_hierarchy(0, 1, 2)
        tlui.create_hierarchy(1, 1.5, 3)

        # order will change with paste
        hrc1 = tlui.timeline[0]
        hrc2 = tlui.timeline[1]
        hrc3 = tlui.timeline[2]

        tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        tlui.select_element(tlui[2])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        tlui.deselect_all_elements()

        tlui.select_element(tlui[1])
        component_state1 = tlui.timeline.components
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)
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
    def test_split(self, tlui, tluis, actions):
        tlui.create_hierarchy(0, 1, 1)

        post(Post.APP_RECORD_STATE, "test state")

        with PatchGet(
            "tilia.ui.timelines.hierarchy.request_handlers", Get.SELECTED_TIME, 0.5
        ):
            actions.trigger(TiliaAction.HIERARCHY_SPLIT)

        post(Post.EDIT_UNDO)
        assert len(tlui) == 1

        post(Post.EDIT_REDO)
        assert len(tlui) == 2

    def test_merge(self, tlui, tluis, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_MERGE)

        post(Post.EDIT_UNDO)
        assert len(tlui) == 2

        post(Post.EDIT_REDO)
        assert len(tlui) == 1

    def test_increase_level(self, tlui, tluis, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.select_element(tlui[0])

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_INCREASE_LEVEL)

        post(Post.EDIT_UNDO)
        assert tlui.elements[0].get_data("level") == 1

        post(Post.EDIT_REDO)
        assert tlui.elements[0].get_data("level") == 2

    def test_decrease_level(self, tlui, tluis, actions):
        tlui.create_hierarchy(0, 1, 2)
        tlui.select_element(tlui[0])

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_DECREASE_LEVEL)

        post(Post.EDIT_UNDO)
        assert tlui.elements[0].get_data("level") == 2

        post(Post.EDIT_REDO)
        assert tlui.elements[0].get_data("level") == 1

    def test_group(self, tlui, tluis, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_GROUP)

        post(Post.EDIT_UNDO)
        assert len(tlui) == 2

        post(Post.EDIT_REDO)
        assert len(tlui) == 3

    def test_delete(self, tlui, tluis, actions):
        tlui.create_hierarchy(0, 1, 1)

        tlui.select_element(tlui[0])

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        post(Post.EDIT_UNDO)
        assert len(tlui) == 1

        post(Post.EDIT_REDO)
        assert len(tlui) == 0

    def test_create_unit_below(self, tlui, tluis, actions):
        tlui.create_hierarchy(0, 1, 2)

        tlui.select_element(tlui[0])

        post(Post.APP_RECORD_STATE, "test state")

        actions.trigger(TiliaAction.HIERARCHY_CREATE_CHILD)

        post(Post.EDIT_UNDO)
        assert len(tlui) == 1

        post(Post.EDIT_REDO)
        assert len(tlui) == 2

    def test_paste(self, tlui, tluis, actions):
        tlui.create_hierarchy(0, 1, 1, label="paste test")
        tlui.create_hierarchy(0, 1, 2)
        post(Post.APP_RECORD_STATE, "test state")

        tlui.select_element(tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        tlui.deselect_element(tlui[0])

        tlui.select_element(tlui[1])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert tlui[1].get_data("label") == "paste test"

        actions.trigger(TiliaAction.EDIT_UNDO)
        assert tlui[1].get_data("label") == ""

        actions.trigger(TiliaAction.EDIT_REDO)
        assert tlui[1].get_data("label") == "paste test"

    @pytest.mark.skip('Paste complete is not being recorded. This has been fixed in another branch')
    def test_paste_with_children(self, tlui, tluis, actions):
        tlui.create_hierarchy(0, 1, 1)
        tlui.create_hierarchy(1, 2, 1)
        tlui.create_hierarchy(0, 2, 2)
        tlui.create_hierarchy(2, 3, 2)

        tlui.relate_hierarchies(tlui.timeline[2], [tlui.timeline[0], tlui.timeline[1]])
        tlui.select_element(tlui[2])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        tlui.deselect_element(tlui[2])

        tlui.select_element(tlui[3])

        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE)

        post(Post.EDIT_UNDO)
        assert len(tlui) == 4

        post(Post.EDIT_REDO)
        assert len(tlui) == 6
