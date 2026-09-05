from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolBar

from tilia.ui import commands


class TimelineToolbar(QToolBar):
    COMMANDS = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The object name must be unique per toolbar class. QMainWindow.restoreState
        # matches saved toolbar entries to live toolbars by object name, so sharing a
        # single name across kinds makes it restore one kind's state onto another.
        self.setObjectName(self.__class__.__name__)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        for command in self.COMMANDS:
            self.addAction(commands.get_qaction(command))
