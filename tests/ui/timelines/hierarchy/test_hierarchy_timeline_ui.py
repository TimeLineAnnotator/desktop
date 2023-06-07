from unittest.mock import patch
import pytest
import tkinter as tk

from tests.mock import PatchGet
from tilia.requests import Post, Get, post
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.timelines.copy_paste import PasteError
from tilia.ui.timelines.hierarchy import HierarchyUI


def is_in_front(id1: int, id2: int, canvas: tk.Canvas) -> bool:
    stacking_order = canvas.find_all()
    return stacking_order.index(id1) > stacking_order.index(id2)


def set_dummy_copy_attributes(hierarchy: Hierarchy) -> None:
    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.by_component_value:
        if attr == "color":
            setattr(hierarchy, attr, "#FFFFFF")
            continue
        setattr(hierarchy, attr, f"test {attr} - {id(hierarchy)}")


def assert_are_copies(hierarchy1: Hierarchy, hierarchy2: Hierarchy):
    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.by_component_value:
        assert getattr(hierarchy1, attr) == getattr(hierarchy2, attr)


def assert_is_copy_data_of(copy_data: dict, hierarchy_ui: HierarchyUI):
    def _make_assertions(copy_data_: dict, hierarchy_ui_: HierarchyUI):
        for attr, value in copy_data_["by_element_value"].items():
            assert value == getattr(hierarchy_ui_, attr)

        for attr, value in copy_data_["support_by_element_value"].items():
            assert value == getattr(hierarchy_ui_, attr)

        for attr, value in copy_data_["by_component_value"].items():
            assert value == getattr(hierarchy_ui_.tl_component, attr)

        for attr, value in copy_data_["support_by_component_value"].items():
            assert value == getattr(hierarchy_ui_.tl_component, attr)

    _make_assertions(copy_data, hierarchy_ui)

    if children := hierarchy_ui.tl_component.children:
        for index, child in enumerate(children):
            _make_assertions(child, copy_data["children"][index])


class TestHierarchyTimelineUI:
    def test_create_hierarchy(self, hierarchy_tlui):
        hierarchy_tlui.create_hierarchy(0, 1, 1)

        assert len(hierarchy_tlui.elements) == 1

    def test_create_multiple_hierarchies(self, hierarchy_tlui):
        hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.create_hierarchy(0.1, 1, 1)
        hierarchy_tlui.create_hierarchy(0.2, 1, 1)
        assert len(hierarchy_tlui.elements) == 3

    def test_right_click_increase_level(self, hierarchy_tlui):
        hrc, ui = hierarchy_tlui.create_hierarchy(0, 1, 1)

        hierarchy_tlui.right_clicked_element = ui

        hierarchy_tlui.right_click_menu_increase_level()

        assert hrc.level == 2

    def test_right_click_decrease_level(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        hierarchy_tlui.right_clicked_element = ui1

        hierarchy_tlui.right_click_menu_decrease_level()

        assert hrc1.level == 1

    def test_right_click_change_color(self, hierarchy_tlui):
        with PatchGet(
            "tilia.ui.timelines.hierarchy.timeline", Get.COLOR_FROM_USER, "#000000"
        ):
            hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)

            hierarchy_tlui.right_clicked_element = ui1

            hierarchy_tlui.right_click_menu_change_color()

            assert hrc1.color == "#000000"

    def test_right_click_reset_color(self, hierarchy_tlui):
        with PatchGet(
            "tilia.ui.timelines.hierarchy.timeline", Get.COLOR_FROM_USER, "#000000"
        ):
            hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)

            hierarchy_tlui.right_clicked_element = ui1

            hierarchy_tlui.right_click_menu_change_color()
            hierarchy_tlui.right_click_menu_reset_color()

            assert hrc1.color == ui1.get_default_color(hrc1.level)

    def test_right_click_add_pre_start(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0.1, 1, 1)

        hierarchy_tlui.right_clicked_element = ui1
        with PatchGet(
            "tilia.ui.timelines.hierarchy.timeline", Get.FLOAT_FROM_USER, 0.1
        ):
            hierarchy_tlui.right_click_menu_add_pre_start()

        assert hrc1.pre_start != hrc1.start

    def test_right_click_add_post_end(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)

        hierarchy_tlui.right_clicked_element = ui1

        with PatchGet(
            "tilia.ui.timelines.hierarchy.timeline", Get.FLOAT_FROM_USER, 0.1
        ):
            hierarchy_tlui.right_click_menu_add_post_end()

        assert hrc1.post_end != hrc1.end

    def test_rearrange_elements_two_levels(self, hierarchy_tlui):
        unit2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        unit3, ui3 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        unit1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        unit1.children = [unit2, unit3]
        unit2.parent = unit1
        unit3.parent = unit1

        assert is_in_front(ui1.body_id, ui2.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui1.body_id, ui3.body_id, hierarchy_tlui.canvas)

        hierarchy_tlui.rearrange_canvas_drawings()

        assert is_in_front(ui2.body_id, ui1.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui3.body_id, ui1.body_id, hierarchy_tlui.canvas)

    def test_rearrange_elements_three_levels(self, hierarchy_tlui):
        unit1, ui1 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        unit2, ui2 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        unit3, ui3 = hierarchy_tlui.create_hierarchy(1.5, 2, 1)
        unit4, ui4 = hierarchy_tlui.create_hierarchy(1, 1.5, 1)
        unit5, ui5 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        unit6, ui6 = hierarchy_tlui.create_hierarchy(1, 2, 2)
        unit7, ui7 = hierarchy_tlui.create_hierarchy(0, 2, 3)

        # set parentage
        unit5.children = [unit1, unit2]
        unit1.parent = unit5
        unit2.parent = unit5

        unit6.children = [unit3, unit4]
        unit3.parent = unit6
        unit4.parent = unit6

        unit7.children = [unit5, unit6]
        unit5.parent = unit7
        unit6.parent = unit7

        hierarchy_tlui.rearrange_canvas_drawings()

        assert is_in_front(ui1.body_id, ui5.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui2.body_id, ui5.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui3.body_id, ui6.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui4.body_id, ui6.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui5.body_id, ui7.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui6.body_id, ui7.body_id, hierarchy_tlui.canvas)

    def test_rearrange_elements_four_levels(self, hierarchy_tlui):
        unit1, ui1 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        unit2, ui2 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        unit3, ui3 = hierarchy_tlui.create_hierarchy(1.5, 2, 1)
        unit4, ui4 = hierarchy_tlui.create_hierarchy(1, 1.5, 1)
        unit5, ui5 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        unit6, ui6 = hierarchy_tlui.create_hierarchy(1, 2, 2)
        unit7, ui7 = hierarchy_tlui.create_hierarchy(0, 2, 3)
        unit8, ui8 = hierarchy_tlui.create_hierarchy(2.5, 3, 1)
        unit9, ui9 = hierarchy_tlui.create_hierarchy(2, 4.5, 1)
        unit10, ui10 = hierarchy_tlui.create_hierarchy(3.5, 4, 1)
        unit11, ui11 = hierarchy_tlui.create_hierarchy(3, 3.5, 1)
        unit12, ui12 = hierarchy_tlui.create_hierarchy(2, 3, 2)
        unit13, ui13 = hierarchy_tlui.create_hierarchy(3, 4, 2)
        unit14, ui14 = hierarchy_tlui.create_hierarchy(2, 4, 3)
        unit15, ui15 = hierarchy_tlui.create_hierarchy(0, 4, 4)

        # set parentage
        unit5.children = [unit1, unit2]
        unit1.parent = unit5
        unit2.parent = unit5

        unit6.children = [unit3, unit4]
        unit3.parent = unit6
        unit4.parent = unit6

        unit7.children = [unit5, unit6]
        unit5.parent = unit7
        unit6.parent = unit7

        # set parentage
        unit12.children = [unit8, unit9]
        unit8.parent = unit12
        unit9.parent = unit12

        unit13.children = [unit10, unit11]
        unit10.parent = unit13
        unit11.parent = unit13

        unit14.children = [unit12, unit13]
        unit12.parent = unit14
        unit13.parent = unit14

        unit15.children = [unit14, unit7]
        unit7.parent = unit15
        unit14.parent = unit15

        hierarchy_tlui.rearrange_canvas_drawings()

        assert is_in_front(ui1.body_id, ui5.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui2.body_id, ui5.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui3.body_id, ui6.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui4.body_id, ui6.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui5.body_id, ui7.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui6.body_id, ui7.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui7.body_id, ui15.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui8.body_id, ui12.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui9.body_id, ui12.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui10.body_id, ui13.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui11.body_id, ui13.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui12.body_id, ui14.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui13.body_id, ui14.body_id, hierarchy_tlui.canvas)
        assert is_in_front(ui14.body_id, ui15.body_id, hierarchy_tlui.canvas)

    # -- TEST COPY.PASTE -- #

    def test_paste_without_children_into_selected_elements(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1, color="#000000")

        set_dummy_copy_attributes(hrc1)

        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1, color="#000000")

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([ui1])
        hierarchy_tlui.select_element(ui2)
        hierarchy_tlui.paste_single_into_selected_elements(copy_data)

        assert_are_copies(hrc1, hrc2)

    def test_get_copy_data_from_hierarchy_uis(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([ui1, ui2])

        assert_is_copy_data_of(copy_data[0], ui1)
        assert_is_copy_data_of(copy_data[1], ui2)

    def test_get_copy_data_from_hierarchy_ui_with_children(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3, ui3 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)
        set_dummy_copy_attributes(hrc3)

        hrc3.children = [hrc1, hrc2]
        hrc1.parent = hrc3
        hrc2.parent = hrc3

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([ui2])

        assert_is_copy_data_of(copy_data[0], ui2)

    def test_paste_with_children_into_selected_elements_without_rescaling(
        self, hierarchy_tlui
    ):
        hrc1, _ = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, _ = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3, ui3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hrc4, ui4 = hierarchy_tlui.create_hierarchy(1, 2, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        hierarchy_tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([ui3])

        hierarchy_tlui.select_element(ui4)

        hierarchy_tlui.paste_with_children_into_selected_elements(copy_data)

        assert len(hierarchy_tlui.elements) == 6
        assert len(hrc4.children) == 2

        copied_children_1, copied_children_2 = sorted(
            hrc4.children, key=lambda h: h.start
        )

        assert copied_children_1.parent == hrc4
        assert copied_children_1.start == 1.0
        assert copied_children_1.end == 1.5

        assert copied_children_2.parent == hrc4
        assert copied_children_2.start == 1.5
        assert copied_children_2.end == 2.0

        assert_are_copies(copied_children_1, hrc1)
        assert_are_copies(copied_children_2, hrc2)

    def test_paste_with_children_into_selected_elements_with_rescaling(
        self, hierarchy_tlui
    ):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3, ui3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hrc4, ui4 = hierarchy_tlui.create_hierarchy(1, 1.5, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        hierarchy_tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([ui3])

        hierarchy_tlui.select_element(ui4)

        hierarchy_tlui.paste_with_children_into_selected_elements(copy_data)

        copied_children_1, copied_children_2 = sorted(
            hrc4.children, key=lambda h: h.start
        )

        assert copied_children_1.parent == hrc4
        assert copied_children_1.start == 1.0
        assert copied_children_1.end == 1.25

        assert copied_children_2.parent == hrc4
        assert copied_children_2.start == 1.25
        assert copied_children_2.end == 1.5

    def test_paste_with_children_that_have_children(self, hierarchy_tlui):
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

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([ui5])

        hierarchy_tlui.select_element(ui6)

        hierarchy_tlui.paste_with_children_into_selected_elements(copy_data)

        copied_children_1, copied_children_2 = sorted(
            hrc6.children, key=lambda h: h.start
        )

        assert len(copied_children_1.children) == 1
        assert copied_children_1.children[0].start == 1
        assert copied_children_1.children[0].end == 1.5

        assert len(copied_children_2.children) == 1
        assert copied_children_2.children[0].start == 1.5
        assert copied_children_2.children[0].end == 2.0

    def test_paste_with_children_into_different_level_raises_error(
        self, hierarchy_tlui
    ):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3, ui3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        _, _ = hierarchy_tlui.create_hierarchy(1, 1.5, 3)

        hierarchy_tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([ui3])

        hierarchy_tlui.select_element(ui2)

        with pytest.raises(PasteError):
            with patch("tkinter.messagebox.showerror", lambda *_: None):
                hierarchy_tlui.paste_with_children_into_selected_elements(copy_data)

    def test_paste_with_children_paste_two_elements_raises_error(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3, ui3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hrc4, ui4 = hierarchy_tlui.create_hierarchy(1, 1.5, 2)

        hierarchy_tlui.relate_hierarchies(parent=hrc3, children=[hrc1, hrc2])

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([ui3, ui4])

        hierarchy_tlui.select_element(ui4)

        with pytest.raises(PasteError):
            hierarchy_tlui.paste_with_children_into_selected_elements(copy_data)

    def test_split(self, hierarchy_tlui):
        hierarchy_tlui.create_hierarchy(0, 1, 1)
        with PatchGet(
            "tilia.ui.timelines.hierarchy.timeline", Get.CURRENT_PLAYBACK_TIME, 0.5
        ):
            hierarchy_tlui.split()

        assert len(hierarchy_tlui) == 2

    def test_merge(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(1, 2, 1)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.select_element(ui2)

        hierarchy_tlui.merge()

        assert len(hierarchy_tlui) == 1

    def test_on_increase_level_button(self, hierarchy_tlui):
        hrc, ui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(ui)

        hierarchy_tlui.change_level(1)

        assert hierarchy_tlui.elements[0].level == 2

    def test_on_decrease_level_button(self, hierarchy_tlui):
        hrc, ui = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hierarchy_tlui.select_element(ui)

        hierarchy_tlui.change_level(-1)

        assert hierarchy_tlui.elements[0].level == 1

    def test_group(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(1, 2, 1)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.select_element(ui2)

        hierarchy_tlui.group()

        assert len(hierarchy_tlui) == 3

    def test_delete_elements(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)

        hierarchy_tlui.select_element(ui1)

        hierarchy_tlui.delete_selected_elements()

        assert len(hierarchy_tlui) == 0

    def test_create_hierarchy_below(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        hierarchy_tlui.select_element(ui1)

        hierarchy_tlui.create_child()

        assert len(hierarchy_tlui) == 2

    def test_paste(self, hierarchy_tlui):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1, label="paste test")
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.collection._on_request_to_copy()
        hierarchy_tlui.deselect_element(ui1)

        hierarchy_tlui.select_element(ui2)
        hierarchy_tlui.paste()

        assert hrc2.label == "paste test"

    def test_paste_with_children(self, hierarchy_tlui):
        parent, parent_ui = hierarchy_tlui.create_hierarchy(0, 2, 2)
        child1, _ = hierarchy_tlui.create_hierarchy(0, 1, 1)
        child2, _ = hierarchy_tlui.create_hierarchy(1, 2, 1)
        receptor, receptor_ui = hierarchy_tlui.create_hierarchy(
            2, 3, 2, label="receptor"
        )

        hierarchy_tlui.relate_hierarchies(parent, [child1, child2])

        hierarchy_tlui.select_element(parent_ui)
        hierarchy_tlui.collection._on_request_to_copy()
        hierarchy_tlui.deselect_element(parent_ui)

        hierarchy_tlui.select_element(receptor_ui)
        hierarchy_tlui.paste_with_children()

        assert len(hierarchy_tlui) == 6

    def test_undo_redo_split(self, hierarchy_tlui, tluis):
        hierarchy_tlui.create_hierarchy(0, 1, 1)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        with PatchGet(
            "tilia.ui.timelines.hierarchy.timeline", Get.CURRENT_PLAYBACK_TIME, 0.5
        ):
            tluis.on_timeline_toolbar_button(TlKind.HIERARCHY_TIMELINE, "split")

        post(Post.REQUEST_TO_UNDO)
        assert len(hierarchy_tlui) == 1

        post(Post.REQUEST_TO_REDO)
        assert len(hierarchy_tlui) == 2

    def test_undo_redo_merge(self, hierarchy_tlui, tluis):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(1, 2, 1)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.select_element(ui2)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tluis.on_timeline_toolbar_button(TlKind.HIERARCHY_TIMELINE, "merge")

        post(Post.REQUEST_TO_UNDO)
        assert len(hierarchy_tlui) == 2

        post(Post.REQUEST_TO_REDO)
        assert len(hierarchy_tlui) == 1

    def test_undo_redo_increase_level(self, hierarchy_tlui, tluis):
        hrc, ui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.select_element(ui)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tluis.on_timeline_toolbar_button(TlKind.HIERARCHY_TIMELINE, "increase_level")

        post(Post.REQUEST_TO_UNDO)
        assert hierarchy_tlui.elements[0].level == 1

        post(Post.REQUEST_TO_REDO)
        assert hierarchy_tlui.elements[0].level == 2

    def test_undo_redo_decrease_level(self, hierarchy_tlui, tluis):
        hrc, ui = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hierarchy_tlui.select_element(ui)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tluis.on_timeline_toolbar_button(TlKind.HIERARCHY_TIMELINE, "decrease_level")

        post(Post.REQUEST_TO_UNDO)
        assert hierarchy_tlui.elements[0].level == 2

        post(Post.REQUEST_TO_REDO)
        assert hierarchy_tlui.elements[0].level == 1

    def test_undo_redo_group(self, hierarchy_tlui, tluis):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(1, 2, 1)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.select_element(ui2)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tluis.on_timeline_toolbar_button(TlKind.HIERARCHY_TIMELINE, "group")

        post(Post.REQUEST_TO_UNDO)
        assert len(hierarchy_tlui) == 2

        post(Post.REQUEST_TO_REDO)
        assert len(hierarchy_tlui) == 3

    def test_undo_redo_delete(self, hierarchy_tlui, tluis):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1)

        hierarchy_tlui.select_element(ui1)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tluis.on_timeline_toolbar_button(TlKind.HIERARCHY_TIMELINE, "delete")

        post(Post.REQUEST_TO_UNDO)
        assert len(hierarchy_tlui) == 1

        post(Post.REQUEST_TO_REDO)
        assert len(hierarchy_tlui) == 0

    def test_undo_redo_create_unit_below(self, hierarchy_tlui, tluis):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        hierarchy_tlui.select_element(ui1)

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        tluis.on_timeline_toolbar_button(TlKind.HIERARCHY_TIMELINE, "create_child")

        post(Post.REQUEST_TO_UNDO)
        assert len(hierarchy_tlui) == 1

        post(Post.REQUEST_TO_REDO)
        assert len(hierarchy_tlui) == 2

    def test_undo_redo_paste(self, hierarchy_tlui, tluis):
        hrc1, ui1 = hierarchy_tlui.create_hierarchy(0, 1, 1, label="paste test")
        hrc2, ui2 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        hierarchy_tlui.select_element(ui1)
        hierarchy_tlui.collection._on_request_to_copy()
        hierarchy_tlui.deselect_element(ui1)

        hierarchy_tlui.select_element(ui2)
        tluis.on_timeline_toolbar_button(TlKind.HIERARCHY_TIMELINE, "paste")

        assert hrc2.label == "paste test"

        post(Post.REQUEST_TO_UNDO)
        hrc_ui2 = hierarchy_tlui.element_manager.ordered_elements[1]
        assert hrc_ui2.label == ""

        post(Post.REQUEST_TO_REDO)
        hrc_ui2 = hierarchy_tlui.element_manager.ordered_elements[1]
        assert hrc_ui2.label == "paste test"

    def test_undo_redo_paste_with_children(self, hierarchy_tlui, tluis):
        parent, parent_ui = hierarchy_tlui.create_hierarchy(0, 2, 2)
        child1, _ = hierarchy_tlui.create_hierarchy(0, 1, 1)
        child2, _ = hierarchy_tlui.create_hierarchy(1, 2, 1)
        receptor, receptor_ui = hierarchy_tlui.create_hierarchy(2, 3, 2)

        hierarchy_tlui.relate_hierarchies(parent, [child1, child2])

        post(Post.REQUEST_RECORD_STATE, Action.TEST_STATE)

        hierarchy_tlui.select_element(parent_ui)
        tluis._on_request_to_copy()
        hierarchy_tlui.deselect_element(parent_ui)

        hierarchy_tlui.select_element(receptor_ui)
        tluis.on_timeline_toolbar_button(
            TlKind.HIERARCHY_TIMELINE, "paste_with_children"
        )

        post(Post.REQUEST_TO_UNDO)
        assert len(hierarchy_tlui) == 4

        post(Post.REQUEST_TO_REDO)
        assert len(hierarchy_tlui) == 6
