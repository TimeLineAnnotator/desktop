import tilia.ui.strings
import tilia.ui.timelines.copy_paste
from tilia.requests import Get, Post, get, listen, post
from tilia.settings import settings
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
    with_elements,
)
from tilia.ui.timelines.collection.collection import TimelineSelector, TimelineUIs
from tilia.ui.timelines.copy_paste import get_copy_data_from_element, paste_into_element
from tilia.ui.timelines.hierarchy import HierarchyTimelineToolbar, HierarchyUI
from tilia.ui.timelines.hierarchy.copy_paste import (
    _display_copy_error,
    _display_paste_complete_error,
    _validate_copy_cardinality,
    _validate_paste_complete_cardinality,
    _validate_paste_complete_level,
)
from tilia.ui.timelines.hierarchy.handles import HierarchyBodyHandle
from tilia.ui.timelines.hierarchy.key_press_manager import (
    HierarchyTimelineUIKeyPressManager,
)


class HierarchyTimelineUI(TimelineUI):
    TOOLBAR_CLASS = HierarchyTimelineToolbar
    ELEMENT_CLASS = HierarchyUI
    TIMELINE_KIND = TimelineKind.HIERARCHY_TIMELINE
    ACCEPTS_HORIZONTAL_ARROWS = True
    ACCEPTS_VERTICAL_ARROWS = True
    MIN_MARGIN = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listen(
            self,
            Post.SETTINGS_UPDATED,
            self.on_settings_updated,
        )

    @classmethod
    def register_commands(cls, collection: TimelineUIs):
        args = [
            ("add_post_end", "Add post-end", "", ""),
            ("add_pre_start", "Add pre-start", "", ""),
            (
                "create_child",
                "Create child",
                "c",
                "hierarchy-create-child",
            ),
            (
                "decrease_level",
                "Move down a level",
                "Ctrl+Down",
                "hierarchy-level-down",
            ),
            ("group", "Group", "g", "hierarchy-create-parent"),
            (
                "increase_level",
                "Move up a level",
                "Ctrl+Up",
                "hierarchy-level-up",
            ),
            ("merge", "Merge", "e", "hierarchy-merge"),
            (
                "split",
                "Split at current position",
                "s",
                "hierarchy-split",
            ),
            (
                "export_audio",
                "Export to audio",
                "",
                "",
            ),
        ]

        for name, text, shortcut, icon in args:
            selector = (
                TimelineSelector.SELECTED if name != "split" else TimelineSelector.FIRST
            )
            cls.register_timeline_command(
                collection,
                name,
                getattr(cls, "on_" + name),
                selector,
                text=text,
                shortcut=shortcut,
                icon=icon,
            )

    def on_settings_updated(self, updated_settings):
        if "hierarchy_timeline" in updated_settings:
            get(Get.TIMELINE_COLLECTION).set_timeline_data(
                self.id, "height", self.timeline.default_height
            )
            for hierarchy_ui in self:
                hierarchy_ui.update_position()
                hierarchy_ui.update_color()

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

        relative_child_start = child_pastedata_["context"]["start"] - prev_parent_start

        new_child_start = (
            relative_child_start * scale_factor
        ) + new_parent.tl_component.start

        relative_child_end = child_pastedata_["context"]["end"] - prev_parent_end

        new_child_end = (
            relative_child_end * scale_factor
        ) + new_parent.tl_component.end

        component, _ = self.timeline.create_component(
            kind=ComponentKind.HIERARCHY,
            start=new_child_start,
            end=new_child_end,
            level=child_pastedata_["context"]["level"],
            **child_pastedata_["values"],
        )

        return component

    def paste_with_children_into_element(self, paste_data: dict, element: HierarchyUI):
        tilia.ui.timelines.copy_paste.paste_into_element(element, paste_data)

        if "children" in paste_data:
            children_of_element = []
            for child_paste_data in paste_data["children"]:
                child_component = self._create_child_from_paste_data(
                    element,
                    paste_data["context"]["start"],
                    paste_data["context"]["end"],
                    child_paste_data,
                )

                if child_paste_data.get("children", None):
                    self.paste_with_children_into_element(
                        child_paste_data, self.get_component_ui(child_component)
                    )

                children_of_element.append(child_component)

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

    def get_max_hierarchy_height(self):
        max_level = max(
            self.timeline.component_manager.get_existing_values_for_attr(
                "level", ComponentKind.HIERARCHY
            )
        )
        return HierarchyUI.base_height() + (
            HierarchyUI.x_increment_per_lvl() * max_level
        )

    @with_elements
    def on_copy_element(self, elements: list[HierarchyUI]) -> bool:
        success, reason = _validate_copy_cardinality(elements)
        if not success:
            _display_copy_error(reason)

        component_data = [self.get_copy_data_from_hierarchy_ui(e) for e in elements]

        if not component_data:
            return False

        post(
            Post.TIMELINE_ELEMENT_COPY_DONE,
            {"components": component_data, "timeline_kind": self.timeline.KIND},
        )

        return True

    def on_paste_element_complete(self, clipboard_contents: dict) -> bool:
        copied_components = clipboard_contents["components"]
        if not copied_components or not self.has_selected_elements:
            return False

        success, reason = _validate_paste_complete_cardinality(copied_components)
        if not success:
            _display_paste_complete_error(reason)
            return False

        data = copied_components[0]
        for element in self.selected_elements:
            success, reason = _validate_paste_complete_level(element, data)
            if not success:
                _display_paste_complete_error(reason)
                return False

            while children := element.get_data("children"):
                self.timeline.delete_components(children)

            self.paste_with_children_into_element(data, element)

        return True

    def _adjust_timeline_height(self):
        max_height = self.get_max_hierarchy_height()
        if max_height > self.get_data("height") + self.MIN_MARGIN:
            get(Get.TIMELINE_COLLECTION).set_timeline_data(
                self.id, "height", max_height + self.MIN_MARGIN
            )

    @with_elements
    def on_increase_level(self, elements: list[HierarchyUI]) -> bool:
        if success := self.timeline.alter_levels(
            self.elements_to_components(list(reversed(elements))), 1
        ):
            self._adjust_timeline_height()
        return success

    @with_elements
    def on_decrease_level(self, elements: list[HierarchyUI]):
        return self.timeline.alter_levels(self.elements_to_components(elements), -1)

    @with_elements
    def on_group(self, elements: list[HierarchyUI]):
        if success := self.timeline.group(self.elements_to_components(elements)):
            self._adjust_timeline_height()
        return success

    def on_split(self, time: float | None = None):
        if time is None:
            time = get(Get.SELECTED_TIME)
        return self.timeline.split(time)

    @with_elements
    def on_merge(self, elements: list[HierarchyUI]):
        return self.timeline.merge(self.elements_to_components(elements))

    @with_elements
    def on_create_child(self, elements: list[HierarchyUI]):
        def _should_prompt_create_level_below() -> bool:
            return settings.get("hierarchy_timeline", "prompt_create_level_below")

        def _prompt_create_level_below() -> bool:
            return get(
                Get.FROM_USER_YES_OR_NO,
                tilia.ui.strings.PROMPT_CREATE_LEVEL_BELOW_TITLE,
                tilia.ui.strings.PROMPT_CREATE_LEVEL_BELOW_MESSAGE,
            )

        if any([e.get_data("level") == 1 for e in elements]):
            if not _should_prompt_create_level_below() or _prompt_create_level_below():
                self.on_increase_level(self.elements)
            else:
                return False

        return self.timeline.create_children(self.elements_to_components(elements))

    @with_elements
    def on_add_pre_start(self, elements: list[HierarchyUI]):
        accept, value = get(Get.FROM_USER_FLOAT, "Add pre-start", "Pre-start length")
        if not accept:
            return False

        self._on_add_frame(elements, value, HierarchyUI.Extremity.PRE_START)
        return True

    @with_elements
    def on_add_post_end(self, elements: list[HierarchyUI]):
        accept, value = get(Get.FROM_USER_FLOAT, "Add post-end", "Post-end length")
        if not accept:
            return False

        self._on_add_frame(elements, value, HierarchyUI.Extremity.POST_END)
        return True

    def _on_add_frame(
        self,
        elements: list[HierarchyUI],
        value: float,
        extremity: HierarchyUI.Extremity,
    ):
        from tilia.ui.timelines.hierarchy.element import HierarchyUI

        elements_to_set = []
        x_attr = extremity.value + "_x"
        for elm in elements:
            elements_to_set += self.get_elements_by_attr(x_attr, getattr(elm, x_attr))

        time_offset = (
            value if extremity == HierarchyUI.Extremity.PRE_START else value * -1
        )
        time = (
            elements_to_set[0].get_data(
                HierarchyUI.frame_to_body_extremity(extremity).value
            )
            - time_offset
        )
        self.set_elements_attr(elements_to_set, extremity.value, time)

    @with_elements
    def on_export_audio(self, elements: list[HierarchyUI]) -> bool:
        for elm in elements:
            post(
                Post.PLAYER_EXPORT_AUDIO,
                segment_name=elm.full_name,
                start_time=elm.get_data("start"),
                end_time=elm.get_data("end"),
            )
        return False
