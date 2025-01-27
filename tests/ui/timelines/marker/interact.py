from tests.ui.timelines.interact import click_timeline_ui
from tilia.ui.coords import time_x_converter


def get_marker_ui_center(element):
    return (
        time_x_converter.get_x_by_time(element.get_data("time")),
        element.timeline_ui.get_data("height") / 2,
    )


def click_marker_ui(element, button="left", modifier=None, double=False):
    click_timeline_ui(
        element.timeline_ui,
        element.get_data("time"),
        button=button,
        modifier=modifier,
        double=double,
    )
