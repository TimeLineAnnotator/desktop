from __future__ import annotations

from tilia.requests import get, Get, Post, listen
from tilia.timelines.hierarchy.common import (
    update_component_genealogy,
)
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
)
from tilia.ui.timelines.collection.requests.enums import ElementSelector
from tilia.ui.timelines.hierarchy import HierarchyTimelineToolbar, HierarchyUI
from tilia.ui.timelines.copy_paste import get_copy_data_from_element
import tilia.ui.timelines.copy_paste
from tilia.ui.timelines.copy_paste import paste_into_element
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.hierarchy.handles import HierarchyBodyHandle
from tilia.ui.timelines.hierarchy.key_press_manager import (
    HierarchyTimelineUIKeyPressManager,
)
from tilia.ui.timelines.hierarchy.request_handlers import HierarchyUIRequestHandler
from tilia.undo_manager import PauseUndoManager


class HierarchyTimelineUI(TimelineUI):
    TOOLBAR_CLASS = HierarchyTimelineToolbar
    ELEMENT_CLASS = HierarchyUI
    TIMELINE_KIND = TimelineKind.HIERARCHY_TIMELINE
    ACCEPTS_HORIZONTAL_ARROWS = True
    ACCEPTS_VERTICAL_ARROWS = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listen(self, Post.SETTINGS_UPDATED, lambda updated_settings: self.on_settings_updated(updated_settings))

    def on_settings_updated(self, updated_settings):        
        if "hierarchy_timeline" in updated_settings:
            get(Get.TIMELINE_COLLECTION).set_timeline_data(self.id, "height", self.timeline.default_height)
            for hierarchy_ui in self:
                hierarchy_ui.update_position()
                hierarchy_ui.update_color()            

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return HierarchyUIRequestHandler(self).on_request(
            request, selector, *args, **kwargs
        )

    def get_handle_by_x(self, x: float):
        def starts_or_ends_at_time(ui: HierarchyUI) -> bool:
            return ui.start_x == x or ui.end_x == x

        element: HierarchyUI | None = self.element_manager.get_element_by_condition(
            starts_or_ends_at_time
        )

        if not element:
            return

        if element.start_x == x:
            return element.start_handle
        elif element.end_x == x:
            return element.end_handle
        else:
            raise ValueError(
                "Can't get handle: handle in found element is not at desired x."
            )

    def get_units_sharing_handle(
        self, handle: HierarchyBodyHandle
    ) -> list[HierarchyBodyHandle]:
        def is_using_handle(e: HierarchyUI):
            return e.start_handle == handle or e.end_handle == handle

        return self.element_manager.get_elements_by_condition(is_using_handle)

    def get_previous_handle_x_by_x(self, x: float) -> None | int:
        all_marker_xs = self.get_all_elements_boundaries()
        earlier_marker_xs = [x_ for x_ in all_marker_xs if x_ < x]

        if earlier_marker_xs:
            return max(earlier_marker_xs)
        else:
            return None

    def get_next_handle_x_by_x(self, x: float) -> None | int:
        all_marker_xs = self.get_all_elements_boundaries()
        later_marker_xs = [x_ for x_ in all_marker_xs if x_ > x]

        if later_marker_xs:
            return min(later_marker_xs)
        else:
            return None

    def get_all_elements_boundaries(self) -> set[int]:
        """Returns all the start_x and end_x values for hierarchy ui's in timeline."""
        earlier_boundaries = self.element_manager.get_existing_values_for_attribute(
            "start_x"
        )
        later_boundaries = self.element_manager.get_existing_values_for_attribute(
            "end_x"
        )

        return earlier_boundaries.union(later_boundaries)

    def paste_single_into_selected_elements(self, paste_data: list[dict]):
        for element in self.element_manager.get_selected_elements():
            self.deselect_element(element)
            paste_into_element(element, paste_data[0])
            self.select_element(element)

    def _create_child_from_paste_data(
        self,
        new_parent: HierarchyUI,
        prev_parent_start: float,
        prev_parent_end: float,
        child_pastedata_: dict,
    ):

        new_parent_length = new_parent.tl_component.end - new_parent.tl_component.start

        prev_parent_length = prev_parent_end - prev_parent_start
        scale_factor = new_parent_length / prev_parent_length

        relative_child_start = (
            child_pastedata_["support_by_component_value"]["start"] - prev_parent_start
        )

        new_child_start = (
            relative_child_start * scale_factor
        ) + new_parent.tl_component.start

        relative_child_end = (
            child_pastedata_["support_by_component_value"]["end"] - prev_parent_end
        )

        new_child_end = (
            relative_child_end * scale_factor
        ) + new_parent.tl_component.end

        component, _ = self.timeline.create_component(
            kind=ComponentKind.HIERARCHY,
            start=new_child_start,
            end=new_child_end,
            level=child_pastedata_["support_by_component_value"]["level"],
            **child_pastedata_["by_element_value"],
            **child_pastedata_["by_component_value"],
        )

        return component

    def paste_with_children_into_element(self, paste_data: dict, element: HierarchyUI):
        tilia.ui.timelines.copy_paste.paste_into_element(element, paste_data)

        if "children" in paste_data:
            children_of_element = []
            for child_paste_data in paste_data["children"]:
                child_component = self._create_child_from_paste_data(
                    element,
                    paste_data["support_by_component_value"]["start"],
                    paste_data["support_by_component_value"]["end"],
                    child_paste_data,
                )

                if child_paste_data.get("children", None):
                    self.paste_with_children_into_element(
                        child_paste_data, self.get_component_ui(child_component)
                    )

                children_of_element.append(child_component)

            update_component_genealogy(element.tl_component, children_of_element)

    def paste_with_children_into_elements(
        self, elements: list[HierarchyUI], data: list[dict]
    ):
        def get_descendants(parent: HierarchyUI):
            is_in_branch = (
                lambda e: e.tl_component.start >= parent.tl_component.start
                and e.tl_component.end <= parent.tl_component.end
            )
            elements_in_branch = self.element_manager.get_elements_by_condition(
                is_in_branch
            )
            elements_in_branch.remove(parent)
            return elements_in_branch

        for elm in elements:
            self.deselect_element(elm)
            # delete previous descendants
            descendants = get_descendants(elm)
            for descendant in descendants:
                with PauseUndoManager():
                    self.timeline.delete_components([descendant.tl_component])

            # create children according to paste data
            self.paste_with_children_into_element(data[0], elm)

        # TODO preserve selection

    def get_copy_data_from_hierarchy_ui(self, hierarchy_ui: HierarchyUI):
        ui_data = get_copy_data_from_element(
            hierarchy_ui, HierarchyUI.DEFAULT_COPY_ATTRIBUTES
        )

        if children := hierarchy_ui.get_data("children"):
            ui_data["children"] = [
                self.get_copy_data_from_hierarchy_ui(self.id_to_element[child.id])
                for child in children
            ]

        return ui_data

    def on_horizontal_arrow_press(self, arrow: str):
        HierarchyTimelineUIKeyPressManager(self).on_horizontal_arrow_press(arrow)

    def on_vertical_arrow_press(self, arrow: str):
        HierarchyTimelineUIKeyPressManager(self).on_vertical_arrow_press(arrow)
