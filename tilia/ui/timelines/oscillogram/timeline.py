from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.enums import Side
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.timeline import TimelineUI
from tilia.ui.timelines.collection.requests.enums import ElementSelector

from tilia.ui.timelines.oscillogram.element import OscillogramUI
from tilia.ui.timelines.oscillogram.request_handlers import OscillogramTimelineUIRequestHandler
from tilia.ui.timelines.oscillogram.toolbar import OscillogramTimelineToolbar


class OscillogramTimelineUI(TimelineUI):
    TOOLBAR_CLASS = OscillogramTimelineToolbar
    ELEMENT_CLASS = OscillogramUI
    ACCEPTS_HORIZONTAL_ARROWS = True

    TIMELINE_KIND = TimelineKind.OSCILLOGRAM_TIMELINE

    def on_timeline_element_request(self, request, selector: ElementSelector, *args, **kwargs):
        return OscillogramTimelineUIRequestHandler(self).on_request(request, selector, *args, *kwargs)
    
    def on_side_arrow_press(self, side: Side):
        if not self.has_selected_elements:
            return
        
        self._deselect_all_but_last()

        selected_element = self.element_manager.get_selected_elements()[0]
        if side == side.RIGHT:
            element_to_select = self.get_next_element(selected_element)
        elif side == side.LEFT:
            element_to_select = self.get_previous_element(selected_element)
        else:
            raise ValueError(f"Invalid side '{side}'.")
        
        if element_to_select:
            self.deselect_element(selected_element)
            self.select_element(element_to_select)
