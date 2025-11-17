from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsScene, QGraphicsRectItem
from PySide6.QtGui import QColor, QPen, QBrush, QFont, QFontMetrics

from tilia.settings import settings
from tilia.requests import Get, get, listen, Post


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
        self._setup_loop_box(left_margin, left_margin)
        listen(
            self,
            Post.SETTINGS_UPDATED,
            self.on_settings_updated,
        )

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
        self.text_bg.setBrush(
            QBrush(QColor(settings.get("general", "timeline_background_color")))
        )

    def _setup_playback_line(self, x):
        pen = QPen()
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setColor(QColor("gray"))
        pen.setDashPattern([4, 4])
        pen.setWidth(0)
        self.playback_line = self.addLine(x, 0, x, self.height(), pen)

    def on_settings_updated(self, updated_settings):
        if "general" in updated_settings:
            self.text_bg.setBrush(
                QBrush(QColor(settings.get("general", "timeline_background_color")))
            )
            self.set_loop_box_color(QColor(settings.get("general", "loop_box_shade")))

    def set_playback_line_pos(self, x):
        self.playback_line.setLine(x, 0, x, self.height())

    def _setup_loop_box(self, x_start, x_end):
        self.loop_box = QGraphicsRectItem(x_start, 0, x_end - x_start, self.height())
        self.set_loop_box_color(QColor(settings.get("general", "loop_box_shade")))
        self.loop_box.setVisible(False)
        self.addItem(self.loop_box)
        self.loop_box.setZValue(
            -len(settings.get("hierarchy_timeline", "default_colors")) - 1
        )

    def set_loop_box_color(self, color):
        pen = QPen()
        pen.setColor(color)
        pen.setWidth(0)

        brush = QBrush(color)

        self.loop_box.setBrush(brush)
        self.loop_box.setPen(pen)

    def set_loop_box_position(self, x_start, x_end):
        if x_end - x_start > 0:
            self.loop_box.setRect(x_start, 0, x_end - x_start, self.height())
            self.loop_box.setVisible(True)

        else:
            self.loop_box.setVisible(False)

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
