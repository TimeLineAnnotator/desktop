from typing import Callable

import tilia.ui.strings
import tilia.ui.timelines.copy_paste
from tilia.requests import Get, Post, get, listen, post
from tilia.settings import settings
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.ui import commands
from tilia.ui.menus import HierarchyMenu
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
    ACCEPTS_HORIZONTAL_ARROWS = True
    ACCEPTS_VERTICAL_ARROWS = True
    MIN_MARGIN = 10
    timeline_class = HierarchyTimeline
    menu_class = HierarchyMenu

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
            # decrease_level / increase_level: shortcut field is empty
            # because Ctrl+Up / Ctrl+Down are dispatched via
            # Post.TIMELINE_KEY_PRESS_CTRL_UP/DOWN (see TimelineView and
            # TimelineUIs.on_ctrl_arrow_press) instead of being attached
            # to the QAction. Registering the same shortcut here as well
            # would produce a Qt "Ambiguous shortcut" warning.
            (
                "decrease_level",
                "Move down a level",
                "",
                "hierarchy-level-down",
            ),
            ("group", "Group", "g", "hierarchy-create-parent"),
            (
                "increase_level",
                "Move up a level",
                "",
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

        cls.register_timeline_command(
            collection,
            "add",
            cls.on_add,
            TimelineSelector.FIRST,
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

    @staticmethod
    def _get_paste_time_map(
        source_start: float,
        source_end: float,
        target_start: float,
        target_end: float,
    ) -> Callable[[float], float]:
        """Return the affine map from the copied subtree's timespan to the target's.

        The whole subtree shares one map, so a time that appears in several
        copied components — as one's end and the next one's start — maps to the
        same float in all of them and coincident boundaries stay coincident.
        Deriving a scale factor separately per nesting level, or anchoring
        starts and ends to different reference points, lets those boundaries
        drift apart by a few ulps, which later reads as an overlap.
        """
        scale_factor = (target_end - target_start) / (source_end - source_start)

        def map_time(time: float) -> float:
            # Anchor the endpoints exactly: scaling them arithmetically can
            # land a ulp off, misaligning the subtree with the target.
            if time == source_start:
                return target_start
            if time == source_end:
                return target_end
            return (time - source_start) * scale_factor + target_start

        return map_time

    def _create_child_from_paste_data(
        self,
        child_pastedata_: dict,
        map_time: Callable[[float], float],
    ) -> tuple[Hierarchy | None, str | None]:
        return self.timeline.create_component(
            kind=ComponentKind.HIERARCHY,
            start=map_time(child_pastedata_["context"]["start"]),
            end=map_time(child_pastedata_["context"]["end"]),
            level=child_pastedata_["context"]["level"],
            **child_pastedata_["values"],
        )

    def paste_with_children_into_element(
        self, paste_data: dict, element: HierarchyUI
    ) -> list[str]:
        """Paste the copied subtree into ``element``, rescaled to its timespan.

        Returns the reasons any descendant could not be created. Pasting is
        best-effort: a child that fails is skipped along with its own subtree,
        and the remaining siblings are still pasted.
        """
        map_time = self._get_paste_time_map(
            paste_data["context"]["start"],
            paste_data["context"]["end"],
            element.tl_component.start,
            element.tl_component.end,
        )
        return self._paste_subtree_into_element(paste_data, element, map_time)

    def _paste_subtree_into_element(
        self,
        paste_data: dict,
        element: HierarchyUI,
        map_time: Callable[[float], float],
    ) -> list[str]:
        tilia.ui.timelines.copy_paste.paste_into_element(element, paste_data)

        fail_reasons = []
        for child_paste_data in paste_data.get("children", []):
            child_component, fail_reason = self._create_child_from_paste_data(
                child_paste_data, map_time
            )

            if child_component is None:
                fail_reasons.append(fail_reason)
                continue

            if child_paste_data.get("children", None):
                fail_reasons += self._paste_subtree_into_element(
                    child_paste_data, self.get_component_ui(child_component), map_time
                )

        return fail_reasons

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

    def on_ctrl_vertical_arrow_press(self, direction: str) -> None:
        cmd = (
            "timeline.hierarchy.increase_level"
            if direction == "up"
            else "timeline.hierarchy.decrease_level"
        )
        commands.execute(cmd)

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
            {"components": component_data, "timeline_type": self.timeline_class},
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
        fail_reasons = []
        for element in self.selected_elements:
            success, reason = _validate_paste_complete_level(element, data)
            if not success:
                _display_paste_complete_error(reason)
                return False

            while children := element.get_data("children"):
                self.timeline.delete_components(children)

            fail_reasons += self.paste_with_children_into_element(data, element)

        if fail_reasons:
            _display_paste_complete_error("\n".join(fail_reasons))
            return False

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

    def on_add(self, start: float, end: float, level: int, **kwargs):
        component, _ = self.timeline.create_component(
            ComponentKind.HIERARCHY, start=start, end=end, level=level, **kwargs
        )
        return bool(component)

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
        accept, value = get(
            Get.FROM_USER_FLOAT,
            "Add pre-start",
            "Pre-start length",
            minValue=HierarchyUI.MIN_FRAME_LENGTH,
            maxValue=min(elm.get_data("start") for elm in elements),
        )
        if not accept:
            return False

        self._on_add_frame(elements, value, HierarchyUI.Extremity.PRE_START)
        return True

    @with_elements
    def on_add_post_end(self, elements: list[HierarchyUI]):
        accept, value = get(
            Get.FROM_USER_FLOAT,
            "Add post-end",
            "Post-end length",
            minValue=HierarchyUI.MIN_FRAME_LENGTH,
            maxValue=get(Get.MEDIA_DURATION)
            - max(elm.get_data("end") for elm in elements),
        )
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
            commands.execute(
                "media.export_audio",
                segment_name=elm.full_name,
                start_time=elm.get_data("start"),
                end_time=elm.get_data("end"),
            )
        return False
