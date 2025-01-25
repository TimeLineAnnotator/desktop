import tilia.ui.strings
from tilia.requests import Post, get, Get, post
from tilia.settings import settings
from tilia.ui.timelines.base.request_handlers import ElementRequestHandler
from tilia.ui.timelines.hierarchy.copy_paste import (
    _display_copy_error,
    _validate_copy_cardinality,
    _validate_paste_complete_cardinality,
    _validate_paste_complete_level,
    _display_paste_complete_error,
)
from tilia.ui.timelines.hierarchy.extremity import Extremity


class HierarchyUIRequestHandler(ElementRequestHandler):
    def __init__(self, timeline_ui):
        super().__init__(
            timeline_ui,
            {
                Post.HIERARCHY_INCREASE_LEVEL: self.on_increase_level,
                Post.HIERARCHY_DECREASE_LEVEL: self.on_decrease_level,
                Post.HIERARCHY_GROUP: self.on_group,
                Post.HIERARCHY_SPLIT: self.on_split,
                Post.HIERARCHY_MERGE: self.on_merge,
                Post.HIERARCHY_CREATE_CHILD: self.on_create_child,
                Post.HIERARCHY_ADD_PRE_START: self.on_add_pre_start,
                Post.HIERARCHY_ADD_POST_END: self.on_add_post_end,
                Post.TIMELINE_ELEMENT_PASTE_COMPLETE: self.on_paste_complete,
                Post.TIMELINE_ELEMENT_DELETE: self.on_delete,
                Post.TIMELINE_ELEMENT_COLOR_SET: self.on_color_set,
                Post.TIMELINE_ELEMENT_COLOR_RESET: self.on_color_reset,
                Post.TIMELINE_ELEMENT_EXPORT_AUDIO: self.on_export_audio,
                Post.TIMELINE_ELEMENT_COPY: self.on_copy,
                Post.TIMELINE_ELEMENT_PASTE: self.on_paste,
            },
        )

    def on_increase_level(self, elements, *_, **__):
        min_margin = 10
        success = self.timeline.alter_levels(
            self.elements_to_components(reversed(elements)), 1
        )
        if success:
            max_height = self.timeline_ui.get_max_hierarchy_height()
            if max_height > self.timeline_ui.get_data("height") + min_margin:
                get(Get.TIMELINE_COLLECTION).set_timeline_data(
                    self.timeline_ui.id, "height", max_height + min_margin
                )

        return success

    def on_decrease_level(self, elements, *_, **__):
        return self.timeline.alter_levels(self.elements_to_components(elements), -1)

    def on_group(self, elements, *_, **__):
        return self.timeline.group(self.elements_to_components(elements))

    def on_split(self, *_, **__):
        return self.timeline.split(get(Get.SELECTED_TIME))

    def on_merge(self, elements, *_, **__):
        return self.timeline.merge(self.elements_to_components(elements))

    def on_create_child(self, elements, *_, **__):
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
                self.on_increase_level(self.timeline_ui.elements, *_, **__)
            else:
                return False

        return self.timeline.create_children(self.elements_to_components(elements))

    def on_add_pre_start(self, elements, value, *_, **__):
        self.on_add_frame(elements, value, Extremity.PRE_START)
        return True

    def on_add_post_end(self, elements, value, *_, **__):
        self.on_add_frame(elements, value, Extremity.POST_END)
        return True

    def on_add_frame(self, elements, value, extremity):
        from tilia.ui.timelines.hierarchy.element import HierarchyUI

        elements_to_set = []
        x_attr = extremity.value + "_x"
        for elm in elements:
            elements_to_set += self.timeline_ui.get_elements_by_attr(
                x_attr, getattr(elm, x_attr)
            )

        time_offset = value if extremity == Extremity.PRE_START else value * -1
        time = (
            elements_to_set[0].get_data(
                HierarchyUI.frame_to_body_extremity(extremity).value
            )
            - time_offset
        )
        self.timeline_ui.set_elements_attr(elements_to_set, extremity.value, time)

    def on_delete(self, elements, *_, **__):
        self.timeline.delete_components(self.elements_to_components(elements))
        return True

    def on_color_set(self, elements, value, **_):
        self.timeline_ui.set_elements_attr(elements, "color", value.name())
        return True

    def on_color_reset(self, elements, *_, **__):
        self.timeline_ui.set_elements_attr(
            elements,
            "color",
            None,
        )
        return True

    @staticmethod
    def on_export_audio(elements, *_, **__):
        for elm in elements:
            post(
                Post.PLAYER_EXPORT_AUDIO,
                segment_name=elm.full_name,
                start_time=elm.get_data("start"),
                end_time=elm.get_data("end"),
            )
        return False  # this action shouldn't be recorded in undo manager

    def on_copy(self, elements):
        success, reason = _validate_copy_cardinality(elements)
        if not success:
            _display_copy_error(reason)

        component_data = [
            self.timeline_ui.get_copy_data_from_hierarchy_ui(e) for e in elements
        ]

        if not component_data:
            return False

        post(
            Post.TIMELINE_ELEMENT_COPY_DONE,
            {"components": component_data, "timeline_kind": self.timeline.KIND},
        )

        return True

    def on_paste_complete(self, *_, **__) -> bool:
        copied_components = get(Get.CLIPBOARD_CONTENTS)["components"]
        if not copied_components or not self.timeline_ui.has_selected_elements:
            return False

        success, reason = _validate_paste_complete_cardinality(copied_components)
        if not success:
            _display_paste_complete_error(reason)
            return False

        data = copied_components[0]
        for element in self.timeline_ui.selected_elements:
            success, reason = _validate_paste_complete_level(element, data)
            if not success:
                _display_paste_complete_error(reason)
                return False

            while children := element.get_data("children"):
                self.timeline.delete_components(children)

            self.timeline_ui.paste_with_children_into_element(data, element)

        return True
