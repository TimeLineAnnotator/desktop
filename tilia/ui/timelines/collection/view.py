from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsView, QAbstractSlider
from tilia.requests import post, Post


class TimelineUIsView(QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def is_hscrollbar_pressed(self):
        return self.horizontalScrollBar().isSliderDown()

    def move_to_x(self, x: float):
        center = self.get_center()
        self.center_on(x, center[1])

    def get_center(self):
        qpoint = self.mapToScene(self.viewport().rect().center())
        return qpoint.x(), qpoint.y()

    def center_on(self, x, y):
        self.centerOn(x, y + 1)

    def wheelEvent(self, event) -> None:
        dx = event.angleDelta().x()
        dy = event.angleDelta().y()

        if event.inverted():
            temp = dx
            dx = dy
            dy = temp

        max_x = self.horizontalScrollBar().maximum()
        cur_x = self.horizontalScrollBar().value() / max_x if max_x != 0 else 0.5
        max_y = self.verticalScrollBar().maximum()
        cur_y = self.verticalScrollBar().value() / max_y if max_y != 0 else 0.5

        if dy > 0:
            post(Post.VIEW_ZOOM_IN)
        else:
            post(Post.VIEW_ZOOM_OUT)

        if self.horizontalScrollBar().maximum() != 0:
            self.horizontalScrollBar().setValue(
                round(cur_x * self.horizontalScrollBar().maximum())
            )
        if self.verticalScrollBar().maximum() != 0:
            self.verticalScrollBar().setValue(
                round(cur_y * self.verticalScrollBar().maximum())
            )

    def wheelEvent_with_mod(self, event) -> None:
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
            max_x = self.horizontalScrollBar().maximum()
            cur_x = self.horizontalScrollBar().value() / max_x if max_x != 0 else 0.5
            max_y = self.verticalScrollBar().maximum()
            cur_y = self.verticalScrollBar().value() / max_y if max_y != 0 else 0.5

            if dy > 0:
                post(Post.VIEW_ZOOM_IN)
            else:
                post(Post.VIEW_ZOOM_OUT)

            if self.horizontalScrollBar().maximum() != 0:
                self.horizontalScrollBar().setValue(
                    round(cur_x * self.horizontalScrollBar().maximum())
                )
            if self.verticalScrollBar().maximum() != 0:
                self.verticalScrollBar().setValue(
                    round(cur_y * self.verticalScrollBar().maximum())
                )
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
