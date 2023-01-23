from unittest.mock import patch

import pytest
import tkinter as tk

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.common import ParentChildRelation as PCRel
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.create import create_timeline
from tilia.ui.timelines.copy_paste import PasteError
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI, HierarchyUI


class TestHierarchyTimelineUI(HierarchyTimelineUI):
    def create_hierarchy(
        self, start: float, end: float, level: int, **kwargs
    ) -> Hierarchy:
        ...

    def relate_hierarchies(self, relation: PCRel):
        ...


@pytest.fixture
def hierarchy_tlui(tl_clct, tlui_clct) -> TestHierarchyTimelineUI:
    def create_hierarchy(start: float, end: float, level: int, **kwargs) -> Hierarchy:
        return tl.create_timeline_component(
            ComponentKind.HIERARCHY, start, end, level, **kwargs
        )

    def relate_hierarchies(relation: PCRel):
        return tl.component_manager._make_parent_child_relation(relation)

    tl: HierarchyTimeline = create_timeline(
        TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct
    )
    tl.clear()
    tl.ui.create_hierarchy = create_hierarchy
    tl.ui.relate_hierarchies = relate_hierarchies
    yield tl.ui
    tl_clct.delete_timeline(tl)


def is_in_front(id1: int, id2: int, canvas: tk.Canvas) -> bool:
    stacking_order = canvas.find_all()
    return stacking_order.index(id1) > stacking_order.index(id2)


def set_dummy_copy_attributes(hierarchy: Hierarchy) -> None:
    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.by_component_value:
        setattr(hierarchy, attr, f"test {attr} - {id(hierarchy)}")

    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.by_element_value:
        if attr == "color":
            setattr(hierarchy.ui, attr, f"#FFFFFF")
            continue
        setattr(hierarchy.ui, attr, f"test {attr} - {id(hierarchy.ui)}")


def assert_are_copies(hierarchy1: Hierarchy, hierarchy2: Hierarchy):
    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.by_component_value:
        assert getattr(hierarchy1, attr) == getattr(hierarchy2, attr)

    for attr in HierarchyUI.DEFAULT_COPY_ATTRIBUTES.by_element_value:
        assert getattr(hierarchy1.ui, attr) == getattr(hierarchy2.ui, attr)


def assert_is_copy_data_of(copy_data: dict, hierarchy_ui: HierarchyUI):
    def _make_assertions(copy_data_: dict, hierarchy_ui_: HierarchyUI):
        for attr, value in copy_data["by_element_value"].items():
            assert value == getattr(hierarchy_ui, attr)

        for attr, value in copy_data["support_by_element_value"].items():
            assert value == getattr(hierarchy_ui, attr)

        for attr, value in copy_data["by_component_value"].items():
            assert value == getattr(hierarchy_ui.tl_component, attr)

        for attr, value in copy_data["support_by_component_value"].items():
            assert value == getattr(hierarchy_ui.tl_component, attr)

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

        hrc1 = hierarchy_tlui.create_hierarchy(0, 0, 1)

        hierarchy_tlui.right_clicked_element = hrc1.ui

        hierarchy_tlui.right_click_menu_increase_level()

        assert hrc1.level == 2

    def test_right_click_decrease_level(self, hierarchy_tlui):

        hrc1 = hierarchy_tlui.create_hierarchy(0, 0, 2)

        hierarchy_tlui.right_clicked_element = hrc1.ui

        hierarchy_tlui.right_click_menu_decrease_level()

        assert hrc1.level == 1

    @patch("tilia.ui.common.ask_for_color")
    def test_right_click_change_color(self, ask_for_color_mock, hierarchy_tlui):

        ask_for_color_mock.return_value = "#000000"

        hrc1 = hierarchy_tlui.create_hierarchy(0, 0, 1)

        hierarchy_tlui.right_clicked_element = hrc1.ui

        hierarchy_tlui.right_click_menu_change_color()

        assert hrc1.ui.color == "#000000"

    @patch("tilia.ui.common.ask_for_color")
    def test_right_click_reset_color(self, ask_for_color_mock, hierarchy_tlui):

        ask_for_color_mock.return_value = "#000000"

        hrc1 = hierarchy_tlui.create_hierarchy(0, 0, 1)

        hierarchy_tlui.right_clicked_element = hrc1.ui

        hierarchy_tlui.right_click_menu_change_color()
        hierarchy_tlui.right_click_menu_reset_color()

        assert hrc1.ui.color == hrc1.ui.get_default_level_color(hrc1.level)

    def test_rearrange_elements_two_levels(self, hierarchy_tlui):
        unit2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        unit3 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        unit1 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        unit1.children = [unit2, unit3]
        unit2.parent = unit1
        unit3.parent = unit1

        assert is_in_front(unit1.ui.rect_id, unit2.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit1.ui.rect_id, unit3.ui.rect_id, hierarchy_tlui.canvas)

        hierarchy_tlui.rearrange_canvas_drawings()

        assert is_in_front(unit2.ui.rect_id, unit1.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit3.ui.rect_id, unit1.ui.rect_id, hierarchy_tlui.canvas)

    def test_rearrange_elements_three_levels(self, hierarchy_tlui):
        unit1 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        unit2 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        unit3 = hierarchy_tlui.create_hierarchy(1.5, 2, 1)
        unit4 = hierarchy_tlui.create_hierarchy(1, 1.5, 1)
        unit5 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        unit6 = hierarchy_tlui.create_hierarchy(1, 2, 2)
        unit7 = hierarchy_tlui.create_hierarchy(0, 2, 3)

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

        assert is_in_front(unit1.ui.rect_id, unit5.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit2.ui.rect_id, unit5.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit3.ui.rect_id, unit6.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit4.ui.rect_id, unit6.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit5.ui.rect_id, unit7.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit6.ui.rect_id, unit7.ui.rect_id, hierarchy_tlui.canvas)

    def test_rearrange_elements_four_levels(self, hierarchy_tlui):
        unit1 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        unit2 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        unit3 = hierarchy_tlui.create_hierarchy(1.5, 2, 1)
        unit4 = hierarchy_tlui.create_hierarchy(1, 1.5, 1)
        unit5 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        unit6 = hierarchy_tlui.create_hierarchy(1, 2, 2)
        unit7 = hierarchy_tlui.create_hierarchy(0, 2, 3)
        unit8 = hierarchy_tlui.create_hierarchy(2.5, 3, 1)
        unit9 = hierarchy_tlui.create_hierarchy(2, 4.5, 1)
        unit10 = hierarchy_tlui.create_hierarchy(3.5, 4, 1)
        unit11 = hierarchy_tlui.create_hierarchy(3, 3.5, 1)
        unit12 = hierarchy_tlui.create_hierarchy(2, 3, 2)
        unit13 = hierarchy_tlui.create_hierarchy(3, 4, 2)
        unit14 = hierarchy_tlui.create_hierarchy(2, 4, 3)
        unit15 = hierarchy_tlui.create_hierarchy(0, 4, 4)

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

        assert is_in_front(unit1.ui.rect_id, unit5.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit2.ui.rect_id, unit5.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit3.ui.rect_id, unit6.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit4.ui.rect_id, unit6.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit5.ui.rect_id, unit7.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit6.ui.rect_id, unit7.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit7.ui.rect_id, unit15.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit8.ui.rect_id, unit12.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit9.ui.rect_id, unit12.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit10.ui.rect_id, unit13.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit11.ui.rect_id, unit13.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit12.ui.rect_id, unit14.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit13.ui.rect_id, unit14.ui.rect_id, hierarchy_tlui.canvas)
        assert is_in_front(unit14.ui.rect_id, unit15.ui.rect_id, hierarchy_tlui.canvas)

        #######################
        ### TEST COPY.PASTE ###
        #######################

    def test_get_copy_data_for_hierarchy_with_children(self):
        # TODO
        # cpm = HierarchyTimelineCopyPasteManager()
        # h_mock, hui_mock = hierarchy_with_ui_mock()
        # h_mock_child1, hui_mock_child1 = hierarchy_with_ui_mock()
        # h_mock_child2, hui_mock_child2 = hierarchy_with_ui_mock()
        #
        # h_mock.children.append(h_mock_child1)
        # h_mock.children.append(h_mock_child2)
        #
        # copy_data = cpm.get_copy_data_for_hierarchy_ui(hui_mock)
        # child1_copy_data = cpm.get_copy_data_for_hierarchy_ui(hui_mock_child1)
        # child2_copy_data = cpm.get_copy_data_for_hierarchy_ui(hui_mock_child2)
        #
        #
        # for attr in HierarchyTimelineCopyPasteManager.DEFAULT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE:
        #     assert copy_data['by_component_value'][attr] == getattr(h_mock, attr)
        #
        # for attr in HierarchyTimelineCopyPasteManager.SUPPORT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE:
        #     assert copy_data['support_by_component_value'][attr] == getattr(h_mock, attr)
        #
        # for attr in HierarchyTimelineCopyPasteManager.DEFAULT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE:
        #     assert copy_data['by_element_value'][attr] == getattr(hui_mock, attr)
        #
        # for attr in HierarchyTimelineCopyPasteManager.SUPPORT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE:
        #     assert copy_data['support_by_element_value'][attr] == getattr(hui_mock, attr)
        #
        # assert child1_copy_data in copy_data['children']
        # assert child2_copy_data in copy_data['children']
        pass

    @patch("tilia.ui.timelines.hierarchy.element.HierarchyUI.on_select")
    def test_paste_without_children_into_selected_elements(
        self, on_select_mock, hierarchy_tlui
    ):
        on_select_mock.return_value = None

        hrc1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)

        set_dummy_copy_attributes(hrc1)

        hrc2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([hrc1.ui])
        hierarchy_tlui.select_element(hrc2.ui)
        hierarchy_tlui.paste_single_into_selected_elements(copy_data)

        assert_are_copies(hrc1, hrc2)

    def test_get_copy_data_from_hierarchy_uis(self, hierarchy_tlui):
        hrc1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([hrc1.ui, hrc2.ui])

        assert_is_copy_data_of(copy_data[0], hrc1.ui)
        assert_is_copy_data_of(copy_data[1], hrc2.ui)

    def test_get_copy_data_from_hierarchy_ui_with_children(self, hierarchy_tlui):
        hrc1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3 = hierarchy_tlui.create_hierarchy(0, 1, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)
        set_dummy_copy_attributes(hrc3)

        hrc3.children = [hrc1, hrc2]
        hrc1.parent = hrc3
        hrc2.parent = hrc3

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([hrc3.ui])

        assert_is_copy_data_of(copy_data[0], hrc3.ui)

    @patch("tilia.ui.timelines.hierarchy.element.HierarchyUI.on_select")
    def test_paste_with_children_into_selected_elements_without_rescaling(
        self, on_select_mock, hierarchy_tlui
    ):
        on_select_mock.return_value = None

        hrc1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hrc4 = hierarchy_tlui.create_hierarchy(1, 2, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        hierarchy_tlui.relate_hierarchies(PCRel(parent=hrc3, children=[hrc1, hrc2]))

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([hrc3.ui])

        hierarchy_tlui.select_element(hrc4.ui)

        hierarchy_tlui.paste_with_children_into_selected_elements(copy_data)

        assert len(hierarchy_tlui.timeline.component_manager._components) == 6
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

    @patch("tilia.ui.timelines.hierarchy.element.HierarchyUI.on_select")
    def test_paste_with_children_into_selected_elements_with_rescaling(
        self, on_select_mock, hierarchy_tlui
    ):
        on_select_mock.return_value = None

        hrc1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hrc4 = hierarchy_tlui.create_hierarchy(1, 1.5, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        hierarchy_tlui.relate_hierarchies(PCRel(parent=hrc3, children=[hrc1, hrc2]))

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([hrc3.ui])

        hierarchy_tlui.select_element(hrc4.ui)

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

    @patch("tilia.ui.timelines.hierarchy.element.HierarchyUI.on_select")
    def test_paste_with_children_that_have_children(
        self, on_select_mock, hierarchy_tlui
    ):
        on_select_mock.return_value = None

        hrc1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3 = hierarchy_tlui.create_hierarchy(0, 0.5, 2)
        hrc4 = hierarchy_tlui.create_hierarchy(0.5, 1, 2)
        hrc5 = hierarchy_tlui.create_hierarchy(0, 1, 3)
        hrc6 = hierarchy_tlui.create_hierarchy(1, 2, 3)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        hierarchy_tlui.relate_hierarchies(PCRel(parent=hrc3, children=[hrc1]))

        hierarchy_tlui.relate_hierarchies(PCRel(parent=hrc4, children=[hrc2]))

        hierarchy_tlui.relate_hierarchies(PCRel(parent=hrc5, children=[hrc3, hrc4]))

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([hrc5.ui])

        hierarchy_tlui.select_element(hrc6.ui)

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

    @patch("tilia.ui.timelines.hierarchy.element.HierarchyUI.on_select")
    def test_paste_with_children_into_different_level_raises_error(
        self, on_select_mock, hierarchy_tlui
    ):
        on_select_mock.return_value = None

        hrc1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hrc4 = hierarchy_tlui.create_hierarchy(1, 1.5, 3)

        hierarchy_tlui.relate_hierarchies(PCRel(parent=hrc3, children=[hrc1, hrc2]))

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([hrc3.ui])

        hierarchy_tlui.select_element(hrc4.ui)

        with pytest.raises(PasteError):
            hierarchy_tlui.paste_with_children_into_selected_elements(copy_data)

    @patch("tilia.ui.timelines.hierarchy.element.HierarchyUI.on_select")
    def test_paste_with_children_paste_two_elements_raises_error(
        self, on_select_mock, hierarchy_tlui
    ):
        on_select_mock.return_value = None
        hrc1 = hierarchy_tlui.create_hierarchy(0, 0.5, 1)
        hrc2 = hierarchy_tlui.create_hierarchy(0.5, 1, 1)
        hrc3 = hierarchy_tlui.create_hierarchy(0, 1, 2)
        hrc4 = hierarchy_tlui.create_hierarchy(1, 1.5, 2)

        hierarchy_tlui.relate_hierarchies(PCRel(parent=hrc3, children=[hrc1, hrc2]))

        copy_data = hierarchy_tlui.get_copy_data_from_hierarchy_uis([hrc3.ui, hrc4.ui])

        hierarchy_tlui.select_element(hrc4.ui)

        with pytest.raises(PasteError):
            hierarchy_tlui.paste_with_children_into_selected_elements(copy_data)
