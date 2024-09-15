from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView

import tilia.errors
from tilia.media.player.base import MediaTimeChangeReason
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import Get, get, listen, Post
from tilia.enums import Side
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
)
from tilia.ui.timelines.collection.requests.enums import ElementSelector

from tilia.ui.timelines.copy_paste import (
    paste_into_element,
)
from tilia.ui.timelines.pdf.context_menu import PdfTimelineUIContextMenu
from tilia.ui.timelines.pdf.element import PdfMarkerUI
from tilia.ui.timelines.pdf.request_handlers import PdfMarkerUIRequestHandler
from tilia.ui.timelines.pdf.toolbar import PdfTimelineToolbar
from tilia.ui.windows.view_window import ViewWindow

if TYPE_CHECKING:
    from tilia.ui.timelines.collection.collection import TimelineUIs
    from tilia.ui.timelines.base.element_manager import ElementManager
    from tilia.ui.timelines.scene import TimelineScene
    from tilia.ui.timelines.view import TimelineView


class PdfTimelineUI(TimelineUI):
    CONTEXT_MENU_CLASS = PdfTimelineUIContextMenu
    TOOLBAR_CLASS = PdfTimelineToolbar
    ELEMENT_CLASS = PdfMarkerUI
    ACCEPTS_HORIZONTAL_ARROWS = True

    TIMELINE_KIND = TimelineKind.PDF_TIMELINE

    def __init__(
        self,
        id: int,
        collection: TimelineUIs,
        element_manager: ElementManager,
        scene: TimelineScene,
        view: TimelineView,
    ):
        super().__init__(id, collection, element_manager, scene, view)

        self._setup_pdf_document()
        self._load_pdf_file()

        listen(self, Post.PLAYER_CURRENT_TIME_CHANGED, self.on_media_time_change)

    def _handle_invalid_pdf(self):
        tilia.errors.display(tilia.errors.INVALID_PDF, self.get_data("path"))
        _, value = get(Get.FROM_USER_RETRY_PDF_PATH)
        if value:
            success, path = get(Get.FROM_USER_PDF_PATH)
            if success:
                self.timeline.set_data("path", path)
                self._load_pdf_file()

    def _load_pdf_file(self):
        if not self.timeline.get_data("is_pdf_valid"):
            self._handle_invalid_pdf()
        self.pdf_document.load(self.get_data("path"))
        self.pdf_view.update_window(
            int(self.pdf_document.pagePointSize(0).height()),
            int(self.pdf_document.pagePointSize(0).width()),
        )

    def _setup_pdf_document(self):
        self.pdf_document = QPdfDocument(None)
        self.pdf_view = QPdfWindow(self.get_data("name"))
        self.pdf_view.setDocument(self.pdf_document)

    def update_name(self):
        name = self.get_data("name")
        self.scene.set_text(name)
        self.pdf_view.update_title(name)

    @property
    def current_page(self):
        return self.pdf_view.pageNavigator().currentPage() + 1  # 1-based

    @property
    def page_total(self):
        if not self.timeline.get_data("is_pdf_valid"):
            # Lifts page number limit on Inspector. This
            # prevents it from capping the
            # number at a value that might be lower than
            # the page total in a PDF loaded in the future.
            # Can't use math.inf because PyQt requires an int.
            return 99999999
        return self.timeline.get_data("page_total")

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return PdfMarkerUIRequestHandler(self).on_request(
            request, selector, *args, **kwargs
        )

    def on_timeline_component_created(self, kind: ComponentKind, id: int):
        super().on_timeline_component_created(kind, id)
        self.update_displayed_page(get(Get.MEDIA_CURRENT_TIME))

    def on_timeline_component_deleted(self, id: int):
        super().on_timeline_component_deleted(id)
        self.update_displayed_page(get(Get.MEDIA_CURRENT_TIME))

    def _deselect_all_but_last(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def on_side_arrow_press(self, side: Side):
        if not self.has_selected_elements:
            return

        self._deselect_all_but_last()

        selected_element = self.element_manager.get_selected_elements()[0]
        if side == Side.RIGHT:
            element_to_select = self.get_next_element(selected_element)
        elif side == Side.LEFT:
            element_to_select = self.get_previous_element(selected_element)
        else:
            raise ValueError(f"Invalid side '{side}'.")

        if element_to_select:
            self.deselect_element(selected_element)
            self.select_element(element_to_select)

    def validate_copy(self, elements: list[TimelineUIElement]) -> None:
        pass

    def paste_single_into_selected_elements(self, paste_data: list[dict] | dict):
        selected_elements = self.element_manager.get_selected_elements()

        self.validate_paste(paste_data, selected_elements)

        for element in self.element_manager.get_selected_elements():
            self.deselect_element(element)
            paste_into_element(element, paste_data[0])
            self.select_element(element)

    def paste_multiple_into_selected_elements(self, paste_data: list[dict] | dict):
        self.validate_paste(paste_data, self.selected_elements)

        paste_data = sorted(
            paste_data, key=lambda md: md["support_by_component_value"]["time"]
        )

        first_selected_element = self.selected_elements[0]

        self.deselect_element(self.selected_elements[0])
        paste_into_element(first_selected_element, paste_data[0])
        self.select_element(first_selected_element)

        self.create_pasted_markers(
            paste_data[1:],
            paste_data[0]["support_by_component_value"]["time"],
            self.selected_elements[0].get_data("time"),
        )

    def paste_single_into_timeline(self, paste_data: list[dict] | dict):
        return self.paste_multiple_into_timeline(paste_data)

    def paste_multiple_into_timeline(self, paste_data: list[dict] | dict):
        reference_time = min(
            md["support_by_component_value"]["time"] for md in paste_data
        )

        self.create_pasted_markers(
            paste_data,
            reference_time,
            get(Get.SELECTED_TIME),
        )

    def create_pasted_markers(
        self, paste_data: list[dict], reference_time: float, target_time: float
    ) -> None:
        for pdf_marker_data in copy.deepcopy(paste_data):
            # deepcopying so popping won't affect original data
            marker_time = pdf_marker_data["support_by_component_value"].pop("time")

            self.timeline.create_component(
                ComponentKind.PDF_MARKER,
                target_time + (marker_time - reference_time),
                **pdf_marker_data["by_element_value"],
                **pdf_marker_data["by_component_value"],
                **pdf_marker_data["support_by_element_value"],
                **pdf_marker_data["support_by_component_value"],
            )

    def on_media_time_change(self, time, reason: MediaTimeChangeReason) -> None:
        self.update_displayed_page(time)

    def update_displayed_page(self, time):
        target_page = self.timeline.get_previous_page_number(time)
        if target_page == 0:
            # No markers are present
            target_page = 1
        if self.pdf_view.pageNavigator().currentPage() != target_page - 1:
            self.pdf_view.pageNavigator().jump(target_page - 1, QPointF(0, 0), 0)

    def delete(self):
        super().delete()
        self.pdf_view.deleteLater()


class QPdfWindow(ViewWindow, QPdfView):
    def __init__(self, name: str):
        super().__init__("TiLiA PDF Viewer", None, menu_title=name)
        self.setPageMode(QPdfView.PageMode.MultiPage)

    def update_window(self, width: int, height: int):
        self.resize(width, height)
        self.show()
