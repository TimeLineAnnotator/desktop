from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QToolBar

from tilia.ui import actions


class TimelineToolbar(QToolBar):
    ACTIONS = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.visible = False
        self._visible_timelines_count = 0
        for action in self.ACTIONS:
            self.addAction(actions.get_qaction(action))
