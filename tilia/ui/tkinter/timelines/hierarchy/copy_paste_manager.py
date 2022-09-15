from __future__ import annotations

from tilia.timelines.hierarchy.components import Hierarchy
from tilia.ui.element_kinds import UIElementKind
from tilia.ui.timelines.common import TimelineUIElement
from tilia.ui.tkinter.timelines.common import CopyPasteManager, CopyError, PasteError, CopyAttributes
from tilia.ui.tkinter.timelines.hierarchy import HierarchyTkUI


class HierarchyTimelineCopyPasteManager(CopyPasteManager):

    DEFAULT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE = ["label", "color"]
    DEFAULT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE = ["formal_type", "formal_function", "comments"]
    SUPPORT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE = []
    SUPPORT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE = ["start", "end", "level"]


    def validate_copy(self, elements: list[TimelineUIElement]) -> None:
        if len(elements) > 1:
            raise CopyError(f"Can't copy more than one hierarchy at once.")


    @staticmethod
    def validate_paste_with_children(paste_data: list[dict], elements_to_receive_paste: list[HierarchyTkUI]) -> None:
        for element in elements_to_receive_paste:
            if len(paste_data) > 1:
                raise PasteError("Can't paste more than one Hierarchy at the same time.")
            elif element.level != int(paste_data[0]["support_by_component_value"]["level"]):
                raise PasteError("Can't paste all of unit's attributes (including children) into unit of different level.")

    def get_copy_data_for_element(self, hierarchy_ui: HierarchyTkUI):
        """
        Returns a dict with the data relevant for copying the given
        HierarchyUI. The data is divided into four different dictionary
        keys, depending on whether the attribute will be directly copied
        (DEFAULT_COPY_ATTRIBUTES) or be used for calculations
        during the copy process (SUPPORT_COPY_ATTRIBUTES).
        """

        copy_attrs = CopyAttributes(
            self.DEFAULT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE,
            self.DEFAULT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE,
            self.SUPPORT_COPY_ATTRIBUTES_BY_ELEMENT_VALUE,
            self.SUPPORT_COPY_ATTRIBUTES_BY_COMPONENT_VALUE
        )

        copy_data = self._get_copy_data_for_element(
            hierarchy_ui,
            UIElementKind.HIERARCHY_TKUI,
            copy_attrs
        )

        if hierarchy_ui.tl_component.children:
            copy_data["children"] = [self.get_copy_data_for_element(child.ui) for child in hierarchy_ui.tl_component.children]

        return copy_data