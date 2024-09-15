from __future__ import annotations

from typing import TYPE_CHECKING

import tilia.errors
from tilia.requests import Post, get, Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.request_handlers import ElementRequestHandler
from tilia.ui.timelines.copy_paste import get_copy_data_from_element
from tilia.ui.timelines.pdf.element import PdfMarkerUI

if TYPE_CHECKING:
    from tilia.ui.timelines.pdf import PdfTimelineUI


class PdfMarkerUIRequestHandler(ElementRequestHandler):
    def __init__(self, timeline_ui: PdfTimelineUI):

        super().__init__(
            timeline_ui,
            {
                Post.PDF_MARKER_ADD: self.on_add,
                Post.PDF_MARKER_DELETE: self.on_delete,
                Post.TIMELINE_ELEMENT_DELETE: self.on_delete,
                Post.TIMELINE_ELEMENT_COPY: self.on_copy,
                Post.TIMELINE_ELEMENT_PASTE: self.on_paste,
            },
        )


    def on_add(self, *_, **__):
        time = get(Get.SELECTED_TIME)

        page_number = min(self.timeline.get_previous_page_number(time) + 1, self.timeline.page_total)

        pdf_marker, reason = self.timeline.create_component(
            ComponentKind.PDF_MARKER, get(Get.SELECTED_TIME), page_number
        )
        if not pdf_marker:
            tilia.errors.display(tilia.errors.ADD_PDF_MARKER_FAILED, reason)

    def on_delete(self, elements, *_, **__):
        self.timeline.delete_components(self.elements_to_components(elements))

    @staticmethod
    def on_copy(elements):
        copy_data = []
        for elm in elements:
            copy_data.append(
                {
                    "components": get_copy_data_from_element(
                        elm, PdfMarkerUI.DEFAULT_COPY_ATTRIBUTES
                    ),
                    "timeline_kind": TimelineKind.PDF_TIMELINE,
                }
            )

        return copy_data

