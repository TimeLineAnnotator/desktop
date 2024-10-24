from tests.ui.timelines.interact import click_timeline_ui_view
from tilia.ui.coords import time_x_converter


def click_marker_ui(element, button="left", modifier=None, double=False):
    click_timeline_ui_view(
        element.timeline_ui.view,
        button,
        time_x_converter.get_x_by_time(element.get_data("time")),
        element.timeline_ui.get_data("height") / 2,
        element.body,
        modifier,
        double,
    )
