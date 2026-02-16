from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QPainter,
    QMouseEvent,
    QGuiApplication,
    QColor,
    QBrush,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsView,
    QSizePolicy,
)

from tilia.settings import settings
from tilia.requests import post, Post, Get, get, listen


class TimelineView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene):
        super().__init__()
        self.setScene(scene)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(int(scene.height()))
        self.setFixedWidth(int(get(Get.TIMELINE_WIDTH)))

        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setBackgroundBrush(
            QBrush(QColor(settings.get("general", "timeline_background_color")))
        )
        listen(
            self,
            Post.SETTINGS_UPDATED,
            self.on_settings_updated,
        )

        self.dragging = False
        self.proxy = QGraphicsProxyWidget()  # will be set by TimelineUIs

    def on_settings_updated(self, updated_settings):
        if "general" in updated_settings:
            self.setBackgroundBrush(
                QBrush(QColor(settings.get("general", "timeline_background_color")))
            )

    def mousePressEvent(self, event: Optional[QMouseEvent]) -> None:
        def handle_left_click():
            self.dragging = True
            post(
                Post.TIMELINE_VIEW_LEFT_CLICK,
                self,
                event.pos().x(),
                event.pos().y(),
                self.itemAt(event.pos()),
                QGuiApplication.keyboardModifiers(),
                double=False,
            )

        def handle_right_click():
            post(
                Post.TIMELINE_VIEW_RIGHT_CLICK,
                self,
                self.mapToGlobal(event.pos()).x(),
                self.mapToGlobal(event.pos()).y(),
                self.itemAt(event.pos()),
                QGuiApplication.keyboardModifiers(),
                double=False,
            )

        if event.button() == Qt.MouseButton.LeftButton:
            handle_left_click()
        elif event.button() == Qt.MouseButton.RightButton:
            handle_right_click()

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            post(
                Post.TIMELINE_VIEW_DOUBLE_LEFT_CLICK,
                self,
                event.pos().x(),
                event.pos().y(),
                self.itemAt(event.pos()),
                QGuiApplication.keyboardModifiers(),
                double=True,
            )

    def mouseReleaseEvent(self, event: Optional[QMouseEvent]) -> None:
        if self.dragging:
            self.dragging = False
            post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: Optional[QMouseEvent]) -> None:
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, event.pos().x(), event.pos().y())

        super().mouseMoveEvent(event)

    def set_height(self, value):
        self.setFixedHeight(value)

    def set_is_visible(self, value):
        self.show() if value else self.hide()

    def keyPressEvent(self, event) -> None:
        request = {
            Qt.Key.Key_Right: Post.TIMELINE_KEY_PRESS_RIGHT,
            Qt.Key.Key_Left: Post.TIMELINE_KEY_PRESS_LEFT,
            Qt.Key.Key_Up: Post.TIMELINE_KEY_PRESS_UP,
            Qt.Key.Key_Down: Post.TIMELINE_KEY_PRESS_DOWN,
        }.get(event.key(), None)

        if request:
            post(request)

        super().keyPressEvent(event)
