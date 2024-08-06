from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsView, QAbstractSlider
from tilia.requests import post, Post, listen


class TimelineUIsView(QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        max_x = self.horizontalScrollBar().maximum()
        max_y = self.verticalScrollBar().maximum()
        self.cur_x = self.horizontalScrollBar().value() / max_x if max_x != 0 else 0.5
        self.cur_y = self.verticalScrollBar().value() / max_y if max_y != 0 else 0.5
        listen(self, Post.PLAYBACK_AREA_SET_WIDTH, lambda _: self.update_width)

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

        if dy > 0:
            post(Post.VIEW_ZOOM_IN)
        else:
            post(Post.VIEW_ZOOM_OUT)

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

    def update_width(self):
        max_x = self.horizontalScrollBar().maximum()
        max_y = self.verticalScrollBar().maximum()

        if max_x != 0:
            self.horizontalScrollBar().setValue(round(self.cur_x * max_x))
        if max_y != 0:
            self.verticalScrollBar().setValue(round(self.cur_y * max_y))

        self.cur_x = self.horizontalScrollBar().value() / max_x if max_x != 0 else 0.5
        self.cur_y = self.verticalScrollBar().value() / max_y if max_y != 0 else 0.5
