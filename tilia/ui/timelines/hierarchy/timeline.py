from __future__ import annotations
import logging
import tkinter as tk

from tilia import settings
from tilia.timelines.hierarchy.common import (
    update_component_genealogy,
)
from tilia.ui.timelines.timeline import (
    TimelineUI,
    RightClickOption,
)
from tilia.ui.timelines.hierarchy import HierarchyTimelineToolbar, HierarchyUI
from tilia.ui.timelines.copy_paste import (
    CopyError,
    PasteError,
    Copyable,
    get_copy_data_from_element,
)
import tilia.ui.timelines.copy_paste
from tilia.ui.timelines.copy_paste import paste_into_element
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import Post, post, get, Get
from tilia.enums import Side, UpOrDown
from tilia.timelines.timeline_kinds import TimelineKind

logger = logging.getLogger(__name__)


class HierarchyTimelineUI(TimelineUI):
    DEFAULT_HEIGHT = settings.get("hierarchy_timeline", "default_height")
    TOOLBAR_CLASS = HierarchyTimelineToolbar
    ELEMENT_CLASS = HierarchyUI
    TIMELINE_KIND = TimelineKind.HIERARCHY_TIMELINE

    def _setup_user_actions_to_callbacks(self):
        self.action_to_callback = {
            "create_child": self.create_child,
            "increase_level": self.increase_level,
            "decrease_level": self.decrease_level,
            "group": self.group,
            "merge": self.merge,
            "paste": self.paste,
            "paste_with_children": self.paste_with_children,
            "delete": self.delete_selected_elements,
            "split": self.split,
        }

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
                is_in_branch
            )
            return elements_in_branch

        def get_drawings_to_arrange(elements: set[HierarchyUI]):
            _drawings_to_lower = set()
            for element in elements:
                _drawings_to_lower.add(element.body_id)
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
                    f"Lowering drawings '{element.canvas_drawings_ids}' of element"
                    f" '{element}'"
                )
                self.canvas.tag_lower(element.body_id, lowest_drawing_in_lower_elements)
                self.canvas.tag_lower(
                    element.label_id, lowest_drawing_in_lower_elements
                )
                self.canvas.tag_lower(
                    element.comments_ind_id, lowest_drawing_in_lower_elements
                )

    def get_markerid_at_x(self, x: float):
        def starts_or_ends_at_time(ui: HierarchyUI) -> bool:
            return ui.start_x == x or ui.end_x == x

        element = self.element_manager.get_element_by_condition(starts_or_ends_at_time)

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
            id_as_start_or_end_marker
        )
        logger.debug(f"Got units {units_using_marker}.")
        return units_using_marker

    def update_genealogy(self, parent_id: str, children_ids: list[str]) -> None:
        def get_lowest_in_stacking_order(ids: list, canvas: tk.Canvas) -> int:
            ids_in_order = [id_ for id_ in canvas.find_all() if id_ in ids]
            return ids_in_order[0]

        logger.debug(
            f"Arranging elements in {self} to parent/child relation of ids"
            f" '{parent_id, children_ids}'"
        )

        parent_ui = self.get_element(parent_id)
        children_uis = [self.get_element(id) for id in children_ids]

        if not parent_ui or not children_uis:
            logger.debug("No parent or children in relation. Nothing to do.")
            return

        children_canvas_drawings_ids = (
            self.element_manager.get_canvas_drawings_ids_from_elements(children_uis)
        )

        lowest_child_drawing_id = get_lowest_in_stacking_order(
            children_canvas_drawings_ids, self.canvas
        )

        # lower parents canvas drawings
        self.canvas.tag_lower(parent_ui.body_id, lowest_child_drawing_id)
        self.canvas.tag_lower(parent_ui.label_id, lowest_child_drawing_id)
        self.canvas.tag_lower(parent_ui.comments_ind_id, lowest_child_drawing_id)

    def create_child(self):
        if not self.selected_elements:
            return

        for component in self.selected_components:
            logger.debug(f"Requesting timeline to create unit below {component}.")
            self.timeline.create_unit_below(component)

        logger.debug("Processed create unit below button.")

    def increase_level(self):
        self.change_level(1)

    def decrease_level(self):
        self.change_level(-1)

    def change_level(self, amount: int):
        if not self.selected_elements:
            return

        logger.debug(
            f"Requesting timeline to change level of selected elements by {amount}."
        )

        self.timeline.change_level(amount, self.selected_components)

        logger.debug("Processed change level button.")

    def group(self):
        if not self.selected_elements:
            return

        logger.debug(f"Requesting timeline to group {self.selected_components}.")
        self.timeline.group(self.selected_components)

        logger.debug("Processed group level button.")

    def split(self):
        logger.debug("Processing split button press...")
        split_time = get(Get.CURRENT_PLAYBACK_TIME)
        logger.debug(f"Requesting timeline to split at time={split_time}.")
        self.timeline.split(split_time)
        logger.debug("Processed split button press.")

    def merge(self):
        if not self.selected_elements:
            return

        logger.debug(f"Requesting timeline to merge {self.selected_components}.")
        self.timeline.merge(self.selected_components)

    def paste(self) -> None:
        if not self.selected_elements:
            return

        self.paste_single_into_selected_elements(get(Get.CLIPBOARD)["components"])

    def paste_with_children(self) -> None:
        if not self.selected_elements:
            return

        self.paste_with_children_into_selected_elements(
            get(Get.CLIPBOARD)["components"]
        )

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
            element_to_select = self.get_component_ui(
                selected_element.tl_component.parent
            )
        elif direction == UpOrDown.DOWN and selected_element.tl_component.children:
            component_to_select = sorted(
                selected_element.tl_component.children, key=lambda x: x.start
            )[0]
            element_to_select = self.get_component_ui(component_to_select)

        if element_to_select:
            self.element_manager.deselect_element(selected_element)
            self.select_element(element_to_select)
        elif direction == UpOrDown.UP:
            logger.debug("Selected element has no parent. Can't select up.")
        else:
            logger.debug("Selected element has no children. Can't select down.")

    def on_side_arrow_press(self, side: Side):
        def _get_next_element_in_same_level(elm):
            is_later_at_same_level = (
                lambda h: h.tl_component.start > elm.tl_component.start
                and h.tl_component.level == elm.tl_component.level
            )
            later_elements = self.element_manager.get_elements_by_condition(
                is_later_at_same_level
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
                is_earlier_at_same_level
            )
            if earlier_elements:
                return sorted(earlier_elements, key=lambda x: x.tl_component.start)[-1]
            else:
                return None

        if not self.has_selected_elements:
            logger.debug(
                f"User pressed {side} arrow but no elements are selected in {self}."
            )
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
                "Selected element is last element in level. Can't select next."
            )
        else:
            logger.debug(
                "Selected element is first element in level. Can't select previous."
            )

    def on_right_click_menu_option_click(self, option: RightClickOption):
        option_to_callback = {
            RightClickOption.CHANGE_TIMELINE_HEIGHT: (
                self.right_click_menu_change_timeline_height
            ),
            RightClickOption.CHANGE_TIMELINE_NAME: (
                self.right_click_menu_change_timeline_name
            ),
            RightClickOption.INCREASE_LEVEL: self.right_click_menu_increase_level,
            RightClickOption.DECREASE_LEVEL: self.right_click_menu_decrease_level,
            RightClickOption.ADD_PRE_START: self.right_click_menu_add_pre_start,
            RightClickOption.ADD_POST_END: self.right_click_menu_add_post_end,
            RightClickOption.CREATE_UNIT_BELOW: self.right_click_menu_decrease_level,
            RightClickOption.EDIT: self.right_click_menu_edit,
            RightClickOption.CHANGE_COLOR: self.right_click_menu_change_color,
            RightClickOption.RESET_COLOR: self.right_click_menu_reset_color,
            RightClickOption.COPY: self.right_click_menu_copy,
            RightClickOption.PASTE: self.right_click_menu_paste,
            RightClickOption.PASTE_WITH_ALL_ATTRIBUTES: (
                self.right_click_menu_paste_with_all_attributes
            ),
            RightClickOption.DELETE: self.right_click_menu_delete,
            RightClickOption.EXPORT_TO_AUDIO: self.right_click_menu_export_to_audio,
        }
        option_to_callback[option]()

    def right_click_menu_increase_level(self) -> None:
        self.timeline.change_level(1, [self.right_clicked_element.tl_component])

    def right_click_menu_decrease_level(self) -> None:
        self.timeline.change_level(-1, [self.right_clicked_element.tl_component])

    def right_click_menu_add_pre_start(self) -> None:
        component = self.right_clicked_element.tl_component
        pre_start_length = get(
            Get.FLOAT_FROM_USER, "Add pre-start", "How many seconds before start?"
        )

        if pre_start_length is None:
            return
        component.pre_start = component.start - pre_start_length
        self.select_element(self.right_clicked_element)
        self.right_clicked_element.update_pre_start_visibility()

    def right_click_menu_add_post_end(self) -> None:
        component = self.right_clicked_element.tl_component
        post_end_length = get(
            Get.FLOAT_FROM_USER, "Add post-end", "How many seconds after end?"
        )
        if post_end_length is None:
            return
        component.post_end = component.end + post_end_length
        self.select_element(self.right_clicked_element)
        self.right_clicked_element.update_post_end_visibility()

    def right_click_menu_edit(self) -> None:
        self.deselect_all_elements()
        self.select_element(self.right_clicked_element)
        post(Post.UI_REQUEST_WINDOW_INSPECTOR)

    def right_click_menu_change_color(self) -> None:
        if color := get(Get.COLOR_FROM_USER, self.right_clicked_element.color):
            self.right_clicked_element.color = color

    def right_click_menu_reset_color(self) -> None:
        self.right_clicked_element.reset_color()

    def right_click_menu_copy(self) -> None:
        post(
            Post.TIMELINE_COMPONENT_COPIED,
            self.get_copy_data_from_hierarchy_uis([self.right_clicked_element]),
        )

    def right_click_menu_paste(self) -> None:
        self.element_manager.deselect_all_elements()
        self.element_manager.select_element(self.right_clicked_element)
        self.paste_single_into_selected_elements(get(Get.CLIPBOARD))

    def right_click_menu_paste_with_all_attributes(self) -> None:
        self.element_manager.deselect_all_elements()
        self.element_manager.select_element(self.right_clicked_element)
        self.paste_with_children_into_selected_elements(get(Get.CLIPBOARD))

    def right_click_menu_delete(self) -> None:
        self.timeline.on_request_to_delete_components(
            [self.right_clicked_element.tl_component]
        )

    def right_click_menu_export_to_audio(self) -> None:
        post(
            Post.REQUEST_EXPORT_AUDIO,
            segment_name=self.right_clicked_element.full_name,
            start_time=self.right_clicked_element.tl_component.start,
            end_time=self.right_clicked_element.tl_component.end,
        )

    def get_previous_marker_x_by_x(self, x: float) -> None | int:
        all_marker_xs = self.get_all_elements_boundaries()
        earlier_marker_xs = [x_ for x_ in all_marker_xs if x_ < x]

        if earlier_marker_xs:
            return max(earlier_marker_xs)
        else:
            return None

    def get_next_marker_x_by_x(self, x: float) -> None | int:
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
            element.update_label()
            element.update_comments_indicator_text()
            self.select_element(element)

    def validate_copy(self, elements: list[Copyable]) -> None:
        if len(elements) > 1:
            post(
                Post.REQUEST_DISPLAY_ERROR,
                title="Copy error",
                message="Can't copy more than one hierarchy at once.",
            )
            raise CopyError("Can't copy more than one hierarchy at once.")

    def _create_child_from_paste_data(
        self,
        new_parent: HierarchyUI,
        prev_parent_start: float,
        prev_parent_end: float,
        child_pastedata_: dict,
    ):
        logger.debug(
            f"Creating child for '{new_parent}' from paste data '{child_pastedata_}'"
        )

        new_parent_length = new_parent.tl_component.end - new_parent.tl_component.start

        prev_parent_length = prev_parent_end - prev_parent_start
        scale_factor = new_parent_length / prev_parent_length

        relative_child_start = (
            child_pastedata_["support_by_component_value"]["start"] - prev_parent_start
        )

        new_child_start = (
            relative_child_start * scale_factor
        ) + new_parent.tl_component.start
        logger.debug(f"New child start is '{new_child_start}'")

        relative_child_end = (
            child_pastedata_["support_by_component_value"]["end"] - prev_parent_end
        )

        new_child_end = (
            relative_child_end * scale_factor
        ) + new_parent.tl_component.end
        logger.debug(f"New child end is '{new_child_end}'")

        return self.timeline.create_timeline_component(
            kind=ComponentKind.HIERARCHY,
            start=new_child_start,
            end=new_child_end,
            level=child_pastedata_["support_by_component_value"]["level"],
            **child_pastedata_["by_element_value"],
            **child_pastedata_["by_component_value"],
        )

    def _paste_with_children_into_element(self, paste_data: dict, element: HierarchyUI):
        logger.debug(
            f"Pasting with children into element '{element}' with paste data ="
            f" {paste_data}'"
        )
        tilia.ui.timelines.copy_paste.paste_into_element(element, paste_data)
        element.update_label()
        element.update_comments_indicator_text()

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
                    self._paste_with_children_into_element(
                        child_paste_data, self.get_component_ui(child_component)
                    )

                children_of_element.append(child_component)

            update_component_genealogy(element.tl_component, children_of_element)

    def paste_with_children_into_selected_elements(self, paste_data: list[dict]):
        def validate_paste_with_children() -> None:
            if len(paste_data) > 1:
                raise PasteError("Can't paste more than one Hierarchy at once.")

            PASTE_ERROR_LVL_PROMPT = (
                "Can't paste all of unit's attributes (including children)"
                " into unit of different level."
            )

            for element in self.selected_elements:
                if element.level != int(
                    paste_data[0]["support_by_component_value"]["level"]
                ):
                    post(
                        Post.REQUEST_DISPLAY_ERROR,
                        title="Paste error",
                        message=PASTE_ERROR_LVL_PROMPT,
                    )
                    raise PasteError(PASTE_ERROR_LVL_PROMPT)

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

        logger.debug("Pasting with children into selected elements...")
        logger.debug(f"Selected elements are: {self.selected_elements}")

        validate_paste_with_children()

        for element in self.selected_elements.copy():
            self.deselect_element(element)
            logger.debug(f"Deleting previous descendants of '{element}'")
            # delete previous descendants
            descendants = get_descendants(element)
            for descendant in descendants:
                self.timeline.on_request_to_delete_components(
                    [descendant.tl_component], record=False
                )

            # create children according to paste data
            self._paste_with_children_into_element(paste_data[0], element)
            self.select_element(element)

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

        if hierarchy_ui.children:
            ui_data["children"] = [
                self.get_copy_data_from_hierarchy_ui(self.id_to_element[child.id])
                for child in hierarchy_ui.children
            ]

        return ui_data

    def on_hierarchy_level_changed(
        self, component_id: str, prev_level: int, new_level: int
    ):
        self.id_to_element[component_id].update_color(prev_level, new_level)

    def on_hierarchy_position_changed(self, component_id: str):
        self.id_to_element[component_id].update_position()
