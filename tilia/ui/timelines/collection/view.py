from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsView, QAbstractSlider
from tilia.requests import post, Post, listen
from tilia.ui.smooth_scroll import setup_smooth, smooth


class TimelineUIsView(QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_scroll_margins()
        setup_smooth(self)

    def is_hscrollbar_pressed(self):
        return self.horizontalScrollBar().isSliderDown()

    def move_to_x(self, x: float):
        def __get_x():
            return [self.mapToScene(self.viewport().rect().center()).x()]

        @smooth(self, __get_x)
        def __set_x(x):
            y = self.mapToScene(self.viewport().rect().center()).y() + 1
            self.centerOn(x, y)

        __set_x(x)

    @property
    def current_viewport_x(self):
        viewport = self.mapToScene(self.viewport().geometry()).boundingRect()
        return {0: viewport.left(), 1: viewport.right()}

    def _update_scroll_margins(self):
        viewport = self.current_viewport_x
        self.scroll_margin = (viewport[1] - viewport[0]) / 10
        self.scroll_offset = self.scroll_margin * 4

    def wheelEvent(self, event) -> None:
        if Qt.KeyboardModifier.ShiftModifier in event.modifiers():
            dx = event.angleDelta().y()
            dy = event.angleDelta().x()
        else:
            dx = event.angleDelta().x()
            dy = event.angleDelta().y()

        if event.inverted():
            temp = dx
            dx = dy
            dy = temp

        if Qt.KeyboardModifier.ControlModifier in event.modifiers():
            if dy > 0:
                post(Post.VIEW_ZOOM_IN)
            else:
                post(Post.VIEW_ZOOM_OUT)
            return

        else:
            if dx < 0:
                self.horizontalScrollBar().triggerAction(
                    QAbstractSlider.SliderAction.SliderSingleStepAdd
                )
            elif dx > 0:
                self.horizontalScrollBar().triggerAction(
                    QAbstractSlider.SliderAction.SliderSingleStepSub
                )
            if dy < 0:
                self.verticalScrollBar().triggerAction(
                    QAbstractSlider.SliderAction.SliderSingleStepAdd
                )
            elif dy > 0:
                self.verticalScrollBar().triggerAction(
                    QAbstractSlider.SliderAction.SliderSingleStepSub
                )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scroll_margins()
