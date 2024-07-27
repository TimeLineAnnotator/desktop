from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QPointF, QLineF
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsLineItem

from tilia.requests import Post, post, get, Get
from ..cursors import CursorMixIn
from ..drag import DragManager
from ...coords import get_x_by_time
from ...color import get_tinted_color
from ...consts import TINT_FACTOR_ON_SELECTION
from tilia.settings import settings
from tilia.ui.timelines.base.element import TimelineUIElement
from ...windows.inspect import InspectRowKind

if TYPE_CHECKING:
    from .timeline import AudioWaveTimelineUI


class AmplitudeBarUI(TimelineUIElement):
    INSPECTOR_FIELDS = [
        ("Start / End", InspectRowKind.LABEL, None),
        ("Amplitude", InspectRowKind.LABEL, None),
    ]

    def __init__(
        self,
        id: int,
        timeline_ui: AudioWaveTimelineUI,
        scene: QGraphicsScene,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)
        self.timeline_ui = timeline_ui
        self._setup_body()
        self.dragged = False

    @property
    def start_x(self):
        return get_x_by_time(self.get_data("start"))

    @property
    def width(self):
        return get_x_by_time(self.get_data("end")) - get_x_by_time(
            self.get_data("start")
        )

    @property
    def amplitude(self):
        return self.get_data("amplitude")

    @property
    def height(self):
        return self.timeline_ui.get_data("height")

    @property
    def seek_time(self):
        return self.get_data("start")

    @property
    def x(self):
        return get_x_by_time(self.seek_time)

    def _setup_body(self):
        self.body = AmplitudeBarUIBody(
            self.start_x, self.width, self.amplitude, self.height
        )
        self.scene.addItem(self.body)

    def update_position(self):
        self.update_time()

    def update_time(self):
        self.body.set_position(self.start_x, self.width, self.amplitude, self.height)

    def child_items(self):
        return [self.body]

    def left_click_triggers(self):
        return [self.body]

    def on_left_click(self, _) -> None:
        self.setup_drag()

    def double_left_click_triggers(self):
        return [self.body]

    def on_double_left_click(self, _):
        post(Post.PLAYER_SEEK, self.seek_time)

    def setup_drag(self):
        DragManager(
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
        pass

    def on_drag_end(self):
        if self.dragged:
            post(Post.APP_RECORD_STATE, "AudioWave drag")
            post(Post.ELEMENT_DRAG_END)
        self.dragged = False

    def on_select(self) -> None:
        self.body.on_select()

    def on_deselect(self) -> None:
        self.body.on_deselect()

    def get_inspector_dict(self) -> dict:
        return self.timeline_ui.get_inspector_dict()


class AmplitudeBarUIBody(CursorMixIn, QGraphicsLineItem):
    def __init__(
        self,
        start_x: float,
        width: float,
        amplitude: float,
        height: float,
    ):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.setLine(self.get_line(start_x, amplitude, height))
        self.width = width / 100
        self.selected = False
        self.update_pen_style()

    def set_position(self, start_x, width, amplitude, height):
        self.setLine(self.get_line(start_x, amplitude, height))
        self.width = width / 100
        self.update_pen_style()

    @staticmethod
    def get_line(x, amplitude, max_height):
        height = amplitude * max_height
        offset = (max_height - height) / 2
        return QLineF(QPointF(x, offset), QPointF(x, offset + height))

    def update_pen_style(self):
        color = (
            get_tinted_color(
                settings.get("audiowave_timeline", "default_color"),
                TINT_FACTOR_ON_SELECTION,
            )
            if self.selected
            else settings.get("audiowave_timeline", "default_color")
        )
        pen = QPen(QColor(color))
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setWidthF(self.width)
        self.setPen(pen)

    def on_select(self):
        self.selected = True
        self.update_pen_style()

    def on_deselect(self):
        self.selected = False
        self.update_pen_style()
