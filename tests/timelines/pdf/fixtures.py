import functools

import pytest

from tests.mock import Serve
from tilia.requests import Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.pdf.components import PdfMarker
from tilia.timelines.pdf.timeline import PdfTimeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.timelines.pdf import PdfTimelineUI, PdfMarkerUI


class TestPdfTimelineUI(PdfTimelineUI):
    def create_component(self, time=0, **kwargs) -> tuple[PdfMarker, PdfMarkerUI]: ...

    def create_pdf_marker(self, time=0, **kwargs) -> tuple[PdfMarker, PdfMarkerUI]: ...


@pytest.fixture
def pdf_tlui(pdf_tl, tluis):

    ui = tluis.get_timeline_ui(pdf_tl.id)

    ui.create_pdf_marker = pdf_tl.create_pdf_marker
    ui.create_component = pdf_tl.create_component

    yield ui  # will be deleted by tls


@pytest.fixture
def pdf_tl(tls):
    with Serve(Get.FROM_USER_RETRY_PDF_PATH, (False, False)):
        tl: PdfTimeline = tls.create_timeline(TlKind.PDF_TIMELINE, path="")
    tl.clear()  # delete initial pdf marker
    tl.create_pdf_marker = functools.partial(
        tl.create_component, ComponentKind.PDF_MARKER
    )

    yield tl


@pytest.fixture
def pdfui(pdf_tlui):
    _, _mrkui = pdf_tlui.create_pdf_marker(0)
    return _mrkui


@pytest.fixture
def pdf_marker(pdf_tl):
    return pdf_tl.create_pdf_marker(0, 1)[0]


@pytest.fixture
def pdf_marker_ui(pdf_tlui, pdf_marker):
    return pdf_tlui.get_element(pdf_marker.id)
