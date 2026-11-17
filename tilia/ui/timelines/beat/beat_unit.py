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
    time signature labels of those measures, and each label is selected on
    its own: clicking a label selects it, Ctrl-clicking adds or removes it,
    and a selection box selects every label it goes over. The beat unit is
    selected while any of its labels is, and outlines the selected ones, or,
    when it is selected without any, the one where it starts. The inspector
    edits the time signature of the label last clicked, or else of the first
    selected one.
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
        self._labels_by_measure: dict[int, TimeSignatureLabel] = {}
        self.hover_line: QGraphicsLineItem | None = None
        self._is_selected = False
        # While selected: the selected labels, as the first beats of their
        # measures and those measures. Kept by beat, so a selected label
        # follows its measure when barlines move (see `_keep_selection`).
        self._selected: dict[int | str, int] = {}
        # The first beat of the measure whose label was clicked last, while
        # that label is selected (see `active_measure_index`).
        self._clicked_beat_id: int | str | None = None
        # The measures whose labels are outlined, so that a change of
        # selection redraws only the labels it changes.
        self._outlined: set[int] = set()
        # The measure the inspector was last given (see `get_inspector_dict`).
        self._shown_measure_index: int | None = None
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
            self._labels_by_measure[label.measure_index] = label
        self._keep_selection()
        self._on_selection_changed()

    def _remove_labels(self) -> None:
        self._remove_hover_line()
        for label in self.labels:
            self.scene.removeItem(label.body)
            self.scene.removeItem(label)
        self.labels = []
        self._labels_by_measure = {}
        self._outlined = set()

    def get_label(self, measure_index: int) -> TimeSignatureLabel | None:
        return self._labels_by_measure.get(measure_index)

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

    @property
    def active_measure_index(self) -> int | None:
        """
        The measure of the label clicked last, which beat unit commands
        apply to, while that label is selected. It is kept by the beat that
        starts the measure, so it follows the measure when barlines move.
        """
        if self._clicked_beat_id is None:
            return None
        measure_index = self._selected.get(self._clicked_beat_id)
        if measure_index is None or not self._is_measure(measure_index):
            return None
        return measure_index

    @property
    def selected_measure_indices(self) -> list[int]:
        """The measures whose labels are selected, in order."""
        return sorted(self._selected.values())

    @property
    def outlined_measure_indices(self) -> list[int]:
        """
        The measures whose labels are outlined, in order: the selected ones,
        or, while the beat unit is selected without any, the one where it
        starts. Deleting the selection acts on these.
        """
        return sorted(self._outlined)

    def _is_measure(self, measure_index: int) -> bool:
        return measure_index < self.timeline_ui.timeline.measure_count

    def _get_first_beat_id(self, label: TimeSignatureLabel) -> int | str:
        timeline = self.timeline_ui.timeline
        return timeline[timeline.beats_that_start_measures[label.measure_index]].id

    def _keep_selection(self) -> None:
        """
        Keeps selected the labels this beat unit still has once they are
        drawn again: those of the measures their first beats still start.
        """
        timeline = self.timeline_ui.timeline
        selected = {}
        for beat_id in self._selected:
            measure_index = timeline.get_measure_started_by(beat_id)
            if measure_index in self._labels_by_measure:
                selected[beat_id] = measure_index
        self._selected = selected
        if self._clicked_beat_id not in selected:
            self._clicked_beat_id = None

    def select_label(self, label: TimeSignatureLabel, clicked: bool = True) -> None:
        """
        Adds a label to the selection, while the beat unit is selected. A
        clicked label becomes the one the inspector and commands act on.
        """
        if not self._is_selected:
            return
        beat_id = self._get_first_beat_id(label)
        self._selected[beat_id] = label.measure_index
        if clicked:
            self._clicked_beat_id = beat_id
        self._on_selection_changed()

    def deselect_label(self, label: TimeSignatureLabel) -> bool:
        """
        Removes a label from the selection. Returns whether any label is
        still selected.
        """
        beat_id = self._get_first_beat_id(label)
        self._selected.pop(beat_id, None)
        if self._clicked_beat_id == beat_id:
            self._clicked_beat_id = None
        self._on_selection_changed()
        return bool(self._selected)

    def toggle_label(self, label: TimeSignatureLabel) -> bool:
        """
        Deselects a label if it is outlined, else selects it, as Ctrl-clicking
        it does. Returns whether any label is still selected.
        """
        if not self._selected:
            # Selected without any label: the outlined one counts as selected.
            for measure_index in list(self._outlined):
                self.select_label(self._labels_by_measure[measure_index], False)
        if self.is_outlined(label):
            return self.deselect_label(label)
        self.select_label(label)
        return True

    def is_outlined(self, label: TimeSignatureLabel) -> bool:
        return self._labels_by_measure.get(label.measure_index) is label and (
            label.measure_index in self._outlined
        )

    def on_selection_box_select(self, item: QGraphicsItem) -> None:
        if isinstance(item, TimeSignatureLabel):
            self.select_label(item, clicked=False)

    def on_selection_box_deselect(self, item: QGraphicsItem) -> None:
        if isinstance(item, TimeSignatureLabel):
            self.deselect_label(item)

    def _get_outlined(self) -> set[int]:
        if not self._is_selected or not self.labels:
            return set()
        if self._selected:
            return set(self._selected.values())
        start = self.start_measure_index
        if start in self._labels_by_measure:
            return {start}
        return {self.labels[0].measure_index}

    def _redraw_outline(self) -> None:
        """
        Outlines the selected labels, redrawing only those whose outline
        changes, as a selection box changes the selection once for each label
        it goes over.
        """
        outlined = self._get_outlined()
        for measure_index in outlined ^ self._outlined:
            label = self._labels_by_measure.get(measure_index)
            if label is not None:
                label.set_outlined(measure_index in outlined)
        self._outlined = outlined

    def _on_selection_changed(self) -> None:
        """Redraws the outline, and refreshes the inspector if its measure moved."""
        self._redraw_outline()
        if self._is_selected and (
            self.inspected_measure_index != self._shown_measure_index
        ):
            self._refresh_inspector()

    def on_left_click(self, item: QGraphicsItem) -> None:
        # A click selects the label alone, as the timeline UI deselects the
        # others first, and Shift-click adds it. Ctrl-click is the timeline
        # UI's (see `BeatTimelineUI.on_left_click`).
        if isinstance(item, TimeSignatureLabel):
            self.select_label(item)

    def on_double_left_click(self, item: QGraphicsItem) -> None:
        self.on_left_click(item)
        commands.execute("timeline.beat.edit_bars")

    def on_right_click(self, x: int, y: int, item: QGraphicsItem) -> None:
        # The menu acts on the selection if the label is in it, and on the
        # label alone if it is not.
        if isinstance(item, TimeSignatureLabel):
            if not self.is_outlined(item):
                self._selected.clear()
            self.select_label(item)
        super().on_right_click(x, y, item)

    @property
    def start_measure_index(self) -> int:
        timeline = self.timeline_ui.timeline
        beat = timeline.get_component(self.get_data("beat_id"))
        return timeline.get_measure_index(timeline.get_beat_index(beat))[0]

    @property
    def inspected_measure_index(self) -> int:
        """
        The measure of the label clicked last, or else of the first selected
        one, or else where the beat unit starts.
        """
        active = self.active_measure_index
        if active is not None:
            return active
        if self._selected:
            first = min(self._selected.values())
            if self._is_measure(first):
                return first
        return self.start_measure_index

    def _get_inspected_bar(self, beat_count: int | None = None) -> PlannedBar:
        """The inspected measure, over `beat_count` beats or the ones it has."""
        return self.timeline_ui.timeline.get_measure_as_planned_bar(
            self.inspected_measure_index, beat_count
        )

    def get_inspector_dict(self) -> dict:
        timeline = self.timeline_ui.timeline
        measure_index = self.inspected_measure_index
        self._shown_measure_index = measure_index
        bar = timeline.get_measure_as_planned_bar(measure_index)
        return {
            "Time signature": format_time_signature(bar),
            "Taps": format_taps(bar),
            "Measure": str(timeline.measure_numbers[measure_index]),
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

        beat_count = timeline.get_beat_count_to_set(value, measure_index)
        bar, error = parse_time_signature_over_taps(value, beat_count)
        if bar is not None and bar.beat_count != beat_count:
            error = tilia.ui.strings.TIME_SIGNATURE_TAPS_ERROR.format(
                beat_count, "" if beat_count == 1 else "s"
            )
        if bar is None or error:
            tilia.errors.display(tilia.errors.INVALID_TIME_SIGNATURE, error)
            self._refresh_inspector()
            return

        edit = (bar.denominator, bar.units_text)
        if bar == self._get_inspected_bar(beat_count) or self._pending_edit == edit:
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
            if self.is_selected() and self.get_label(measure_index) is None:
                # The measure has a beat unit of its own now, whose label it
                # is: select that, so the measure stays the one inspected.
                self.timeline_ui.select_time_signature_label(measure_index)
            else:
                self._refresh_inspector()
        finally:
            self._pending_edit = None

    def _refresh_inspector(self) -> None:
        # The click that ended the edit may have selected something else,
        # whose inspector must not be replaced by this one.
        if self.is_selected():
            self.timeline_ui.post_inspectable_selected_event(self)

    def on_select(self) -> None:
        # Selecting the beat unit gives the inspector its values, so only the
        # outline is drawn here.
        self._is_selected = True
        self._redraw_outline()

    def on_deselect(self) -> None:
        self._is_selected = False
        self._selected.clear()
        self._clicked_beat_id = None
        self._shown_measure_index = None
        self._redraw_outline()

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
