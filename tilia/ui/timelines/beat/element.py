from __future__ import annotations
from typing import TYPE_CHECKING, Callable, Any

from PyQt6.QtCore import Qt, QLineF, QPointF
from PyQt6.QtGui import QPen, QColor, QFont
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsLineItem, QGraphicsTextItem

from tilia.requests import Post, post, Get, get
from .context_menu import BeatContextMenu
from ..copy_paste import CopyAttributes
from ..cursors import CursorMixIn
from ..drag import DragManager
from ...format import format_media_time
from ...coords import time_x_converter
from tilia.ui.timelines.base.element import TimelineUIElement
from ...windows.inspect import InspectRowKind

if TYPE_CHECKING:
    from .timeline import BeatTimelineUI


class BeatUI(TimelineUIElement):
    WIDTH_THIN = 1
    WIDTH_THICK = 3
    HEIGHT_SHORT = 7
    HEIGHT_TALL = 15

    FILL = "gray"
    FIRST_IN_MEASURE_FILL = "black"

    UPDATE_TRIGGERS = ["is_first_in_measure", "time"]

    LABEL_MARGIN = 0

    DRAG_PROXIMITY_LIMIT = 2

    INSPECTOR_FIELDS = [
        ("Time", InspectRowKind.LABEL, None),
        ("Measure", InspectRowKind.LABEL, None),
        ("Beat", InspectRowKind.LABEL, None),
    ]

    FIELD_NAMES_TO_ATTRIBUTES: dict[str, str] = (
        {}
    )  # only needed if attrs will be set by Inspect

    DEFAULT_COPY_ATTRIBUTES = CopyAttributes(
        by_element_value=[],
        by_component_value=[],
        support_by_element_value=[],
        support_by_component_value=["time"],
    )

    CONTEXT_MENU_CLASS = BeatContextMenu

    def __init__(
        self,
        id: int,
        timeline_ui: BeatTimelineUI,
        scene: QGraphicsScene,
        get_data: Callable[[str], Any],
        set_data: Callable[[str, Any], None],
        **_,
    ):
        super().__init__(
            id=id,
            timeline_ui=timeline_ui,
            scene=scene,
            get_data=get_data,
            set_data=set_data,
        )

        self._setup_body()
        self._setup_label()

        self.dragged = False
        self.drag_manager = None

    def _setup_body(self):
        self.body = BeatBody(self.x, self.height)
        self.scene.addItem(self.body)

    def _setup_label(self):
        self.label = BeatLabel(self.x, self.label_y, self.text)
        self.scene.addItem(self.label)

    @property
    def time(self):
        return self.tl_component.time

    @property
    def label_y(self):
        return self.height + self.LABEL_MARGIN

    @property
    def text(self):
        if self.get_data(
            "is_first_in_measure"
        ) and self.timeline_ui.should_display_measure_number(self):
            return str(self.get_data("measure"))
        else:
            return ""

    @property
    def height(self):
        return (
            self.HEIGHT_TALL
            if self.get_data("is_first_in_measure")
            else self.HEIGHT_SHORT
        )

    @property
    def seek_time(self):
        return self.time

    def child_items(self):
        return self.body, self.label

    def update_time(self):
        self.update_position()

    def update_position(self):
        self.body.set_position(self.x, self.height)
        self.label.set_position(self.x, self.height)

    def update_is_first_in_measure(self) -> None:
        self.body.set_position(self.x, self.height)
        self.update_label()

    def update_label(self):
        self.label.set_text(self.text)
        self.label.set_position(self.x, self.label_y)

    def selection_triggers(self):
        return self.body, self.label

    def left_click_triggers(self):
        return (self.body,)

    def on_left_click(self, _) -> None:
        self.setup_drag()

    def double_left_click_triggers(self):
        return self.body, self.label

    def on_double_left_click(self, _) -> None:
        if self.drag_manager:
            self.drag_manager.on_release()
            self.drag_manager = None
        post(Post.PLAYER_SEEK, self.seek_time)

    @property
    def right_click_triggers(self):
        return self.body, self.label

    def setup_drag(self):
        self.drag_manager = DragManager(
            get_min_x=self.get_drag_left_limit,
            get_max_x=self.get_drag_right_limit,
            before_each=self.before_each_drag,
            after_each=self.after_each_drag,
            on_release=self.on_drag_end,
        )

    def get_drag_left_limit(self):
        previous_beat = self.timeline_ui.get_previous_element(self)
        if not previous_beat:
            return get(Get.LEFT_MARGIN_X)
        return (
            time_x_converter.get_x_by_time(previous_beat.time)
            + self.DRAG_PROXIMITY_LIMIT
        )

    def get_drag_right_limit(self):
        next_beat = self.timeline_ui.get_next_element(self)
        if not next_beat:
            return get(Get.RIGHT_MARGIN_X)
        return (
            time_x_converter.get_x_by_time(next_beat.time) - self.DRAG_PROXIMITY_LIMIT
        )

    def before_each_drag(self):
        if not self.dragged:
            post(Post.ELEMENT_DRAG_START)
            self.dragged = True

    def after_each_drag(self, drag_x: int):
        self.set_data("time", time_x_converter.get_time_by_x(drag_x))
        self.update_position()

    def on_drag_end(self):
        if self.dragged:
            post(Post.APP_RECORD_STATE, "beat drag")
            post(Post.ELEMENT_DRAG_END)

        self.dragged = False

    def on_select(self) -> None:
        self.body.on_select()

    def on_deselect(self) -> None:
        self.body.on_deselect()

    def get_inspector_dict(self) -> dict:
        return {
            "Time": format_media_time(self.time),
            "Measure": str(self.get_data("measure")),
        }


class BeatBody(CursorMixIn, QGraphicsLineItem):
    def __init__(self, x: float, height: float):
        super().__init__(cursor_shape=Qt.CursorShape.SizeHorCursor)
        self.setLine(self.get_line(x, height))
        self.set_pen_style_default()

    def set_pen_style_default(self):
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setWidth(1)
        self.setPen(pen)

    def set_pen_style_thick(self):
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setWidth(3)
        self.setPen(pen)

    def set_position(self, x, height):
        self.setLine(self.get_line(x, height))

    def on_select(self):
        self.set_pen_style_thick()

    def on_deselect(self):
        self.set_pen_style_default()

    @staticmethod
    def get_line(x, height):
        return QLineF(QPointF(x, 0), QPointF(x, height))


class BeatLabel(QGraphicsTextItem):
    def __init__(
        self,
        x: float,
        y: float,
        text: str,
    ):
        super().__init__()
        self._setup_font()
        self.set_text(text)
        self.set_position(x, y)

    def _setup_font(self):
        font = QFont("Arial", 10)
        self.setFont(font)
        self.setDefaultTextColor(QColor("black"))

    def get_point(self, x: float, y: float):
        return QPointF(x - self.boundingRect().width() / 2, y)

    def set_position(self, x, y):
        self.setPos(self.get_point(x, y))

    def set_text(self, value: str):
        if not value:
            # Settting plain text to empty string
            # keeps the graphics item interactable,
            # so we need to hide it, instead.
            self.setVisible(False)
        else:
            self.setVisible(True)
            self.setPlainText(value)
