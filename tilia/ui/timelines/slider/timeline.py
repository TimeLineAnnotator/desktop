from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, QLineF, Qt
from PyQt6.QtGui import QPen, QColor, QBrush, QGuiApplication
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem

import tilia.ui.coords
from tilia.media.player.base import MediaTimeChangeReason
from tilia.requests import get, Get, post
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui import coords
from tilia.ui.modifier_enum import ModifierEnum
from tilia import settings
from tilia.requests import Post, listen
from tilia.timelines.base.component import TimelineComponent
from tilia.ui.timelines.base.timeline import TimelineUI
from tilia.ui.timelines.base.element_manager import ElementManager
from tilia.ui.timelines.drag import DragManager
from tilia.ui.timelines.view import TimelineView
from ..cursors import CursorMixIn

if TYPE_CHECKING:
    from tilia.ui.timelines.scene import TimelineScene
    from tilia.ui.timelines.collection.collection import TimelineUIs


class SliderTimelineUI(TimelineUI):
    TOOLBAR_CLASS = None

    TROUGH_RADIUS = settings.get("slider_timeline", "trough_radius")
    TROUGH_DEFAULT_COLOR = settings.get("slider_timeline", "trough_color")
    LINE_DEFAULT_COLOR = settings.get("slider_timeline", "line_color")
    LINE_WEIGHT = settings.get("slider_timeline", "line_weight")

    TIMELINE_KIND = TimelineKind.SLIDER_TIMELINE
    CONTEXT_MENU_CLASS = []

    def __init__(
        self,
        id: int,
        collection: TimelineUIs,
        element_manager: ElementManager,
        scene: TimelineScene,
        view: TimelineView,
    ):
        super().__init__(
            id=id,
            collection=collection,
            element_manager=element_manager,
            scene=scene,
            view=view,
        )

        listen(self, Post.PLAYER_CURRENT_TIME_CHANGED, self.on_audio_time_change)

        self.x = get(Get.LEFT_MARGIN_X)
        self._setup_line()
        self._setup_trough()
        self._setup_playback_line()

        self.dragging = False

    def _setup_line(self):
        self.line = Line()
        self.scene.addItem(self.line)
        self.line.set_position(*self._get_line_pos_args())
        self.line.set_color(self.LINE_DEFAULT_COLOR)
        self.line.set_width(self.LINE_WEIGHT)

    def _get_line_pos_args(self):
        return get(Get.LEFT_MARGIN_X), get(Get.RIGHT_MARGIN_X), self.view.height() / 2

    def _setup_trough(self):
        self.trough = Trough(self.TROUGH_RADIUS, self.TROUGH_DEFAULT_COLOR)
        self.scene.addItem(self.trough)
        self.set_trough_position()

    def _setup_playback_line(self):
        self.scene: TimelineScene
        self.scene.playback_line.setVisible(False)

    def set_trough_position(self) -> None:
        args = (
            self.x - self.TROUGH_RADIUS,
            self.view.height() / 2 - self.TROUGH_RADIUS,
        )
        self.trough.setPos(*args)

    def set_line_position(self) -> None:
        y = self.view.height() / 2
        self.line.setLine(QLineF(get(Get.LEFT_MARGIN_X), y, get(Get.RIGHT_MARGIN_X), y))

    def set_width(self, width):
        self.scene.set_width(int(width))
        self.view.setFixedWidth(int(width))
        self.update_items_position()

    def on_left_click(self, item_id: int, modifier: ModifierEnum, double: bool, x: int, y: int) -> None:
        if item_id == self.line:
            time = tilia.ui.coords.get_time_by_x(x)
            if double:
                post(Post.PLAYER_SEEK, time)
            else:
                post(Post.PLAYER_SEEK_IF_NOT_PLAYING, time)
        elif item_id == self.trough:
            self.setup_drag()

    def setup_drag(self) -> None:
        DragManager(
            get_min_x=lambda: get(Get.LEFT_MARGIN_X),
            get_max_x=lambda: get(Get.RIGHT_MARGIN_X),
            before_each=self.before_each_drag,
            after_each=self.after_each_drag,
            on_release=self.on_drag_end,
        )

    def before_each_drag(self):
        if not self.dragging:
            post(Post.SLIDER_DRAG_START)
            self.dragging = True

    def after_each_drag(self, x: int):
        self.x = x
        self.set_trough_position()
        post(Post.SLIDER_DRAG, x)

    def on_drag_end(self):
        post(Post.PLAYER_SEEK, coords.get_time_by_x(self.x))  # maybe not necessary
        self.dragging = False
        post(Post.SLIDER_DRAG_END)

    def on_audio_time_change(self, time: float, _: MediaTimeChangeReason) -> None:
        if not self.dragging:
            self.x = coords.get_x_by_time(time)
            self.set_trough_position()

    def get_ui_for_component(
        self, component_kind: ComponentKind, component: TimelineComponent, **kwargs
    ):
        """No components in SliderTimeline. Must implement abstract method."""

    def update_items_position(self):
        self.x = coords.get_x_by_time(get(Get.MEDIA_CURRENT_TIME))
        self.set_trough_position()
        self.line.set_position(*self._get_line_pos_args())

    @property
    def has_selected_elements(self):
        return False

    def draw_playback_line(self) -> None:
        """Slider timeline does not have a playback line (as it has a slider trough)."""

    def change_playback_line_position(self, time: float) -> None:
        """Slider timeline does not have a playback line (as it has a slider trough)."""

    def crop(self):
        self.update_items_position()

    def __str__(self):
        return "Slider Timeline"


class Line(CursorMixIn, QGraphicsLineItem):
    def __init__(self):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self._setup_pen()

    def _setup_pen(self):
        pen = self.pen()
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)

    def set_position(self, x0: int, x1: int, y: int):
        self.setLine(x0, y, x1, y)

    def set_color(self, color: str):
        pen = self.pen()
        pen.setColor(QColor(color))
        self.setPen(pen)

    def set_width(self, width: int):
        pen = self.pen()
        pen.setWidth(width)
        self.setPen(pen)


class Trough(CursorMixIn, QGraphicsEllipseItem):
    def __init__(self, radius: float, color: str):
        super().__init__(cursor_shape=Qt.CursorShape.SizeHorCursor)
        self.setRect(self.get_rect(radius))
        self.set_pen(color)
        self.set_brush(color)

    def set_brush(self, color):
        self.setBrush(QBrush(QColor(color)))

    def set_pen(self, color):
        self.setPen(QPen(QColor(color)))

    def set_position(self, x):
        self.setRect(self.get_rect(x))

    @staticmethod
    def get_rect(radius):
        return QRectF(
            0,
            0,
            radius * 2,
            radius * 2,
        )