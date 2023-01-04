"""
Defines the tkinter ui corresponding a HierarchyTimeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import tilia.ui.timelines.copy_paste
from tilia.ui.timelines.copy_paste import paste_into_element
from tilia.timelines.component_kinds import ComponentKind
from tilia.events import Event, subscribe
from tilia.misc_enums import IncreaseOrDecrease, Side, UpOrDown
from tilia.timelines.state_actions import StateAction

from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.ui.timelines.common import TimelineCanvas
    from tilia.ui.timelines.collection import TimelineUICollection

import logging

logger = logging.getLogger(__name__)
import tkinter as tk

from tilia import events, settings
from tilia.timelines.hierarchy.common import (
    ParentChildRelation,
    process_parent_child_relation,
)
from tilia.ui.timelines.timeline import (
    TimelineUI,
    RightClickOption,
    TimelineUIElementManager,
)
from tilia.ui.timelines.hierarchy import HierarchyTimelineToolbar, HierarchyUI

from tilia.ui.timelines.copy_paste import (
    CopyError,
    PasteError,
    Copyable,
    get_copy_data_from_element,
)
from tilia.ui.element_kinds import UIElementKind


class HierarchyTimelineUI(TimelineUI):
    DEFAULT_HEIGHT = settings.settings['hierarchy_timeline']['default_height']

    TOOLBAR_CLASS = HierarchyTimelineToolbar
    ELEMENT_KINDS_TO_ELEMENT_CLASSES = {UIElementKind.HIERARCHY_TKUI: HierarchyUI}
    COMPONENT_KIND_TO_UIELEMENT_KIND = {
        ComponentKind.HIERARCHY: UIElementKind.HIERARCHY_TKUI
    }

    TIMELINE_KIND = TimelineKind.HIERARCHY_TIMELINE

    def __init__(
        self,
        *args,
        timeline_ui_collection: TimelineUICollection,
        element_manager: TimelineUIElementManager,
        canvas: TimelineCanvas,
        toolbar: HierarchyTimelineToolbar,
        name: str,
        height: int = DEFAULT_HEIGHT,
        is_visible: bool = True,
        **kwargs,
    ):

        super().__init__(
            *args,
            timeline_ui_collection=timeline_ui_collection,
            timeline_ui_element_manager=element_manager,
            component_kinds_to_classes=self.ELEMENT_KINDS_TO_ELEMENT_CLASSES,
            component_kinds_to_ui_element_kinds=self.COMPONENT_KIND_TO_UIELEMENT_KIND,
            canvas=canvas,
            toolbar=toolbar,
            name=name,
            height=height,
            is_visible=is_visible,
            **kwargs,
        )

        subscribe(
            self,
            Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_CREATE_CHILD,
            self.on_create_unit_below_button,
        )
        subscribe(
            self,
            Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_INCREASE,
            lambda: self.on_change_level_button(IncreaseOrDecrease.INCREASE),
        )
        subscribe(
            self,
            Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_DECREASE,
            lambda: self.on_change_level_button(IncreaseOrDecrease.DECREASE),
        )
        subscribe(
            self, Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_GROUP, self.on_group_button
        )
        subscribe(
            self, Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_MERGE, self.on_merge_button
        )
        subscribe(
            self,
            Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT,
            self.on_paste_unit_button,
        )
        subscribe(
            self,
            Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT_WITH_CHILDREN,
            self.on_paste_unit_with_children_button,
        )
        subscribe(
            self, Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_DELETE, self.on_delete_button
        )
        subscribe(self, Event.INSPECTOR_WINDOW_OPENED, self.on_inspector_window_opened)

        self.collection = timeline_ui_collection

        self._name = name

        self.timeline = None

        self.right_clicked_element = None

    def get_timeline_height(self):
        return self.height

    def rearrange_canvas_drawings(self):
        for element in self.element_manager.get_all_elements():
            if not element.tl_component.parent and element.tl_component.children:
                self.rearrange_descendants_drawings_stacking_order(element)

    def rearrange_descendants_drawings_stacking_order(self, element: HierarchyUI):
        logger.debug(f"Rearranging descendants of {element}...")

        def get_element_and_descendants(parent: HierarchyUI):
            is_in_branch = (
                lambda e: e.tl_component.start >= parent.tl_component.start
                and e.tl_component.end <= parent.tl_component.end
            )
            elements_in_branch = self.element_manager.get_elements_by_condition(
                is_in_branch, kind=UIElementKind.HIERARCHY_TKUI
            )
            return elements_in_branch

        def get_drawings_to_arrange(elements: set[HierarchyUI]):
            _drawings_to_lower = set()
            for element in elements:
                _drawings_to_lower.add(element.rect_id)
                _drawings_to_lower.add(element.label_id)
                _drawings_to_lower.add(element.comments_ind_id)

            return _drawings_to_lower

        def get_lowest_in_stacking_order(ids: set, canvas: tk.Canvas) -> int:
            ids_in_order = [id_ for id_ in canvas.find_all() if id_ in ids]
            return ids_in_order[0]

        element_and_descendants = get_element_and_descendants(element)
        logger.debug(f"Element and descendants are: {element_and_descendants}")
        element_and_descendants_levels = sorted(
            {e.level for e in element_and_descendants}, reverse=True
        )
        logger.debug(
            f"Element and descendants span levels: {element_and_descendants_levels}"
        )

        for level in element_and_descendants_levels[:-1]:
            logger.debug(f"Rearranging level {level}")
            elements_in_level = {e for e in element_and_descendants if e.level == level}
            logger.debug(f"Elements in level are: {elements_in_level}")

            lowest_drawing_in_lower_elements = get_lowest_in_stacking_order(
                get_drawings_to_arrange(
                    {e for e in element_and_descendants if e.level < level}
                ),
                self.canvas,
            )

            for element in elements_in_level:
                logger.debug(
                    f"Lowering drawings '{element.canvas_drawings_ids}' of element '{element}'"
                )
                self.canvas.tag_lower(element.rect_id, lowest_drawing_in_lower_elements)
                self.canvas.tag_lower(
                    element.label_id, lowest_drawing_in_lower_elements
                )
                self.canvas.tag_lower(
                    element.comments_ind_id, lowest_drawing_in_lower_elements
                )

    def get_markerid_at_x(self, x: float):
        starts_or_ends_at_time = lambda u: u.start_x == x or u.end_x == x
        element = self.element_manager.get_element_by_condition(
            starts_or_ends_at_time, UIElementKind.HIERARCHY_TKUI
        )

        if not element:
            return

        # noinspection PyUnresolvedReferences
        if element.start_x == x:
            # noinspection PyUnresolvedReferences
            return element.start_marker
        elif element.end_x == x:
            # noinspection PyUnresolvedReferences
            return element.end_marker
        else:
            raise ValueError(
                "Can't get marker: markers in found element do not match desired x."
            )

    def get_units_using_marker(self, marker_id: int) -> list[int]:
        logger.debug(f"Getting units using marker '{marker_id}'...")
        id_as_start_or_end_marker = (
            lambda e: e.start_marker == marker_id or e.end_marker == marker_id
        )
        units_using_marker = self.element_manager.get_elements_by_condition(
            id_as_start_or_end_marker, kind=UIElementKind.ANY
        )
        logger.debug(f"Got units {units_using_marker}.")
        return units_using_marker

    @staticmethod
    def _swap_components_with_uis_in_relation(
        relation: ParentChildRelation,
    ) -> ParentChildRelation:

        return ParentChildRelation(
            parent=relation[0].ui, children=[child.ui for child in relation[1]]
        )

    def update_parent_child_relation(self, relation: ParentChildRelation) -> None:
        def get_lowest_in_stacking_order(ids: list, canvas: tk.Canvas) -> int:
            ids_in_order = [id_ for id_ in canvas.find_all() if id_ in ids]
            return ids_in_order[0]

        logging.debug(
            f"Arranging elements in {self} to parent/child relation '{relation}'"
        )

        ui_relation = self._swap_components_with_uis_in_relation(relation)
        parent_ui, children_uis = ui_relation

        if not parent_ui or not children_uis:
            logger.debug(f"No parent or children in relation. Nothing to do.")
            return

        children_canvas_drawings_ids = (
            self.element_manager.get_canvas_drawings_ids_from_elements(children_uis)
        )

        lowest_child_drawing_id = get_lowest_in_stacking_order(
            children_canvas_drawings_ids, self.canvas
        )

        # lower parents canvas drawings
        self.canvas.tag_lower(parent_ui.rect_id, lowest_child_drawing_id)
        self.canvas.tag_lower(parent_ui.label_id, lowest_child_drawing_id)
        self.canvas.tag_lower(parent_ui.comments_ind_id, lowest_child_drawing_id)

    def on_create_unit_below_button(self):
        selected_elements = self._log_and_get_elements_for_button_processing(
            "create button below"
        )
        if not selected_elements:
            return

        selected_tl_components = [e.tl_component for e in selected_elements]
        for component in selected_tl_components:
            logging.debug(f"Requesting timeline to create unit below {component}.")
            self.timeline.create_unit_below(component)

        logging.debug(f"Processed create unit below button.")

    def on_change_level_button(self, increase_or_decrease: IncreaseOrDecrease):
        selected_elements = self._log_and_get_elements_for_button_processing(
            increase_or_decrease.name.lower()
        )
        if not selected_elements:
            return

        if not selected_elements:
            logging.debug(f"No element is selected. Nothing to do.")

        selected_tl_components = [e.tl_component for e in selected_elements]
        for component in selected_tl_components:
            logging.debug(
                f"Requesting timeline to {increase_or_decrease.name.lower()} level of {component}."
            )
            self.timeline.change_level_by_amount(increase_or_decrease.value, component)

        logging.debug(f"Processed {increase_or_decrease.name.lower()} level button.")

    def on_group_button(self):
        selected_elements = self._log_and_get_elements_for_button_processing("group")
        if not selected_elements:
            return

        selected_components = [e.tl_component for e in selected_elements]
        logging.debug(f"Requesting timeline to group {selected_components}.")
        self.timeline.group(selected_components)

        logging.debug(f"Processed group level button.")

    def on_split_button(self):
        logging.debug(f"Processing split button press...")
        split_time = self.timeline.get_current_playback_time()
        logging.debug(f"Requesting timeline to split at time={split_time}.")
        self.timeline.split(split_time)
        logging.debug(f"Processed split button press.")

    def on_merge_button(self):
        selected_elements = self._log_and_get_elements_for_button_processing("merge")
        if not selected_elements:
            return

        selected_components = [e.tl_component for e in selected_elements]
        logging.debug(f"Requesting timeline to merge {selected_components}.")
        self.timeline.merge(selected_components)

    def on_paste_unit_button(self) -> None:
        selected_elements = self._log_and_get_elements_for_button_processing("paste")
        if not selected_elements:
            return

        self.paste_single_into_selected_elements(
            self.collection.get_elements_for_pasting()
        )

    def on_paste_unit_with_children_button(self) -> None:
        selected_elements = self._log_and_get_elements_for_button_processing(
            "paste with children"
        )
        if not selected_elements:
            return

        self.paste_with_children_into_selected_elements(
            self.collection.get_elements_for_pasting()
        )

    def on_delete_button(self):
        self.delete_selected_elements()

    def _deselect_all_but_last(self):
        ordered_selected_elements = sorted(
            self.element_manager.get_selected_elements(),
            key=lambda x: x.tl_component.start,
        )
        if len(ordered_selected_elements) > 1:
            for element in ordered_selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def on_up_down_arrow_press(self, direction: UpOrDown):

        if not self.has_selected_elements:
            logger.debug(
                f"User pressed {direction.value} arrow but no elements were selected."
            )
            return

        self._deselect_all_but_last()

        selected_element = self.element_manager.get_selected_elements()[0]

        element_to_select = None
        if direction == UpOrDown.UP and selected_element.tl_component.parent:
            element_to_select = selected_element.tl_component.parent.ui
        elif direction == UpOrDown.DOWN and selected_element.tl_component.children:
            element_to_select = sorted(
                selected_element.tl_component.children, key=lambda x: x.start
            )[0].ui

        if element_to_select:
            self.element_manager.deselect_element(selected_element)
            self.select_element(element_to_select)
        elif direction == UpOrDown.UP:
            logger.debug(f"Selected element has no parent. Can't select up.")
        else:
            logger.debug(f"Selected element has no children. Can't select down.")

    def on_side_arrow_press(self, side: Side):
        def _get_next_element_in_same_level(elm):
            is_later_at_same_level = (
                lambda h: h.tl_component.start > elm.tl_component.start
                and h.tl_component.level == elm.tl_component.level
            )
            later_elements = self.element_manager.get_elements_by_condition(
                is_later_at_same_level, UIElementKind.HIERARCHY_TKUI
            )
            if later_elements:
                return sorted(later_elements, key=lambda x: x.tl_component.start)[0]
            else:
                return None

        def _get_previous_element_in_same_level(elm):
            is_earlier_at_same_level = (
                lambda h: h.tl_component.start < elm.tl_component.start
                and h.tl_component.level == elm.tl_component.level
            )
            earlier_elements = self.element_manager.get_elements_by_condition(
                is_earlier_at_same_level, UIElementKind.HIERARCHY_TKUI
            )
            if earlier_elements:
                return sorted(earlier_elements, key=lambda x: x.tl_component.start)[-1]
            else:
                return None

        if not self.has_selected_elements:
            logger.debug(f"User pressed {side} arrow but no elements are selected in {self}.")
            return

        self._deselect_all_but_last()

        selected_element = self.element_manager.get_selected_elements()[0]
        if side == Side.RIGHT:
            element_to_select = _get_next_element_in_same_level(selected_element)
        elif side == Side.LEFT:
            element_to_select = _get_previous_element_in_same_level(selected_element)
        else:
            raise ValueError(f"Invalid side '{side}'.")

        if element_to_select:
            self.deselect_element(selected_element)
            self.select_element(element_to_select)
        elif side == Side.RIGHT:
            logger.debug(
                f"Selected element is last element in level. Can't select next."
            )
        else:
            logger.debug(
                f"Selected element is first element in level. Can't select previous."
            )

    def on_right_click_menu_option_click(self, option: RightClickOption):
        option_to_callback = {
            RightClickOption.CHANGE_TIMELINE_HEIGHT: self.right_click_menu_change_timeline_height,
            RightClickOption.CHANGE_TIMELINE_NAME: self.right_click_menu_change_timeline_name,
            RightClickOption.INCREASE_LEVEL: self.right_click_menu_increase_level,
            RightClickOption.DECREASE_LEVEL: self.right_click_menu_decrease_level,
            RightClickOption.CREATE_UNIT_BELOW: self.right_click_menu_decrease_level,
            RightClickOption.EDIT: self.right_click_menu_edit,
            RightClickOption.CHANGE_COLOR: self.right_click_menu_change_color,
            RightClickOption.RESET_COLOR: self.right_click_menu_reset_color,
            RightClickOption.COPY: self.right_click_menu_copy,
            RightClickOption.PASTE: self.right_click_menu_paste,
            RightClickOption.PASTE_WITH_ALL_ATTRIBUTES: self.right_click_menu_paste_with_all_attributes,
            RightClickOption.DELETE: self.right_click_menu_delete,
            RightClickOption.EXPORT_TO_AUDIO: self.right_click_menu_export_to_audio,
        }
        option_to_callback[option]()

    def right_click_menu_increase_level(self) -> None:
        self.timeline.change_level_by_amount(1, self.right_clicked_element.tl_component)

    def right_click_menu_decrease_level(self) -> None:
        self.timeline.change_level_by_amount(
            -1, self.right_clicked_element.tl_component
        )

    def right_click_menu_edit(self) -> None:
        self.deselect_all_elements()
        self.select_element(self.right_clicked_element)
        events.post(Event.UI_REQUEST_WINDOW_INSPECTOR)

    def right_click_menu_change_color(self) -> None:
        if color := tilia.ui.common.ask_for_color(self.right_clicked_element.color):
            self.right_clicked_element.color = color

    def right_click_menu_reset_color(self) -> None:
        self.right_clicked_element.reset_color()

    def right_click_menu_copy(self) -> None:
        events.post(
            Event.TIMELINE_COMPONENT_COPIED,
            self.get_copy_data_from_hierarchy_uis([self.right_clicked_element]),
        )

    def right_click_menu_paste(self) -> None:
        self.element_manager.deselect_all_elements()
        self.element_manager.select_element(self.right_clicked_element)
        self.paste_single_into_selected_elements(
            self.collection.get_elements_for_pasting()
        )

    def right_click_menu_paste_with_all_attributes(self) -> None:
        self.element_manager.deselect_all_elements()
        self.element_manager.select_element(self.right_clicked_element)
        self.paste_with_children_into_selected_elements(
            self.collection.get_elements_for_pasting()
        )

    def right_click_menu_delete(self) -> None:
        self.timeline.on_request_to_delete_components(
            [self.right_clicked_element.tl_component]
        )

    def right_click_menu_export_to_audio(self) -> None:
        events.post(
            Event.REQUEST_EXPORT_AUDIO_SEGMENT,
            segment_name=self.right_clicked_element.full_name,
            start_time=self.right_clicked_element.tl_component.start,
            end_time=self.right_clicked_element.tl_component.end,
        )

    def get_previous_marker_x_by_x(self, x: int) -> None | int:
        all_marker_xs = self.get_all_elements_boundaries()
        earlier_marker_xs = [x_ for x_ in all_marker_xs if x_ < x]

        if earlier_marker_xs:
            return max(earlier_marker_xs)
        else:
            return None

    def get_next_marker_x_by_x(self, x: int) -> None | int:
        all_marker_xs = self.get_all_elements_boundaries()
        later_marker_xs = [x_ for x_ in all_marker_xs if x_ > x]

        if later_marker_xs:
            return min(later_marker_xs)
        else:
            return None

    def get_all_elements_boundaries(self) -> set[int]:
        """Returns all the start_x and end_x values for hierarchy ui's in timeline."""
        earlier_boundaries = self.element_manager.get_existing_values_for_attribute(
            "start_x", kind=UIElementKind.HIERARCHY_TKUI
        )
        later_boundaries = self.element_manager.get_existing_values_for_attribute(
            "end_x", kind=UIElementKind.HIERARCHY_TKUI
        )

        return earlier_boundaries.union(later_boundaries)

    def on_inspector_window_opened(self):
        for element in self.element_manager.get_selected_elements():
            logger.debug(
                f"Notifying inspector of previsously selected elements on {self}..."
            )
            # noinspection PyTypeChecker
            self.post_inspectable_selected_event(element)

    def paste_single_into_selected_elements(self, paste_data: list[dict]):

        for element in self.element_manager.get_selected_elements():
            self.deselect_element(element)
            paste_into_element(element, paste_data[0])
            self.select_element(element)

        events.post(Event.REQUEST_RECORD_STATE, StateAction.PASTE)

    def validate_copy(self, elements: list[Copyable]) -> None:
        if len(elements) > 1:
            events.post(
                Event.REQUEST_DISPLAY_ERROR,
                title="Copy error",
                message="Can't copy more than one hierarchy at once.",
            )
            raise CopyError(f"Can't copy more than one hierarchy at once.")

    def paste_with_children_into_selected_elements(self, paste_data: list[dict]):
        def validate_paste_with_children(
            paste_data_: list[dict], elements_to_receive_paste: list[HierarchyUI]
        ) -> None:
            for element in elements_to_receive_paste:
                if len(paste_data_) > 1:
                    raise PasteError(
                        "Can't paste more than one Hierarchy at the same time."
                    )
                elif element.level != int(
                    paste_data_[0]["support_by_component_value"]["level"]
                ):
                    raise PasteError(
                        "Can't paste all of unit's attributes (including children) into unit of different level."
                    )

        def get_descendants(parent: HierarchyUI):
            is_in_branch = (
                lambda e: e.tl_component.start >= parent.tl_component.start
                and e.tl_component.end <= parent.tl_component.end
            )
            elements_in_branch = self.element_manager.get_elements_by_condition(
                is_in_branch, kind=UIElementKind.HIERARCHY_TKUI
            )
            elements_in_branch.remove(parent)
            return elements_in_branch

        def paste_with_children_into_element(paste_data_: dict, element_: HierarchyUI):
            logger.debug(
                f"Pasting with children into element '{element_}' with paste data = {paste_data_}'"
            )
            tilia.ui.timelines.copy_paste.paste_into_element(element_, paste_data_)

            if "children" in paste_data_:
                children_of_element = []
                for child_paste_data in paste_data_["children"]:
                    child_component = create_child_from_paste_data(
                        element_,
                        paste_data_["support_by_component_value"]["start"],
                        paste_data_["support_by_component_value"]["end"],
                        child_paste_data,
                    )

                    if child_paste_data.get("children", None):
                        paste_with_children_into_element(
                            child_paste_data, child_component.ui
                        )

                    children_of_element.append(child_component)

                parent_child_relation = ParentChildRelation(
                    parent=element_.tl_component, children=children_of_element
                )
                self._swap_components_with_uis_in_relation(parent_child_relation)
                process_parent_child_relation(parent_child_relation)

        def create_child_from_paste_data(
            new_parent: HierarchyUI,
            previous_parent_start: float,
            previous_parent_end: float,
            child_paste_data_: dict,
        ):
            logger.debug(
                f"Creating child for '{new_parent}' from paste data '{child_paste_data_}'"
            )
            new_parent_length = (
                new_parent.tl_component.end - new_parent.tl_component.start
            )
            prev_parent_length = previous_parent_end - previous_parent_start
            scale_factor = new_parent_length / prev_parent_length
            # logger.debug(f"Scale factor between previous and new parents is '{scale_factor}'")

            relative_child_start = (
                child_paste_data_["support_by_component_value"]["start"]
                - previous_parent_start
            )
            # logger.debug(f"Child start relative to previous parent is '{relative_child_start}'")
            new_child_start = (
                relative_child_start * scale_factor
            ) + new_parent.tl_component.start
            logger.debug(f"New child start is '{new_child_start}'")

            relative_child_end = (
                child_paste_data_["support_by_component_value"]["end"]
                - previous_parent_end
            )
            # logger.debug(f"Child end relative to previous parent is '{relative_child_end}'")
            new_child_end = (
                relative_child_end * scale_factor
            ) + new_parent.tl_component.end
            logger.debug(f"New child end is '{new_child_end}'")

            return self.timeline.create_timeline_component(
                kind=ComponentKind.HIERARCHY,
                start=new_child_start,
                end=new_child_end,
                level=child_paste_data_["support_by_component_value"]["level"],
                **child_paste_data_["by_element_value"],
                **child_paste_data_["by_component_value"],
            )

        logger.debug(f"Pasting with children into selected elements...")
        selected_elements = self.element_manager.get_selected_elements()
        logger.debug(f"Selected elements are: {selected_elements}")

        validate_paste_with_children(paste_data, selected_elements)

        for element in selected_elements.copy():
            self.deselect_element(element)
            logger.debug(f"Deleting previous descendants of '{element}'")
            # delete previous descendants
            descendants = get_descendants(element)
            for descendant in descendants:
                self.timeline.on_request_to_delete_components(
                    [descendant.tl_component], record=False
                )

            # create children according to paste data
            paste_with_children_into_element(paste_data[0], element)
            self.select_element(element)

        events.post(Event.REQUEST_RECORD_STATE, StateAction.PASTE)

    def get_copy_data_from_selected_elements(self):
        selected_elements = self.element_manager.get_selected_elements()

        self.validate_copy(selected_elements)

        return self.get_copy_data_from_hierarchy_uis(selected_elements)

    def get_copy_data_from_hierarchy_uis(self, hierarchy_uis: list[HierarchyUI]):

        copy_data = []
        for ui in hierarchy_uis:
            copy_data.append(self.get_copy_data_from_hierarchy_ui(ui))

        return copy_data

    def get_copy_data_from_hierarchy_ui(self, hierarchy_ui: HierarchyUI):
        ui_data = get_copy_data_from_element(
            hierarchy_ui, HierarchyUI.DEFAULT_COPY_ATTRIBUTES
        )

        if hierarchy_ui.tl_component.children:
            ui_data["children"] = [
                self.get_copy_data_from_hierarchy_ui(child.ui)
                for child in hierarchy_ui.tl_component.children
            ]

        return ui_data

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name}|{id(self)})"
