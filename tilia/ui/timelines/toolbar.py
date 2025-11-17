from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolBar

from tilia.ui import commands


class TimelineToolbar(QToolBar):
    COMMANDS = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("timeline_toolbar")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.visible = False
        self._visible_timelines_count = 0
        for command in self.COMMANDS:
            self.addAction(commands.get_qaction(command))
