from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt, QRectF
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsRectItem,
)

from tilia.requests import Post, post
from . import attrs
from ..cursors import CursorMixIn
from ...color import get_tinted_color, get_untinted_color
from ...format import format_media_time
from ...consts import TINT_FACTOR_ON_SELECTION
from ...coords import get_x_by_time
from tilia.settings import settings
from tilia.ui.timelines.base.element import TimelineUIElement

if TYPE_CHECKING:
    from .timeline import NoteTimelineUI


class NoteUI(TimelineUIElement):
    LABEL_MARGIN = 3

    INSPECTOR_FIELDS = attrs.INSPECTOR_FIELDS

    FIELD_NAMES_TO_ATTRIBUTES = attrs.FIELD_NAMES_TO_ATTRIBUTES

    UPDATE_TRIGGERS = ["color"]

    CONTEXT_MENU_CLASS = None

    def __init__(
        self,
        id: int,
        timeline_ui: NoteTimelineUI,
        scene: QGraphicsScene,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)

        self._setup_body()

    def _setup_body(self):
        self.body = NoteBody(self.start_x, self.end_x, self.top_y, self.ui_color)
        self.scene.addItem(self.body)
        
    @property
    def start_x(self):
        return get_x_by_time(self.get_data("start"))
    
    @property
    def end_x(self):
        return get_x_by_time(self.get_data("end"))
    
    @property
    def top_y(self):
        note_height = self.note_height()
        middle_y = self.timeline_ui.get_data('height') / 2
        note_offset = (self.get_data('step') - 6) * note_height
        octave_offset = (self.get_data('octave') - 3) * note_height * 7
        return middle_y - note_offset - octave_offset
    
    @property
    def seek_time(self):
        return self.get_data("start")

    @classmethod
    def note_height(cls):
        return settings.get("score_timeline", "note_height")


    @property
    def default_color(self):
        return settings.get("score_timeline", "default_note_color")

    @property
    def ui_color(self):
        base_color = self.get_data("color") or self.default_color
        return (
            base_color
            if not self.is_selected()
            else get_tinted_color(base_color, TINT_FACTOR_ON_SELECTION)
        )

    def update_color(self):
        self.body.set_fill(self.ui_color)

    def update_position(self):
        self.update_time()

    def update_time(self):
        self.body.set_position(self.start_x, self.end_x, self.top_y)

    def child_items(self):
        return [self.body]

    def left_click_triggers(self) -> list[QGraphicsItem]:
        return [self.body]

    def on_left_click(self, _) -> None:
        pass

    def double_left_click_triggers(self):
        return [self.body]

    def on_double_left_click(self, _):
        post(Post.PLAYER_SEEK, self.seek_time)

    def on_select(self) -> None:
        self.body.on_select()

    def on_deselect(self) -> None:
        self.body.on_deselect()

    def get_inspector_dict(self) -> dict:
        return {
            "Start": format_media_time(self.get_data("start")),
            "End": format_media_time(self.get_data('end')),
            "Pitch class": self.get_data('pitch_class'),
            "Comments": self.get_data("comments"),
        }


class NoteBody(CursorMixIn, QGraphicsRectItem):
    X_OFFSET = 1
    Y_OFFSET = 1

    def __init__(
        self, start_x: float, end_x: float, top_y: float, color: str
    ):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.set_position(start_x, end_x, top_y)
        self.set_pen_style_no_pen()
        self.set_fill(color)

    def set_fill(self, color: str):
        self.setBrush(QColor(color))

    def set_pen_style_solid(self):
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.SolidLine)
        self.setPen(pen)

    def set_pen_style_no_pen(self):
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.NoPen)
        self.setPen(pen)

    def set_position(self, start_x: float, end_x: float, top_y: float):
        self.setRect(self.get_rect(start_x, end_x, top_y))

    def on_select(self):
        self.set_pen_style_solid()
        self.setBrush(
            QColor(get_tinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )

    def on_deselect(self):
        self.set_pen_style_no_pen()
        self.setBrush(
            QColor(get_untinted_color(self.brush().color(), TINT_FACTOR_ON_SELECTION))
        )

    def get_rect(self, start_x: float, end_x: float, top_y: float) -> QRectF:
        x0 = start_x + self.X_OFFSET
        y0 = top_y + self.Y_OFFSET / 2
        x1 = end_x - self.X_OFFSET
        y1 = top_y + NoteUI.note_height() - self.Y_OFFSET / 2
        return QRectF(QPointF(x0, y0), QPointF(x1, y1))
