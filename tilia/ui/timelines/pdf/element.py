from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import (
    QPen,
    QColor,
    QFont,
    QPixmap,
    QFontMetrics,
)
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsTextItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
)

from tilia.requests import Post, post, get, Get
from .context_menu import PdfMarkerContextMenu
from ..copy_paste import CopyAttributes
from ..cursors import CursorMixIn
from ..drag import DragManager
from ...format import format_media_time
from ...coords import get_x_by_time, get_time_by_x
from tilia.ui.timelines.base.element import TimelineUIElement
from ...windows.inspect import InspectRowKind

if TYPE_CHECKING:
    from .timeline import PdfTimelineUI


class PdfMarkerUI(TimelineUIElement):
    RADIUS = 10

    LABEL_MARGIN = 3

    FIELD_NAMES_TO_ATTRIBUTES = {"Page number": "page_number"}

    DEFAULT_COPY_ATTRIBUTES = CopyAttributes(
        by_element_value=[],
        by_component_value=["page_number"],
        support_by_element_value=[],
        support_by_component_value=["time"],
    )

    UPDATE_TRIGGERS = ["time", "page_number"]

    CONTEXT_MENU_CLASS = PdfMarkerContextMenu

    def __init__(
        self,
        id: int,
        timeline_ui: PdfTimelineUI,
        scene: QGraphicsScene,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)

        self.INSPECTOR_FIELDS = [
            (
                "Page number",
                InspectRowKind.SPIN_BOX,
                self.get_page_number_inspector_field_args,
            ),
            ("Time", InspectRowKind.LABEL, None),
        ]
        self._setup_body()
        self._setup_label()

        self.dragged = False

    def _setup_body(self):
        self.body = PdfMarkerBody(self.x)
        self.scene.addItem(self.body)

    def _setup_label(self):
        self.label = PdfMarkerLabel(self.x, str(self.get_data("page_number")))
        self.scene.addItem(self.label)

    @property
    def x(self):
        return get_x_by_time(self.get_data("time"))

    @property
    def seek_time(self):
        return self.get_data("time")

    @property
    def ui_color(self):
        return "#000000"

    def update_position(self):
        self.update_time()

    def update_time(self):
        self.body.set_position(self.x)
        self.label.set_position(self.x)

    def update_page_number(self):
        self.label.set_text(str(self.get_data("page_number")))
        self.timeline_ui.update_displayed_page(get(Get.MEDIA_CURRENT_TIME))

    def child_items(self):
        return [self.body, self.label]

    def left_click_triggers(self) -> list[QGraphicsItem]:
        return [self.body, self.label]

    def on_left_click(self, _) -> None:
        self.setup_drag()

    def double_left_click_triggers(self):
        return [self.body, self.label]

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
        self.set_data("time", get_time_by_x(drag_x))

    def on_drag_end(self):
        if self.dragged:
            post(Post.APP_RECORD_STATE, "page marker drag")
            post(Post.ELEMENT_DRAG_END)

        self.dragged = False

    def on_select(self) -> None:
        self.body.on_select()

    def on_deselect(self) -> None:
        self.body.on_deselect()

    def get_inspector_dict(self) -> dict:
        return {
            "Time": format_media_time(self.get_data("time")),
            "Page number": self.get_data("page_number"),
        }

    def get_page_number_inspector_field_args(self):
        return {"min": 1, "max": self.timeline_ui.page_total}


class PdfMarkerBody(CursorMixIn, QGraphicsPixmapItem):
    # Icon by Freepik. Available at: https://www.flaticon.com/free-icon/page-blank_16120
    ICON_PATH = Path("ui", "img", "pdf_page.png")
    WIDTH = 20
    TOP_MARGIN = 5
    SELECTION_BOX_MARGIN = 2

    def __init__(self, x: float):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.setPixmap(
            QPixmap(self.ICON_PATH.resolve().__str__()).scaled(self.WIDTH, self.WIDTH)
        )
        self.set_position(x)

    def set_position(self, x):
        self.setPos(x - self.WIDTH / 2, self.TOP_MARGIN)

    def on_select(self):
        self.selection_box = QGraphicsRectItem(self)
        margin = self.SELECTION_BOX_MARGIN
        self.selection_box.setRect(
            -margin, -margin, self.WIDTH + 2 * margin, self.WIDTH + 2 * margin
        )
        pen = QPen()
        pen.setWidth(2)

    def on_deselect(self):
        self.selection_box.hide()


class PdfMarkerLabel(QGraphicsTextItem):
    TOP_MARGIN = 4
    DEFAULT_FONT_SIZE = 8
    MAX_TEXT_WIDTH = 12

    def __init__(self, x: float, text: str):
        super().__init__()
        self.set_font()
        self.set_text(text)
        self.set_position(x)

    def set_font(self, size=None):
        if not size:
            size = self.DEFAULT_FONT_SIZE
        font = QFont("Arial", size)
        self.setFont(font)
        self.setDefaultTextColor(QColor("black"))

    def get_point(self, x: float):
        return QPointF(
            x - self.boundingRect().width() / 2,
            PdfMarkerBody.TOP_MARGIN + self.TOP_MARGIN,
        )

    def set_position(self, x):
        self.setPos(self.get_point(x))

    def set_text(self, value: str):
        fits = False
        self.set_font(self.DEFAULT_FONT_SIZE)
        while not fits:
            font_metrics = QFontMetrics(self.font())
            width = font_metrics.horizontalAdvance(value)
            if width > self.MAX_TEXT_WIDTH:
                self.set_font(self.font().pointSize() - 1)
            else:
                fits = True

        self.setPlainText(value)
