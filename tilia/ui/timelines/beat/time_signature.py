"""Time signature labels drawn on the beat timeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsSceneHoverEvent

from tilia.requests import Get, get
from tilia.ui.consts import (
    BEAT_TIMELINE_TIME_SIGNATURE_BAND_HEIGHT,
    BEAT_TIMELINE_TIME_SIGNATURE_DIGIT_HEIGHT,
)
from tilia.ui.timelines.time_signature_glyphs import TimeSignatureBody

# Vertical layout, below the beats and their measure numbers.
TIME_SIGNATURE_Y = 34
TIME_SIGNATURE_DIGIT_HEIGHT = BEAT_TIMELINE_TIME_SIGNATURE_DIGIT_HEIGHT
# Height added to the timeline while time signatures are shown.
TIME_SIGNATURE_BAND_HEIGHT = BEAT_TIMELINE_TIME_SIGNATURE_BAND_HEIGHT

CONFLICT_COLOR = QColor("#cc0000")
AMBIGUOUS_COLOR = QColor("#d98c00")
SELECTED_COLOR = QColor("#1f77b4")
# Time signatures the user hasn't confirmed are drawn faded.
ASSUMED_OPACITY = 0.5


class LabelState(Enum):
    NORMAL = auto()
    AMBIGUOUS = auto()
    CONFLICTING = auto()


@dataclass(frozen=True)
class TimeSignatureLabelSpec:
    measure_index: int
    x: float
    numerator: str
    denominator: str
    state: LabelState
    tooltip: str = ""
    assumed: bool = False


class TimeSignatureLabel(QGraphicsRectItem):
    """
    A clickable box around a time signature. The box sits above the glyphs
    so clicks land on it, and outlines the label when its beat unit is
    selected.
    """

    def __init__(
        self,
        spec: TimeSignatureLabelSpec,
        pixmaps: dict,
        on_hover: Callable[[TimeSignatureLabel, bool], None] | None = None,
    ):
        super().__init__()
        self.spec = spec
        self.on_hover = on_hover
        self.body = TimeSignatureBody(
            0,
            0,
            spec.numerator,
            spec.denominator,
            TIME_SIGNATURE_DIGIT_HEIGHT,
            pixmaps,
            self._get_color(spec.state),
        )
        self.body.setZValue(self.zValue() - 1)
        if spec.assumed:
            self.body.setOpacity(ASSUMED_OPACITY)
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.set_selected(False)
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        self.setAcceptHoverEvents(True)
        self.set_position(spec.x)

    @staticmethod
    def _get_color(state: LabelState) -> QColor | None:
        return {
            LabelState.NORMAL: None,
            LabelState.AMBIGUOUS: AMBIGUOUS_COLOR,
            LabelState.CONFLICTING: CONFLICT_COLOR,
        }[state]

    @property
    def measure_index(self) -> int:
        return self.spec.measure_index

    def set_position(self, x: float) -> None:
        # Centered on the measure's first beat, but kept out of the view's
        # margins, where it would be clipped.
        width = self.body.width
        left = x - width / 2
        left = min(left, get(Get.RIGHT_MARGIN_X) - width)
        left = max(left, get(Get.LEFT_MARGIN_X))
        self.body.set_position(left, TIME_SIGNATURE_Y)
        self.setRect(
            QRectF(
                left - 1,
                TIME_SIGNATURE_Y - 1,
                self.body.width + 2,
                2 * TIME_SIGNATURE_DIGIT_HEIGHT + 2,
            )
        )

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.setPen(QPen(SELECTED_COLOR, 1))
        else:
            self.setPen(Qt.PenStyle.NoPen)

    def items(self) -> list:
        return [self, self.body]

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        if self.on_hover:
            self.on_hover(self, True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        if self.on_hover:
            self.on_hover(self, False)
        super().hoverLeaveEvent(event)
