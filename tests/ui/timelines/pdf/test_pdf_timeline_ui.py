from typing import Any

from tilia.requests import Post, post
from tilia.timelines.pdf.timeline import PdfTimeline
from tilia.ui import commands
from tilia.ui.commands import get_qaction
from tilia.ui.timelines.pdf import PdfTimelineUI


def assert_pdf_marker(tlui: PdfTimelineUI, index: int, attr: str, value: Any) -> None:
    assert tlui[index].get_data(attr) == value


class TestAddMarker:
    def test_no_args(self, pdf_tlui, tilia_state):
        commands.execute("media.seek", 10)
        commands.execute("timeline.pdf.add")
        commands.execute("media.seek", 11)
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


class TestTimelineUIContextMenu:
    def test_has_no_height_set_action(self, pdf_tlui, tluis):
        context_menu = pdf_tlui.CONTEXT_MENU_CLASS(pdf_tlui, 0, 0)

        assert get_qaction("timeline.set_height") not in context_menu.actions()


class TestPdfViewWindow:
    """Each PDF timeline owns its own top-level PDF viewer
    window, managed through the same generic ViewWindow/View-menu plumbing
    as the media player windows (see TestViewWindow in
    tests/ui/windows/test_windows.py)."""

    def test_several_pdf_timelines_get_separate_windows(self, tls, tluis, resources):
        path = str((resources / "example.pdf").resolve())
        tl1 = tls.create_timeline(PdfTimeline, path=path)
        tl2 = tls.create_timeline(PdfTimeline, path=path)

        window1 = tluis.get_timeline_ui(tl1.id).pdf_view
        window2 = tluis.get_timeline_ui(tl2.id).pdf_view

        assert window1 is not window2
        assert window1.isVisible()
        assert window2.isVisible()

    def test_view_hides_when_closed_from_itself(self, pdf_tlui):
        window = pdf_tlui.pdf_view
        window.close()

        assert not window.isVisible()

    def test_view_reopens_from_view_menu(self, pdf_tlui):
        window = pdf_tlui.pdf_view
        post(Post.WINDOW_UPDATE_REQUEST, window.id, False)

        post(Post.WINDOW_UPDATE_REQUEST, window.id, True)

        assert window.isVisible()

    def test_view_closes_from_view_menu(self, pdf_tlui):
        window = pdf_tlui.pdf_view

        post(Post.WINDOW_UPDATE_REQUEST, window.id, False)

        assert not window.isVisible()
