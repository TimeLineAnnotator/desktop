import pytest

from tests.mock import Serve
from tilia.requests import Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.pdf.components import PdfMarker
from tilia.timelines.pdf.timeline import PdfTimeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.timelines.pdf import PdfTimelineUI, PdfMarkerUI


class TestPdfTimelineUI(PdfTimelineUI):
    def create_component(
            self,
            kind,
            time=0,
            **kwargs
    ) -> tuple[PdfMarker, PdfMarkerUI]: ...

    def create_pdf_marker(
            self, time=0, **kwargs
    ) -> tuple[PdfMarker, PdfMarkerUI]: ...


@pytest.fixture
def pdf_tlui(tls, tluis) -> TestPdfTimelineUI:
    with Serve(Get.FROM_USER_RETRY_PDF_PATH, (False, False)):
        tl: PdfTimeline = tls.create_timeline(TlKind.PDF_TIMELINE, path='')
    tl.clear()  # delete initial pdf marker
    ui = tluis.get_timeline_ui(tl.id)

    def create_component(
            *args,
            **kwargs
    ) -> tuple[PdfMarker, PdfMarkerUI]:
        return create_pdf_marker(*args, **kwargs)

    def create_pdf_marker(*args, **kwargs):
        component, _ = tl.create_timeline_component(
            ComponentKind.PDF_MARKER, *args, **kwargs
        )
        element = ui.get_element(component.id) if component else None
        return component, element

    def noop(*args, **kwargs):
        pass

    tl.create_pdf_marker = create_pdf_marker
    ui.create_pdf_marker = create_pdf_marker
    tl.create_component = create_component
    ui.create_component = create_component

    yield ui  # will be deleted by tls


@pytest.fixture
def pdf_tl(pdf_tlui):
    tl = pdf_tlui.timeline

    yield tl


@pytest.fixture
def pdfui(pdf_tlui):
    _, _mrkui = pdf_tlui.create_pdf_marker(0)
    return _mrkui


@pytest.fixture
def pdf(pdf_tlui):
    _mrk, _ = pdf_tlui.create_pdf_marker(0)
    return _mrk


@pytest.fixture
def pdf_and_ui(pdf_tlui):
    return pdf_tlui.create_pdf_marker(0)
