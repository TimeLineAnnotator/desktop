from tests.ui.timelines.interact import click_timeline_ui_view
from tilia.ui.coords import time_x_converter


def _click_element_ui(element, button, modifier, double):
    click_timeline_ui_view(
        element.timeline_ui.view,
        button,
        time_x_converter.get_x_by_time(element.get_data("time")),
        element.timeline_ui.get_data("height") / 2,
        element.body,
        modifier,
        double,
    )


def click_harmony_ui(harmony_ui, button="left", modifier=None, double=False):
    _click_element_ui(harmony_ui, button, modifier, double)


def click_mode_ui(mode_ui, button="left", modifier=None, double=False):
    _click_element_ui(mode_ui, button, modifier, double)
