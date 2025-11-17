from PySide6.QtCore import QLineF
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsLineItem

from tilia.requests import get, Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.score.element import NoteUI


class StaffUI(TimelineUIElement):
    COMPONENT_KIND = ComponentKind.STAFF

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_lines()

    @property
    def middle_y(self):
        return self.timeline_ui.get_staff_middle_y(self.get_data("index"))

    def top_y(self):
        return self.staff_lines.lines[0].line().y1()

    def bottom_y(self):
        return self.staff_lines.lines[-1].line().y1()

    def line_args(self):
        return (
            self.get_data("line_count"),
            get(Get.LEFT_MARGIN_X),
            get(Get.RIGHT_MARGIN_X),
            self.middle_y,
            NoteUI.note_height(),
        )

    def update_position(self):
        self.staff_lines.set_position(*self.line_args())

    def _setup_lines(self):
        self.staff_lines = StaffLines(*self.line_args())
        for line in self.staff_lines.lines:
            self.scene.addItem(line)

    def on_components_deserialized(self):
        self.update_position()

    def child_items(self):
        return self.staff_lines.lines

    def selection_triggers(self):
        return []


class StaffLines:
    COLOR = "gray"

    def __init__(
        self,
        line_count: int,
        x1: float,
        x2: float,
        middle_y: float,
        line_spacing: float,
    ):
        self._setup_lines(line_count, x1, x2, middle_y, line_spacing)

    @staticmethod
    def get_offsets(line_count: int, line_spacing: float) -> list[float]:
        if line_count % 2 == 0:
            return [
                (line_spacing * i) - ((line_count - 1) * line_spacing / 2)
                for i in range(line_count)
            ]
        else:
            return [
                (line_spacing * i) - ((line_count / 2 - 1) * line_spacing)
                for i in range(line_count)
            ]

    def _setup_lines(
        self,
        line_count: int,
        x1: float,
        x2: float,
        middle_y: float,
        line_spacing: float,
    ):
        self.lines = [QGraphicsLineItem() for _ in range(line_count)]
        pen = QPen(QColor("gray"))
        pen.setWidth(2)
        for line in self.lines:
            line.setPen(pen)
            line.setZValue(-1)
        self.set_position(line_count, x1, x2, middle_y, line_spacing)

    def set_position(
        self,
        line_count: int,
        x1: float,
        x2: float,
        middle_y: float,
        line_spacing: float,
    ):
        for i, y_offset in enumerate(self.get_offsets(line_count, line_spacing)):
            y = middle_y + y_offset - line_spacing / 2
            self.lines[i].setLine(QLineF(x1, y, x2, y))
