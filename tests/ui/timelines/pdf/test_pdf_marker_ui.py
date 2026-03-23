from typing import cast

from tilia.ui import commands
from tilia.ui.format import format_media_time
from tilia.ui.qtui import QtUI
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
    except KeyError:
        raise KeyError("Field name not found in inspect window.")


class TestInspect:
    def test_inspect(self, pdf_tlui, qtui, resources):
        commands.execute("timeline.pdf.add", time=10, page_number=5)
        pdf_tlui.select_element(pdf_tlui[0])
        commands.execute("timeline.element.inspect")
        time = get_inspect_widget(qtui, "Time").text()
        page_number = get_inspect_widget(qtui, "Page number").value()
        assert time == format_media_time(10)
        assert page_number == 5
