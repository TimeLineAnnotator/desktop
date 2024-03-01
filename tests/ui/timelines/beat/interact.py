from tests.ui.timelines.interact import click_timeline_ui_view
from tilia.ui.coords import get_x_by_time


def click_beat_ui(beat_ui, button="left", modifier=None, double=False):
    click_timeline_ui_view(
        beat_ui.timeline_ui.view,
        button,
        get_x_by_time(beat_ui.time),
        beat_ui.height / 2,
        beat_ui.body,
        modifier,
        double,
    )
