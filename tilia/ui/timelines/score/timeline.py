from __future__ import annotations

from tilia.exceptions import GetComponentDataError
from tilia.requests import Get, get, listen, Post
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
)
from tilia.ui.timelines.collection.requests.enums import ElementSelector
from tilia.ui.timelines.score.element import NoteUI, StaffUI
from tilia.ui.timelines.score.element.with_collision import TimelineUIElementWithCollision
from tilia.ui.timelines.score.request_handlers import ScoreTimelineUIElementRequestHandler
from tilia.ui.timelines.score.toolbar import ScoreTimelineToolbar


class ScoreTimelineUI(TimelineUI):
    TOOLBAR_CLASS = ScoreTimelineToolbar
    ACCEPTS_HORIZONTAL_ARROWS = True

    TIMELINE_KIND = TimelineKind.SCORE_TIMELINE
    ELEMENT_CLASS = [NoteUI, StaffUI]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listen(self, Post.SETTINGS_UPDATED, lambda updated_settings: self.on_settings_updated(updated_settings))

    def on_settings_updated(self, updated_settings):        
        if "score_timeline" in updated_settings:  
            get(Get.TIMELINE_COLLECTION).set_timeline_data(self.id, "height", self.timeline.default_height)
            for element in self:
                element.update_position()

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return ScoreTimelineUIElementRequestHandler(self).on_request(
            request, selector, *args, **kwargs
        )

    def get_barline_top_y(self) -> float:
        staff = self.element_manager.get_element_by_attribute('kind', ComponentKind.STAFF)
        return staff.top_y()

    def get_barline_bottom_y(self) -> float:
        staff = self.element_manager.get_element_by_attribute('kind', ComponentKind.STAFF)
        return staff.bottom_y()

    def get_height_for_symbols_above_staff(self) -> int:
        return 50

    def on_timeline_component_created(self, kind: ComponentKind, id: int):
        element = super().on_timeline_component_created(kind, id)
        try:
            time = element.get_data('time')
        except GetComponentDataError:
            return
        if overlapping_components := self._get_overlap(time, kind):
            component_to_offset = self._get_offsets_for_overlapping_elements(overlapping_components)
            for component in overlapping_components:
                component.x_offset = component_to_offset[component]

    def _get_overlap(self, time: float, kind: ComponentKind) -> list[TimelineUIElementWithCollision]:
        # Elements will be displayed in the order below
        overlapping_kinds = [ComponentKind.CLEF, ComponentKind.KEY_SIGNATURE, ComponentKind.TIME_SIGNATURE]

        if kind not in overlapping_kinds:
            return []

        overlapping = [c for c in self if c.kind in overlapping_kinds and c.get_data('time') == time]
        overlapping = sorted(overlapping, key=lambda c: overlapping_kinds.index(c.kind))
        return overlapping if len(overlapping) > 1 else []

    def _get_offsets_for_overlapping_elements(self, overlapping_elements: list[TimelineUIElementWithCollision]):
        mid_x = sum([c.width for c in overlapping_elements]) / 2
        element_to_offset = {}
        total_width = 0

        for element in overlapping_elements:
            element_to_offset[element] = total_width - mid_x

            total_width += element.width


        return element_to_offset
