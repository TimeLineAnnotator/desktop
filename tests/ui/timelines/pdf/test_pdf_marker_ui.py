from typing import cast
from unittest.mock import Mock

import pytest

from tests.utils import save_and_reopen, undoable
from tilia.requests import Post, post
from tilia.ui import commands
from tilia.ui.format import format_media_time
from tilia.ui.qtui import QtUI
from tilia.ui.timelines.pdf import PdfTimelineUI
from tilia.ui.windows import WindowKind
from tilia.ui.windows.inspect import Inspect


def get_inspect_window(qtui: QtUI) -> Inspect | None:
    window = qtui._windows[WindowKind.INSPECT]
    if not window:
        return
    return cast(Inspect, window)


def get_inspect_widget(qtui: QtUI, field_name: str) -> None:
    window = get_inspect_window(qtui)
    if not window:
        raise ValueError("Inspect window not found.")

    try:
        return window.field_name_to_widgets[field_name][1]
    except KeyError as e:
        raise KeyError("Field name not found in inspect window.") from e


class TestInspect:
    def test_inspect(self, pdf_tlui, qtui, resources):
        commands.execute("timeline.pdf.add", time=10, page_number=5)
        pdf_tlui.select_element(pdf_tlui[0])
        commands.execute("timeline.element.inspect")
        time = get_inspect_widget(qtui, "Time").text()
        page_number = get_inspect_widget(qtui, "Page number").value()
        assert time == format_media_time(10)
        assert page_number == 5


class TestDoubleClick:
    def test_pdf_marker_seek(self, pdf_tlui, tilia_state):
        commands.execute("timeline.pdf.add", time=10)
        pdf_tlui[0].on_double_left_click(None)

        assert tilia_state.current_time == 10

    def test_does_not_trigger_drag(self, pdf_tlui):
        commands.execute("timeline.pdf.add")
        mock = Mock()
        pdf_tlui[0].setup_drag = mock
        pdf_tlui[0].on_double_left_click(None)

        mock.assert_not_called()


class TestPageNumberInspectorEdit:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def test_page_number_capped_at_page_total(
        self, pdf_tl, pdf_tlui, qtui, tluis, tmp_path
    ):
        # Setting the page number through the inspector is capped at
        # the document's page count.
        pdf_tl.page_total = 3
        commands.execute("timeline.pdf.add", time=10, page_number=1)
        pdf_tlui.select_element(pdf_tlui[0])
        commands.execute("timeline.element.inspect")

        page_number_widget = get_inspect_widget(qtui, "Page number")
        assert page_number_widget.maximum() == 3

        with undoable():
            page_number_widget.setValue(999)

        assert pdf_tlui[0].get_data("page_number") == 3
        assert pdf_tlui[0].label.toPlainText() == "3"

        save_and_reopen(tmp_path)
        reloaded_tlui = [t for t in tluis if isinstance(t, PdfTimelineUI)][0]
        assert reloaded_tlui[0].get_data("page_number") == 3
        assert reloaded_tlui[0].label.toPlainText() == "3"
