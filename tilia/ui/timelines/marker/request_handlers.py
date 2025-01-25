from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.requests import Post, get, Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.ui.timelines.base.request_handlers import ElementRequestHandler

if TYPE_CHECKING:
    from tilia.ui.timelines.marker import MarkerTimelineUI


class MarkerUIRequestHandler(ElementRequestHandler):
    def __init__(self, timeline_ui: MarkerTimelineUI):

        super().__init__(
            timeline_ui,
            {
                Post.MARKER_ADD: self.on_add,
                Post.TIMELINE_ELEMENT_DELETE: self.on_delete,
                Post.TIMELINE_ELEMENT_COLOR_SET: self.on_color_set,
                Post.TIMELINE_ELEMENT_COLOR_RESET: self.on_color_reset,
                Post.TIMELINE_ELEMENT_COPY: self.on_copy,
                Post.TIMELINE_ELEMENT_PASTE: self.on_paste,
            },
        )

    def on_color_set(self, elements, value, **_):
        self.timeline_ui.set_elements_attr(elements, "color", value.name())
        return True

    def on_color_reset(self, elements, *_, **__):
        self.timeline_ui.set_elements_attr(elements, "color", None)
        return True

    def on_add(self, *_, **__):
        component, _ = self.timeline.create_component(
            ComponentKind.MARKER, get(Get.SELECTED_TIME)
        )
        return False if component is None else True

    def on_delete(self, elements, *_, **__):
        self.timeline.delete_components(self.elements_to_components(elements))
        return True
