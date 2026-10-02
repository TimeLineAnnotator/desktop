from unittest.mock import patch

from PySide6.QtWidgets import QDialog

from tests.ui.timelines.interact import click_timeline_ui_view
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.ui.coords import time_x_converter
from tilia.ui.windows.fill_beat_timeline import FillBeatTimeline


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


def patch_fill_beat_timeline_dialog(timeline, method, value: float):
    """
    Makes the "Fill with beats" dialog choose `timeline`, fill `method` and
    `value`, then press OK.
    """

    def exec_(dialog):
        combobox = dialog._timeline_combobox
        combobox.setCurrentIndex(combobox.findData(timeline))
        dialog._options.button(method.value).setChecked(True)
        if method == BeatTimeline.FillMethod.BY_AMOUNT:
            dialog._by_amount_edit.setValue(int(value))
        else:
            dialog._by_interval_edit.setValue(value)
        return QDialog.DialogCode.Accepted

    return patch.object(FillBeatTimeline, "exec", new=exec_)
