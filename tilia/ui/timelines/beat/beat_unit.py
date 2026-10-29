from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QLineF, QPointF, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsScene

import tilia.errors
import tilia.ui.strings
from tilia.requests import Get, Post, get, post
from tilia.timelines.beat.pattern import (
    PlannedBar,
    format_taps,
    format_time_signature,
    parse_time_signature_over_taps,
)
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.beat.context_menu import BeatUnitContextMenu
from tilia.ui.timelines.beat.time_signature import (
    SELECTED_COLOR,
    TIME_SIGNATURE_Y,
    TimeSignatureLabel,
    TimeSignatureLabelSpec,
)
from tilia.ui.windows.beat_pattern import BeatPatternValidator
from tilia.ui.windows.inspect import InspectRowKind

if TYPE_CHECKING:
    from tilia.ui.timelines.beat.timeline import BeatTimelineUI

# How often to check whether the mouse has been released.
_MOUSE_RELEASE_POLL_MS = 20


def _call_once_mouse_is_released(callback: Callable[[], None]) -> None:
    """Calls `callback` from the event loop, once no mouse button is held."""

    def attempt() -> None:
        if QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton:
            QTimer.singleShot(_MOUSE_RELEASE_POLL_MS, attempt)
            return
        callback()

    QTimer.singleShot(0, attempt)


class BeatUnitUI(TimelineUIElement):
    """
    A beat unit, which gives the taps of the measures it governs their
    values, has no mark of its own: it is shown, and selected, through the
    time signature labels of those measures. The inspector edits the time
    signature of the measure whose label was clicked.
    """

    UPDATE_TRIGGERS = ["denominator", "units", "beat_id", "assumed"]
    CONTEXT_MENU_CLASS = BeatUnitContextMenu

    INSPECTOR_FIELDS = [
        (
            "Time signature",
            InspectRowKind.SINGLE_LINE_EDIT_ON_FINISH,
            lambda: {"validator": BeatPatternValidator},
        ),
        ("Taps", InspectRowKind.LABEL, None),
        ("Measure", InspectRowKind.LABEL, None),
        ("Assumed", InspectRowKind.LABEL, None),
    ]
    FIELD_NAMES_TO_ATTRIBUTES: dict[str, str] = {}

    def __init__(
        self,
        id: int,
        timeline_ui: BeatTimelineUI,
        scene: QGraphicsScene,
        get_data: Callable[[str], Any],
        set_data: Callable[[str, Any], None],
        **_,
    ) -> None:
        super().__init__(
            id=id,
            timeline_ui=timeline_ui,
            scene=scene,
            get_data=get_data,
            set_data=set_data,
        )
        self.labels: list[TimeSignatureLabel] = []
        self.hover_line: QGraphicsLineItem | None = None
        self._is_selected = False
        # The measure of the label last clicked, which beat unit commands
        # apply to.
        self.active_measure_index: int | None = None
        # An inspector edit waiting for the mouse to be released, so the same
        # edit reported twice asks once.
        self._pending_edit: tuple[str, Any] | None = None

    def set_labels(self, specs: list[TimeSignatureLabelSpec]) -> None:
        self._remove_labels()
        for spec in specs:
            label = TimeSignatureLabel(
                spec, self.timeline_ui.time_signature_pixmaps, self.on_label_hover
            )
            self.scene.addItem(label.body)
            self.scene.addItem(label)
            self.labels.append(label)
        self._update_highlight()

    def _remove_labels(self) -> None:
        self._remove_hover_line()
        for label in self.labels:
            self.scene.removeItem(label.body)
            self.scene.removeItem(label)
        self.labels = []

    def get_label(self, measure_index: int) -> TimeSignatureLabel | None:
        return next(
            (lb for lb in self.labels if lb.measure_index == measure_index), None
        )

    @property
    def beat_x(self) -> float | None:
        beat = self.timeline_ui.timeline.get_component(self.get_data("beat_id"))
        return time_x_converter.get_x_by_time(beat.time) if beat else None

    def on_label_hover(self, label: TimeSignatureLabel, entered: bool) -> None:
        self._remove_hover_line()
        if not entered or self.beat_x is None:
            return
        rect = label.rect()
        start = QPointF(rect.center().x(), TIME_SIGNATURE_Y)
        end = QPointF(self.beat_x, self.timeline_ui.beat_bottom_y)
        self.hover_line = QGraphicsLineItem(QLineF(start, end))
        pen = QPen(SELECTED_COLOR, 1)
        pen.setStyle(Qt.PenStyle.DotLine)
        self.hover_line.setPen(pen)
        self.scene.addItem(self.hover_line)

    def _remove_hover_line(self) -> None:
        if self.hover_line is not None:
            self.scene.removeItem(self.hover_line)
            self.hover_line = None

    def child_items(self) -> list:
        items = [item for label in self.labels for item in label.items()]
        if self.hover_line is not None:
            items.append(self.hover_line)
        return items

    def selection_triggers(self) -> list:
        return list(self.labels)

    def left_click_triggers(self) -> list:
        return list(self.labels)

    def right_click_triggers(self) -> list:
        return list(self.labels)

    def double_left_click_triggers(self) -> list:
        return list(self.labels)

    def _set_active_label(self, item: QGraphicsItem) -> None:
        if isinstance(item, TimeSignatureLabel):
            self.active_measure_index = item.measure_index
            self._update_highlight()

    def _get_highlighted_label(self) -> TimeSignatureLabel | None:
        """
        The label the selection is shown on: the one last clicked, or, if it
        is gone or none was clicked, the one where the beat unit starts.
        """
        if not self.labels:
            return None
        if self.active_measure_index is not None:
            label = self.get_label(self.active_measure_index)
            if label is not None:
                return label
        return self.get_label(self.start_measure_index) or self.labels[0]

    def _update_highlight(self) -> None:
        highlighted = self._get_highlighted_label() if self._is_selected else None
        for label in self.labels:
            label.set_selected(label is highlighted)

    def on_left_click(self, item: QGraphicsItem) -> None:
        self._set_active_label(item)

    def on_double_left_click(self, item: QGraphicsItem) -> None:
        self._set_active_label(item)
        commands.execute("timeline.beat.edit_bars")

    def on_right_click(self, x: int, y: int, item: QGraphicsItem) -> None:
        self._set_active_label(item)
        super().on_right_click(x, y, item)

    @property
    def start_measure_index(self) -> int:
        timeline = self.timeline_ui.timeline
        beat = timeline.get_component(self.get_data("beat_id"))
        return timeline.get_measure_index(timeline.get_beat_index(beat))[0]

    @property
    def inspected_measure_index(self) -> int:
        """The measure whose label was clicked, or where the beat unit starts."""
        if self.active_measure_index is not None:
            return self.active_measure_index
        return self.start_measure_index

    def _get_inspected_bar(self) -> PlannedBar:
        timeline = self.timeline_ui.timeline
        bar = timeline.get_measures_as_planned_bars()[self.inspected_measure_index]
        return PlannedBar.from_values(bar.values, bar.denominator)

    def get_inspector_dict(self) -> dict:
        timeline = self.timeline_ui.timeline
        bar = self._get_inspected_bar()
        return {
            "Time signature": format_time_signature(bar),
            "Taps": format_taps(bar),
            "Measure": str(timeline.measure_numbers[self.inspected_measure_index]),
            "Assumed": "Yes" if self.get_data("assumed") else "No",
        }

    def on_inspector_edit(self, field_name: str, value: str) -> None:
        """
        Sets the time signature of the measure whose label was clicked, over
        its taps, asking first whether it applies there only or to the alike
        measures after it too.
        """
        measure_index = self.inspected_measure_index
        timeline = self.timeline_ui.timeline
        if field_name != "Time signature" or measure_index >= timeline.measure_count:
            return

        beat_count = timeline.get_full_beat_count(measure_index)
        bar, error = parse_time_signature_over_taps(value, beat_count)
        if bar is not None and bar.beat_count != beat_count:
            error = tilia.ui.strings.TIME_SIGNATURE_TAPS_ERROR.format(beat_count)
        if bar is None or error:
            tilia.errors.display(tilia.errors.INVALID_TIME_SIGNATURE, error)
            self._refresh_inspector()
            return

        edit = (bar.denominator, bar.units_text)
        if bar == self._get_inspected_bar() or self._pending_edit == edit:
            return

        self._pending_edit = edit
        # Editing often finishes because the user clicked elsewhere. The
        # scope question is modal, and opening it inside that mouse press
        # keeps the view from ever seeing the release (its selection box
        # stays up). Ask once the mouse is released instead.
        _call_once_mouse_is_released(
            lambda: self._apply_inspector_edit(value, measure_index)
        )

    def _apply_inspector_edit(self, value: str, measure_index: int) -> None:
        try:
            if self.id not in self.timeline_ui.id_to_element:
                return  # deleted in the meantime
            timeline = self.timeline_ui.timeline
            if measure_index >= timeline.measure_count:
                return

            stop = timeline.get_alike_measures_end(measure_index)
            if stop > measure_index + 1:
                accepted, only_this_measure = get(Get.FROM_USER_BEAT_UNIT_SCOPE)
                if not accepted:
                    self._refresh_inspector()
                    return
                if only_this_measure:
                    stop = measure_index + 1

            error = timeline.set_time_signature(value, measure_index, stop)
            if error:
                tilia.errors.display(tilia.errors.INVALID_TIME_SIGNATURE, error)
            else:
                post(Post.APP_STATE_RECORD, "time signature edit via inspect")
            self._refresh_inspector()
        finally:
            self._pending_edit = None

    def _refresh_inspector(self) -> None:
        # The click that ended the edit may have selected something else,
        # whose inspector must not be replaced by this one.
        if self.is_selected():
            self.timeline_ui.post_inspectable_selected_event(self)

    def on_select(self) -> None:
        self._is_selected = True
        self._update_highlight()

    def on_deselect(self) -> None:
        self._is_selected = False
        self._update_highlight()

    def update_position(self) -> None:
        # Labels are positioned by BeatTimelineUI.update_time_signatures,
        # once for all beat units, when the timeline's times change.
        pass

    def update_denominator(self) -> None:
        self.timeline_ui.update_time_signatures()

    def update_units(self) -> None:
        self.timeline_ui.update_time_signatures()

    def update_beat_id(self) -> None:
        self.timeline_ui.update_time_signatures()

    def update_assumed(self) -> None:
        self.timeline_ui.update_time_signatures()

    def delete(self) -> None:
        self._remove_labels()
        super().delete()
