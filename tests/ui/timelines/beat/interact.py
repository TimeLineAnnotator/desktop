from contextlib import contextmanager
from unittest.mock import patch

from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QGraphicsSceneHoverEvent, QMessageBox

from tests.ui.timelines.interact import click_timeline_ui_view
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.ui import strings
from tilia.ui.coords import time_x_converter
from tilia.ui.windows.beat_pattern import BeatPatternDialog
from tilia.ui.windows.beat_unit import BeatUnitDialog
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


def patch_beat_pattern_dialog(typed: str | None, on_exec=None):
    """
    Makes the beat pattern dialog type `typed` and press OK, or press Cancel
    when `typed` is None. `on_exec(dialog)` runs after typing, before OK, e.g.
    to check the preview.
    """

    def exec_(dialog):
        if typed is None:
            return QDialog.DialogCode.Rejected
        dialog.line_edit.clear()
        QTest.keyClicks(dialog.line_edit, typed)
        if on_exec:
            on_exec(dialog)
        dialog.ok_button.click()
        return dialog.result()

    return patch.object(BeatPatternDialog, "exec", new=exec_)


def click_time_signature_label(
    timeline_ui, label, button="left", modifier=None, double=False
):
    """Clicks the middle of a time signature label, hit-testing like the view."""
    center = label.rect().center()
    x, y = int(center.x()), int(center.y())
    item = timeline_ui.view.itemAt(x, y)
    click_timeline_ui_view(timeline_ui.view, button, x, y, item, modifier, double)


def hover_time_signature_label(timeline_ui, label, entered=True):
    event_type = (
        QEvent.Type.GraphicsSceneHoverEnter
        if entered
        else QEvent.Type.GraphicsSceneHoverLeave
    )
    timeline_ui.scene.sendEvent(label, QGraphicsSceneHoverEvent(event_type))


def patch_beat_unit_dialog(
    denominator: int | None = None,
    units: str | None = None,
    only_this_measure: bool = False,
    cancel: bool = False,
    on_exec=None,
):
    """
    Makes the beat unit dialog take the given values (keeping any left as
    None) and press OK, or press Cancel. `on_exec(dialog)` runs first.
    """

    def exec_(dialog):
        if on_exec:
            on_exec(dialog)
        if cancel:
            return QDialog.DialogCode.Rejected
        if denominator is not None:
            dialog.denominator_edit.setValue(denominator)
        if units is not None:
            dialog.units_edit.clear()
            QTest.keyClicks(dialog.units_edit, units)
        if only_this_measure:
            dialog.measure_option.click()
        dialog.ok_button.click()
        return dialog.result()

    return patch.object(BeatUnitDialog, "exec", new=exec_)


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


@contextmanager
def patch_beat_unit_scope_prompt(answer: str | None):
    """
    Answers the inspector's "Where should this change apply?" prompt by
    pressing "onward", "measure" (this measure only) or, for None, Cancel.
    Yields a list of the prompts' texts, so tests can count them.
    """
    shown = []
    button_texts = {
        "onward": strings.BEAT_UNIT_SCOPE_ONWARD,
        "measure": strings.BEAT_UNIT_SCOPE_MEASURE,
    }

    def exec_(box):
        shown.append(box.text())
        if answer is None:
            box.button(QMessageBox.StandardButton.Cancel).click()
            return
        button = next(b for b in box.buttons() if b.text() == button_texts[answer])
        button.click()

    with patch.object(QMessageBox, "exec", new=exec_):
        yield shown
