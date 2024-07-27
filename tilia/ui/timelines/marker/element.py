from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPolygonF, QPen, QColor, QFont
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
)

from tilia.requests import Post, post, get, Get
from .context_menu import MarkerContextMenu
from ..copy_paste import CopyAttributes
from ..cursors import CursorMixIn
from ..drag import DragManager
from ...color import get_tinted_color
from ...format import format_media_time
from ...consts import TINT_FACTOR_ON_SELECTION
from ...coords import get_x_by_time, get_time_by_x
from tilia.settings import settings
from tilia.ui.timelines.base.element import TimelineUIElement
from ...windows.inspect import InspectRowKind

if TYPE_CHECKING:
    from .timeline import MarkerTimelineUI


class MarkerUI(TimelineUIElement):
    LABEL_MARGIN = 3

    INSPECTOR_FIELDS = [
        ("Label", InspectRowKind.SINGLE_LINE_EDIT, None),
        ("Time", InspectRowKind.LABEL, None),
        ("Comments", InspectRowKind.MULTI_LINE_EDIT, None),
    ]

    FIELD_NAMES_TO_ATTRIBUTES = {"Label": "label", "Comments": "comments"}

    DEFAULT_COPY_ATTRIBUTES = CopyAttributes(
        by_element_value=[],
        by_component_value=["comments", "label", "color"],
        support_by_element_value=[],
        support_by_component_value=["time"],
    )

    UPDATE_TRIGGERS = ["time", "label", "color"]

    CONTEXT_MENU_CLASS = MarkerContextMenu

    def __init__(
        self,
        id: int,
        timeline_ui: MarkerTimelineUI,
        scene: QGraphicsScene,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)

        self._setup_body()
        self._setup_label()

        self.dragged = False
        self.drag_manager = None

    def _setup_body(self):
        self.body = MarkerBody(self.x, self.width, self.height, self.ui_color)
        self.scene.addItem(self.body)

    def _setup_label(self):
        self.label = MarkerLabel(self.x, self.label_y, self.get_data("label"))
        self.scene.addItem(self.label)

    @property
    def x(self):
        return get_x_by_time(self.get_data("time"))

    @property
    def label_y(self):
        return self.height - self.LABEL_MARGIN

    @property
    def seek_time(self):
        return self.get_data("time")

    @property
    def width(self):
        return settings.get("marker_timeline", "marker_width")

    @property
    def height(self):
        return settings.get("marker_timeline", "marker_height")

    @property
    def default_color(self):
        return settings.get("marker_timeline", "default_color")

    @property
    def ui_color(self):
        base_color = self.get_data("color") or self.default_color
        return (
            base_color
            if not self.is_selected()
            else get_tinted_color(base_color, TINT_FACTOR_ON_SELECTION)
        )

    def update_label(self):
        self.label.set_text(self.get_data("label"))
        self.label.set_position(self.x, self.label_y)

    def update_color(self):
        self.body.set_fill(self.ui_color)

    def update_position(self):
        self.update_time()

    def update_time(self):
        self.body.set_position(self.x, self.width, self.height)
        self.label.set_position(self.x, self.label_y)

    def child_items(self):
        return [self.body, self.label]

    def left_click_triggers(self) -> list[QGraphicsItem]:
        return [self.body, self.label]

    def on_left_click(self, _) -> None:
        self.setup_drag()

    def double_left_click_triggers(self):
        return [self.body, self.label]

    def on_double_left_click(self, _):
        if self.drag_manager:
            self.drag_manager.on_release()
            self.drag_manager = None
        post(Post.PLAYER_SEEK, self.seek_time)

    def setup_drag(self):
        self.drag_manager = DragManager(
            get_min_x=lambda: get(Get.LEFT_MARGIN_X),
            get_max_x=lambda: get(Get.RIGHT_MARGIN_X),
            before_each=self.before_each_drag,
            after_each=self.after_each_drag,
            on_release=self.on_drag_end,
        )

    def before_each_drag(self):
        if not self.dragged:
            post(Post.ELEMENT_DRAG_START)
            self.dragged = True

    def after_each_drag(self, drag_x: int):
        self.set_data("time", get_time_by_x(drag_x))

    def on_drag_end(self):
        if self.dragged:
            post(Post.APP_RECORD_STATE, "marker drag")
            post(Post.ELEMENT_DRAG_END)

        self.dragged = False

    def on_select(self) -> None:
        self.body.on_select()

    def on_deselect(self) -> None:
        self.body.on_deselect()

    def get_inspector_dict(self) -> dict:
        return {
            "Label": self.get_data("label"),
            "Time": format_media_time(self.get_data("time")),
            "Comments": self.get_data("comments"),
        }


class MarkerBody(CursorMixIn, QGraphicsPolygonItem):
    def __init__(self, x: float, width: float, height: float, color: str):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.set_position(x, width, height)
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

    def set_position(self, x, width, height):
        self.setPolygon(self.get_polygon(x, width, height))

    def on_select(self):
        self.set_pen_style_solid()
        self.setBrush(self.brush().color().darker(TINT_FACTOR_ON_SELECTION))

    def on_deselect(self):
        self.set_pen_style_no_pen()
        self.setBrush(self.brush().color().lighter(TINT_FACTOR_ON_SELECTION))

    @staticmethod
    def get_polygon(x, width, height):
        return QPolygonF(
            [
                QPointF(x - width / 2, height),
                QPointF(x, 0),
                QPointF(x + width / 2, height),
            ]
        )


class MarkerLabel(QGraphicsTextItem):
    def __init__(self, x: float, y: float, text: str):
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
        self.setPlainText(value)
