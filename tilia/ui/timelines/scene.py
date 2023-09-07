from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QFontMetrics

from tilia import settings
from tilia.requests import Get, get


class TimelineScene(QGraphicsScene):
    LABEL_Y_MARGIN = 3

    def __init__(
        self,
        id: int,
        width: int,
        height: int,
        left_margin: int,
        text: str,
    ):
        self.id = id
        super().__init__(0, 0, width, height)

        self._setup_text_bg(left_margin)
        self._setup_text(text)
        self._setup_playback_line(left_margin)

    def _setup_text(self, text: str):
        self.font = QFont()
        self.text = self.addText(self._get_elided_text(text), self.font)
        self.text.setDefaultTextColor(QColor("black"))
        self.text.setPos(*self.text_pos)

    def _get_elided_text(self, text: str):
        return QFontMetrics(self.font).elidedText(
            text,
            Qt.TextElideMode.ElideRight,
            get(Get.LEFT_MARGIN_X) - self.LABEL_Y_MARGIN - 10,
        )

    def _setup_text_bg(self, width):
        pen = QPen()
        pen.setStyle(Qt.PenStyle.NoPen)
        self.text_bg = self.addRect(0, 0, width, self.height(), pen)
        self.text_bg.setBrush(QBrush(QColor(settings.get("general", "timeline_bg"))))

    def _setup_playback_line(self, x):
        pen = QPen()
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setColor(QColor("gray"))
        pen.setDashPattern([4, 4])
        pen.setWidth(0)
        self.playback_line = self.addLine(x, 0, x, self.height(), pen)

    def set_playback_line_pos(self, x):
        self.playback_line.setLine(x, 0, x, self.height())

    def set_height(self, value):
        x, y, w, _ = self.sceneRect().getRect()
        self.setSceneRect(x, y, w, value)
        self.text.setPos(*self.text_pos)

    def set_width(self, value):
        x, y, _, h = self.sceneRect().getRect()
        self.setSceneRect(x, y, value, h)
        self.text.setPos(*self.text_pos)

    def set_text(self, value):
        self.text.setPlainText(self._get_elided_text(value))

    @property
    def text_pos(self):
        return (
            self.LABEL_Y_MARGIN,
            self.height() / 2 - self.text.boundingRect().height() / 2,
        )

    def destroy(self):
        self.deleteLater()
