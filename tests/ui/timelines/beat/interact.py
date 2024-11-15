from tests.ui.timelines.interact import click_timeline_ui_view
from tilia.ui.coords import time_x_converter


def click_beat_ui(beat_ui, button="left", modifier=None, double=False):
    click_timeline_ui_view(
        beat_ui.timeline_ui.view,
        button,
        time_x_converter.get_x_by_time(beat_ui.time),
        beat_ui.height / 2,
        beat_ui.body,
        modifier,
        double,
    )
