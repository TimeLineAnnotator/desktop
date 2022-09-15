import itertools
from unittest.mock import MagicMock

import pytest
import tkinter as tk

import tilia.ui.tkinter.timelines.copy_paste
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.common import ParentChildRelation
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.hierarchy.timeline import HierarchyTimeline, HierarchyTLComponentManager
from tilia.ui.tkinter.timelines.hierarchy import HierarchyTkUI
from tilia.ui.tkinter.timelines.hierarchy.timeline import (
    HierarchyTimelineTkUI, HierarchyTimelineToolbar
)
from tilia.ui.tkinter.timelines.common import TkTimelineUICollection, TimelineUIElementManager
from tilia.ui.tkinter.timelines.copy_paste import PasteError

import logging

logger = logging.getLogger(__name__)


@pytest.fixture
def hierarchy_timeline():
    yield HierarchyTimeline(
        collection=MagicMock(),
        component_manager=HierarchyTLComponentManager()
    )


@pytest.fixture
def tl_with_ui() -> HierarchyTimeline:
    id_counter = itertools.count()

    tl_coll_mock = MagicMock()
    tl_coll_mock.get_id = lambda: next(id_counter)

    tlui_coll_mock = MagicMock()
    tlui_coll_mock.get_id = lambda: next(id_counter)
    tlui_coll_mock.get_media_length.return_value = 1.0
    tlui_coll_mock.timeline_width = 200
    tlui_coll_mock.left_margin_x = 10

    component_manager = HierarchyTLComponentManager()
    timeline = HierarchyTimeline(tl_coll_mock, component_manager)
    timeline_ui = HierarchyTimelineTkUI(
        timeline_ui_collection=tlui_coll_mock,
        element_manager=TimelineUIElementManager(
            HierarchyTimelineTkUI.ELEMENT_KINDS_TO_ELEMENT_CLASSES
        ),
        canvas=tk.Canvas(),
        toolbar=MagicMock(),
        name="",
    )

    timeline.ui = timeline_ui
    timeline_ui.timeline = timeline

    component_manager.associate_to_timeline(timeline)
    yield timeline


@pytest.fixture
def mock_tluicoll():
    return TkTimelineUICollection(
        app_ui=MagicMock(),
        frame=MagicMock(),
        scrollbar=MagicMock(),
        toolbar_frame=MagicMock()
    )


@pytest.fixture
def hierarchy_tlui(mock_tluicoll):
    htlui = HierarchyTimelineTkUI(
        timeline_ui_collection=mock_tluicoll,
        element_manager=TimelineUIElementManager(HierarchyTimelineTkUI.ELEMENT_KINDS_TO_ELEMENT_CLASSES),
        canvas=tk.Canvas(),
        toolbar=MagicMock(),
        name='testHTL'
    )

    htlui.timeline = MagicMock(spec=HierarchyTimeline)

    return htlui


def is_in_front(id1: int, id2: int, canvas: tk.Canvas) -> bool:
    stacking_order = canvas.find_all()
    return stacking_order.index(id1) > stacking_order.index(id2)


def set_dummy_copy_attributes(hierarchy: Hierarchy) -> None:
    for attr in HierarchyTkUI.DEFAULT_COPY_ATTRIBUTES.by_component_value:
        setattr(hierarchy, attr, f'test {attr} - {id(hierarchy)}')

    for attr in HierarchyTkUI.DEFAULT_COPY_ATTRIBUTES.by_element_value:
        if attr == 'color':
            setattr(hierarchy.ui, attr, f"#FFFFFF")
            continue
        setattr(hierarchy.ui, attr, f'test {attr} - {id(hierarchy.ui)}')


def assert_are_copies(hierarchy1: Hierarchy, hierarchy2: Hierarchy):
    for attr in HierarchyTkUI.DEFAULT_COPY_ATTRIBUTES.by_component_value:
        assert getattr(hierarchy1, attr) == getattr(hierarchy2, attr)

    for attr in HierarchyTkUI.DEFAULT_COPY_ATTRIBUTES.by_element_value:
        assert getattr(hierarchy1.ui, attr) == getattr(hierarchy2.ui, attr)


def assert_is_copy_data_of(copy_data: dict, hierarchy_ui: Hierarchy):
    def _make_assertions(copy_data_: dict, hierarchy_ui_: Hierarchy):
        for attr, value in copy_data['by_element_value'].items():
            assert value == getattr(hierarchy_ui, attr)

        for attr, value in copy_data['support_by_element_value'].items():
            assert value == getattr(hierarchy_ui, attr)

        for attr, value in copy_data['by_component_value'].items():
            assert value == getattr(hierarchy_ui.tl_component, attr)

        for attr, value in copy_data['support_by_component_value'].items():
            assert value == getattr(hierarchy_ui.tl_component, attr)

    _make_assertions(copy_data, hierarchy_ui)

    if children := hierarchy_ui.tl_component.children:
        for index, child in enumerate(children):
            _make_assertions(child, copy_data['children'][index])


class TestHierarchyTimelineTkUI:

    def test_constructor(self, mock_tluicoll):
        HierarchyTimelineTkUI(
            timeline_ui_collection=mock_tluicoll,
            element_manager=TimelineUIElementManager(HierarchyTimelineTkUI.ELEMENT_KINDS_TO_ELEMENT_CLASSES),
            canvas=tk.Canvas(),
            toolbar=HierarchyTimelineToolbar,
            name='testHTL'
        )

    def test_rearrange_elements_two_levels(self, tl_with_ui):
        unit2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)
        unit3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        unit1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        unit1.children = [unit2, unit3]
        unit2.parent = unit1
        unit3.parent = unit1

        assert is_in_front(unit1.ui.rect_id, unit2.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit1.ui.rect_id, unit3.ui.rect_id, tl_with_ui.ui.canvas)

        tl_with_ui.ui.rearrange_canvas_drawings()

        assert is_in_front(unit2.ui.rect_id, unit1.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit3.ui.rect_id, unit1.ui.rect_id, tl_with_ui.ui.canvas)

    def test_rearrange_elements_three_levels(self, tl_with_ui):
        unit1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)
        unit2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        unit3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1.5, 2, 1)
        unit4 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 1.5, 1)
        unit5 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)
        unit6 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 2, 2)
        unit7 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 2, 3)

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

        tl_with_ui.ui.rearrange_canvas_drawings()

        assert is_in_front(unit1.ui.rect_id, unit5.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit2.ui.rect_id, unit5.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit3.ui.rect_id, unit6.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit4.ui.rect_id, unit6.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit5.ui.rect_id, unit7.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit6.ui.rect_id, unit7.ui.rect_id, tl_with_ui.ui.canvas)

    def test_rearrange_elements_four_levels(self, tl_with_ui):
        unit1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)
        unit2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        unit3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1.5, 2, 1)
        unit4 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 1.5, 1)
        unit5 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)
        unit6 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 2, 2)
        unit7 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 2, 3)
        unit8 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 2.5, 3, 1)
        unit9 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 2, 4.5, 1)
        unit10 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 3.5, 4, 1)
        unit11 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 3, 3.5, 1)
        unit12 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 2, 3, 2)
        unit13 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 3, 4, 2)
        unit14 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 2, 4, 3)
        unit15 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 4, 4)

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

        tl_with_ui.ui.rearrange_canvas_drawings()

        assert is_in_front(unit1.ui.rect_id, unit5.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit2.ui.rect_id, unit5.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit3.ui.rect_id, unit6.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit4.ui.rect_id, unit6.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit5.ui.rect_id, unit7.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit6.ui.rect_id, unit7.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit7.ui.rect_id, unit15.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit8.ui.rect_id, unit12.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit9.ui.rect_id, unit12.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit10.ui.rect_id, unit13.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit11.ui.rect_id, unit13.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit12.ui.rect_id, unit14.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit13.ui.rect_id, unit14.ui.rect_id, tl_with_ui.ui.canvas)
        assert is_in_front(unit14.ui.rect_id, unit15.ui.rect_id, tl_with_ui.ui.canvas)

    #######################
    ### TEST COPY/PASTE ###
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

    def test_paste_without_children_into_selected_elements(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)

        set_dummy_copy_attributes(hrc1)

        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)

        copy_data = tilia.ui.tkinter.timelines.copy_paste.get_copy_data_from_element(hrc1.ui, HierarchyTkUI.DEFAULT_COPY_ATTRIBUTES)
        tl_with_ui.ui._select_element(hrc2.ui)
        tl_with_ui.ui.paste_into_selected_elements([copy_data])

        assert_are_copies(hrc1, hrc2)

    def test_get_copy_data_from_hierarchy_uis(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        copy_data = tl_with_ui.ui.get_copy_data_from_hierarchy_uis([hrc1.ui, hrc2.ui])

        assert_is_copy_data_of(copy_data[0], hrc1.ui)
        assert_is_copy_data_of(copy_data[1], hrc2.ui)

    def test_get_copy_data_from_hierarchy_ui_with_children(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)
        hrc3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)
        set_dummy_copy_attributes(hrc3)

        hrc3.children = [hrc1, hrc2]
        hrc1.parent = hrc3
        hrc2.parent = hrc3

        copy_data = tl_with_ui.ui.get_copy_data_from_hierarchy_uis([hrc3.ui])

        assert_is_copy_data_of(copy_data[0], hrc3.ui)

    def test_paste_with_children_into_selected_elements_without_rescaling(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)
        hrc3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)
        hrc4 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 2, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1, hrc2])
        )

        copy_data = tl_with_ui.ui.get_copy_data_from_hierarchy_uis([hrc3.ui])

        tl_with_ui.ui._select_element(hrc4.ui)

        tl_with_ui.ui.paste_with_children_into_selected_elements(copy_data)

        assert len(tl_with_ui.component_manager._components) == 6
        assert len(hrc4.children) == 2

        copied_children_1, copied_children_2 = sorted(hrc4.children, key=lambda h: h.start)

        assert copied_children_1.parent == hrc4
        assert copied_children_1.start == 1.0
        assert copied_children_1.end == 1.5

        assert copied_children_2.parent == hrc4
        assert copied_children_2.start == 1.5
        assert copied_children_2.end == 2.0

        assert_are_copies(copied_children_1, hrc1)
        assert_are_copies(copied_children_2, hrc2)

    def test_paste_with_children_into_selected_elements_with_rescaling(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)
        hrc3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)
        hrc4 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 1.5, 2)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1, hrc2])
        )

        copy_data = tl_with_ui.ui.get_copy_data_from_hierarchy_uis([hrc3.ui])

        tl_with_ui.ui._select_element(hrc4.ui)

        tl_with_ui.ui.paste_with_children_into_selected_elements(copy_data)

        copied_children_1, copied_children_2 = sorted(hrc4.children, key=lambda h: h.start)

        assert copied_children_1.parent == hrc4
        assert copied_children_1.start == 1.0
        assert copied_children_1.end == 1.25

        assert copied_children_2.parent == hrc4
        assert copied_children_2.start == 1.25
        assert copied_children_2.end == 1.5

    def test_paste_with_children_that_have_children(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)
        hrc3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 2)
        hrc4 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 2)
        hrc5 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 3)
        hrc6 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 2, 3)

        set_dummy_copy_attributes(hrc1)
        set_dummy_copy_attributes(hrc2)

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1])
        )

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc4, children=[hrc2])
        )

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc5, children=[hrc3, hrc4])
        )

        copy_data = tl_with_ui.ui.get_copy_data_from_hierarchy_uis([hrc5.ui])

        tl_with_ui.ui._select_element(hrc6.ui)

        tl_with_ui.ui.paste_with_children_into_selected_elements(copy_data)

        copied_children_1, copied_children_2 = sorted(hrc6.children, key=lambda h: h.start)

        assert len(copied_children_1.children) == 1
        assert copied_children_1.children[0].start == 1
        assert copied_children_1.children[0].end == 1.5

        assert len(copied_children_2.children) == 1
        assert copied_children_2.children[0].start == 1.5
        assert copied_children_2.children[0].end == 2.0

    def test_paste_with_children_into_different_level_raises_error(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)
        hrc3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)
        hrc4 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 1.5, 3)

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1, hrc2])
        )

        copy_data = tilia.ui.tkinter.timelines.copy_paste.get_copy_data_from_element(hrc3.ui, HierarchyTkUI.DEFAULT_COPY_ATTRIBUTES)

        tl_with_ui.ui._select_element(hrc4.ui)

        with pytest.raises(PasteError):
            tl_with_ui.ui.paste_with_children_into_selected_elements([copy_data])

    def test_paste_with_children_paste_two_elements_raises_error(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)
        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)
        hrc3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)
        hrc4 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 1.5, 2)

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1, hrc2])
        )

        copy_data = tilia.ui.tkinter.timelines.copy_paste.get_copy_data_from_element(hrc3.ui, HierarchyTkUI.DEFAULT_COPY_ATTRIBUTES)

        tl_with_ui.ui._select_element(hrc4.ui)

        with pytest.raises(PasteError):
            tl_with_ui.ui.paste_with_children_into_selected_elements([copy_data, copy_data])



