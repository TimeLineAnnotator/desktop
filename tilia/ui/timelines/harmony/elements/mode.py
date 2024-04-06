from __future__ import annotations

import typing

import music21
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsItem, QGraphicsTextItem

from tilia.requests import get, Get, post, Post
from tilia.ui.coords import get_x_by_time, get_time_by_x
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.drag import DragManager
from tilia.ui.timelines.harmony.constants import (
    INT_TO_NOTE_NAME,
    ACCIDENTAL_NUMBER_TO_MUSIC21_CHAR,
    INT_TO_ACCIDENTAL,
)
from tilia.ui.timelines.harmony.context_menu import ModeContextMenu
from tilia.ui.timelines.harmony.elements import mode_attrs

if typing.TYPE_CHECKING:
    from tilia.ui.timelines.harmony import HarmonyTimelineUI


class ModeUI(TimelineUIElement):
    INSPECTOR_FIELDS = mode_attrs.INSPECTOR_FIELDS
    FIELD_NAMES_TO_ATTRIBUTES = mode_attrs.FIELD_NAMES_TO_ATTRIBUTES
    DEFAULT_COPY_ATTRIBUTES = mode_attrs.DEFAULT_COPY_ATTRIBUTES
    UPDATE_TRIGGERS = ["time", "step", "accidental", "type", "level"]
    CONTEXT_MENU_CLASS = ModeContextMenu

    def __init__(
        self,
        id: int,
        timeline_ui: HarmonyTimelineUI,
        scene: QGraphicsScene,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)

        self._setup_body()

        self.dragged = False

    def _setup_body(self):
        self.body = ModeBody(self.x, self.y, self.label)
        self.scene.addItem(self.body)

    @property
    def x(self):
        return get_x_by_time(self.get_data("time"))

    @property
    def y(self):
        return (self.timeline_ui.get_y(self.get_data("level"))) + 10

    @property
    def label(self):
        center = (
            INT_TO_NOTE_NAME[self.get_data("step")]
            + INT_TO_ACCIDENTAL[self.get_data("accidental")]
        )
        result = center if self.get_data("type") == "major" else center.lower()
        if result[0] == "b":
            result = "@" + result
        return result

    @property
    def key(self):
        tonic = (
            INT_TO_NOTE_NAME[self.get_data("step")]
            + ACCIDENTAL_NUMBER_TO_MUSIC21_CHAR[self.get_data("accidental")]
        )
        return music21.key.Key(tonic, mode=self.get_data("type"))

    @property
    def seek_time(self):
        return self.get_data("time")

    def update_step(self):
        self.update_label()
        self.timeline_ui.update_harmony_labels()

    def update_accidental(self):
        self.update_label()
        self.timeline_ui.update_harmony_labels()

    def update_type(self):
        self.update_label()
        self.timeline_ui.update_harmony_labels()

    def update_level(self):
        self.update_label()

    def update_label(self):
        self.body.set_text(self.label)
        self.body.set_position(self.x, self.y)

    def update_position(self):
        self.update_time()

    def update_time(self):
        self.body.set_position(self.x, self.y)

    def child_items(self):
        return [self.body]

    def left_click_triggers(self) -> list[QGraphicsItem]:
        return [self.body]

    def on_left_click(self, _) -> None:
        self.setup_drag()

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
        self.set_data("time", get_time_by_x(drag_x))

    def on_drag_end(self):
        if self.dragged:
            post(Post.APP_RECORD_STATE, "harmony drag")
            post(Post.ELEMENT_DRAG_END)
            self.timeline_ui.on_element_drag_done()

        self.dragged = False

    def on_select(self) -> None:
        self.body.on_select()

    def on_deselect(self) -> None:
        self.body.on_deselect()

    def get_inspector_dict(self):
        return mode_attrs.get_inspector_dict(self)


class ModeBody(QGraphicsTextItem):
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
        font = QFont("MusAnalysis", 10)
        self.setFont(font)
        self.setDefaultTextColor(QColor("black"))

    def get_point(self, x: float, y: float):
        return QPointF(x - self.boundingRect().width() / 2, y)

    def set_position(self, x, y):
        self.setPos(self.get_point(x, y))

    def set_text(self, value: str):
        self.setPlainText(value)

    def on_select(self):
        font = self.font()
        font.setBold(True)
        self.setFont(font)

    def on_deselect(self):
        font = self.font()
        font.setBold(False)
        self.setFont(font)
