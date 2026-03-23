from typing import Any

from tilia.ui import commands
from tilia.ui.timelines.pdf import PdfTimelineUI


def assert_pdf_marker(tlui: PdfTimelineUI, index: int, attr: str, value: Any) -> None:
    assert tlui[index].get_data(attr) == value


class TestAddMarker:
    def test_no_args(self, pdf_tlui, tilia_state):
        tilia_state.current_time = 10
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 11
        commands.execute("timeline.pdf.add")

        assert len(pdf_tlui.timeline) == 2
        assert_pdf_marker(pdf_tlui, 0, "time", 10)
        assert_pdf_marker(pdf_tlui, 0, "page_number", 1)
        assert_pdf_marker(pdf_tlui, 1, "time", 11)
        assert_pdf_marker(pdf_tlui, 1, "page_number", 2)

    def test_pass_time(self, pdf_tlui):
        commands.execute("timeline.pdf.add", time=10)

        assert len(pdf_tlui.timeline) == 1
        assert_pdf_marker(pdf_tlui, 0, "time", 10)

    def test_pass_page_number(self, pdf_tlui):
        commands.execute("timeline.pdf.add", page_number=5)

        assert len(pdf_tlui.timeline) == 1
        assert_pdf_marker(pdf_tlui, 0, "page_number", 5)

    def test_pass_time_and_page_number(self, pdf_tlui):
        commands.execute("timeline.pdf.add", time=10, page_number=5)

        assert len(pdf_tlui.timeline) == 1
        assert_pdf_marker(pdf_tlui, 0, "time", 10)
        assert_pdf_marker(pdf_tlui, 0, "page_number", 5)
