import pytest
import tkinter as tk

from tilia.ui.tkinter.timelines.hierarchy.timeline import (
    HierarchyTimelineCopyPasteManager
)


def hierarchy_with_ui_mock():
    h = HierarchyMockForCopy()
    hui = HierarchyUIMockForCopy()

    h.ui = hui
    hui.tl_component = h

    return h, hui


class HierarchyMockForCopy:
    def __init__(self):
        for attr in HierarchyTimelineCopyPasteManager.DEFAULT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE:
            setattr(self, attr, f'test {attr} - {id(self)}')

        for attr in HierarchyTimelineCopyPasteManager.SUPPORT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE:
            setattr(self, attr, f'test {attr} - {id(self)}')

        self.children = []
        self.parent = None



class HierarchyUIMockForCopy:
    def __init__(self):
        for attr in HierarchyTimelineCopyPasteManager.DEFAULT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE:
            setattr(self, attr, f'test {attr} - {id(self)}')

        for attr in HierarchyTimelineCopyPasteManager.SUPPORT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE:
            setattr(self, attr, f'test {attr} - {id(self)}')



class TestHierarchyTimelineCopyPasteManager:
    def test_constructor(self):
        HierarchyTimelineCopyPasteManager()

    def test_get_copy_data_for_element_with_children(self):
        cpm = HierarchyTimelineCopyPasteManager()
        h_mock, hui_mock = hierarchy_with_ui_mock()
        h_mock_child1, hui_mock_child1 = hierarchy_with_ui_mock()
        h_mock_child2, hui_mock_child2 = hierarchy_with_ui_mock()

        h_mock.children.append(h_mock_child1)
        h_mock.children.append(h_mock_child2)

        copy_data = cpm.get_copy_data_for_element(hui_mock)
        child1_copy_data = cpm.get_copy_data_for_element(hui_mock_child1)
        child2_copy_data = cpm.get_copy_data_for_element(hui_mock_child2)


        for attr in HierarchyTimelineCopyPasteManager.DEFAULT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE:
            assert copy_data['by_component_value'][attr] == getattr(h_mock, attr)

        for attr in HierarchyTimelineCopyPasteManager.SUPPORT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE:
            assert copy_data['support_by_component_value'][attr] == getattr(h_mock, attr)

        for attr in HierarchyTimelineCopyPasteManager.DEFAULT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE:
            assert copy_data['by_element_value'][attr] == getattr(hui_mock, attr)

        for attr in HierarchyTimelineCopyPasteManager.SUPPORT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE:
            assert copy_data['support_by_element_value'][attr] == getattr(hui_mock, attr)

        assert child1_copy_data in copy_data['children']
        assert child2_copy_data in copy_data['children']
