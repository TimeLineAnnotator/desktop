from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsView


class TimelineUIsView(QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def is_hscrollbar_pressed(self):
        return self.horizontalScrollBar().isSliderDown()
