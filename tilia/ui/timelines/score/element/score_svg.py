from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtWidgets import QGraphicsRectItem

from tilia.requests import Post, post, get, Get
from tilia.ui.timelines.cursors import CursorMixIn
from tilia.ui.timelines.drag import DragManager
from tilia.ui.coords import time_x_converter
from tilia.ui.color import get_tinted_color
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.format import format_media_time
from tilia.settings import settings
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.windows.inspect import InspectRowKind

if TYPE_CHECKING:
    from ..timeline import ScoreTimelineUI


class ScoreSVGUI(TimelineUIElement):
    INSPECTOR_FILEDS = [
        ("Start / end", InspectRowKind.LABEL, None),
        ("Start / end (metric)", InspectRowKind.LABEL, None),
        ("Length", InspectRowKind.LABEL, None),
    ]
    UPDATE_TRIGGERS = [
        "start",
        "end",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._setup_body()
        self.dragged = False
        self.drag_extremity = None
        self.drag_manager = None

    @property
    def seek_time(self):
        return (self.get_data("start") + self.get_data("end")) / 2

    def child_items(self):
        return [
            self.body,
        ]

    def update(self, attr: str, _):
        if attr not in self.UPDATE_TRIGGERS:
            return

        update_func_name = "update_" + attr
        if not hasattr(self, update_func_name):
            raise ValueError(f"{self} has no updater function for attribute '{attr}'")

        getattr(self, update_func_name)()

    def update_end(self):
        self.update_position()

    def update_start(self):
        self.update_position()

    def update_position(self):
        start_x = self.start_x
        end_x = self.end_x
        height = self.timeline_ui.get_data("height")

        self.update_body_position(height, start_x, end_x)

    def update_body_position(self, height, start_x, end_x):
        self.body.set_position(
            start_x,
            end_x,
            height,
        )

    def _setup_body(self):
        self.body = MeasureBoxBody(
            self.start_x,
            self.end_x,
            self.timeline_ui.get_data("height"),
        )
        self.scene.addItem(self.body)

    def selection_triggers(self):
        return self.body

    def left_click_triggers(self):
        return self.body

    def on_left_click(self, _) -> None:
        self.setup_drag()

    def double_left_click_triggers(self):
        return self.left_click_triggers()

    def on_double_left_click(self, _) -> None:
        if self.drag_manager:
            self.drag_manager.on_release()
            self.drag_manager = None
        post(Post.PLAYER_SEEK, self.seek_time)

    def right_click_triggers(self):
        return self.body

    def setup_drag(self):
        self.drag_manager = DragManager(
            get_min_x=self.get_drag_left_limit,
            get_max_x=self.get_drag_right_limit,
            before_each=self.before_each_drag,
            after_each=self.after_each_drag,
            on_release=self.on_drag_end,
        )

    def get_drag_left_limit(self):
        return get(Get.LEFT_MARGIN_X)

    def get_drag_right_limit(self):
        return get(Get.RIGHT_MARGIN_X)

    def before_each_drag(self):
        if not self.dragged:
            post(Post.ELEMENT_DRAG_START)
            self.dragged = True

    def after_each_drag(self, drag_x: int):
        self.tl_component.time = time_x_converter.get_time_by_x(drag_x)
        self.update_position()

    def on_drag_end(self):
        if self.dragged:
            post(Post.APP_RECORD_STATE, "measure box drag")
            post(Post.ELEMENT_DRAG_END)

        self.dragged = False

    def on_select(self) -> None:
        self.body.on_select()

    def on_deselect(self) -> None:
        self.body.on_deselect()

    @property
    def start_and_end_formatted(self) -> str:
        return (
            f"{format_media_time(self.get_data('start'))} /"
            f" {format_media_time(self.get_data('end'))}"
        )

    @property
    def length_formatted(self) -> str:
        return format_media_time(self.get_data("length"))

    @property
    def metric_position_formatted(self):
        start_metric_position = self.get_data("start_metric_position")
        end_metric_position = self.get_data("end_metric_position")
        if not start_metric_position:
            return "-"
        return f"{start_metric_position.measure}.{start_metric_position.beat} / {end_metric_position.measure}.{end_metric_position.beat}"

    def get_inspector_dict(self) -> dict:
        data = {
            "Start / end": self.start_and_end_formatted,
            "Length": self.length_formatted,
        }

        if self.get_data("start_metric_position"):
            data["Start / end (metric)"] = self.metric_position_formatted

        return data


class MeasureBoxBody(CursorMixIn, QGraphicsRectItem):
    def __init__(self, start_x: float, end_x: float, tl_height: float):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.set_position(start_x, end_x, tl_height)
        self.selected = False
        self.update_style()

    def update_style(self):
        color = (
            get_tinted_color(
                settings.get("score_timeline", "measure_box_color"),
                TINT_FACTOR_ON_SELECTION,
            )
            if self.selected
            else settings.get("score_timeline", "measure_box_color")
        )
        self.setBrush(QColor(color))
        pen = QPen(QColor(get_tinted_color(color, TINT_FACTOR_ON_SELECTION)))
        pen.setStyle(Qt.PenStyle.SolidLine if self.selected else Qt.PenStyle.NoPen)
        self.setPen(pen)

    def set_position(self, start_x: float, end_x: float, tl_height: float):
        self.setRect(QRectF(QPointF(start_x, 0), QPointF(end_x, tl_height)))
        self.setZValue(10)

    def on_select(self):
        self.selected = True
        self.update_style()

    def on_deselect(self):
        self.selected = False
        self.update_style()
