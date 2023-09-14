from tilia.ui.qt.actions import Actions, action_to_qaction
from tilia.ui.timelines.common import TimelineToolbar

from PyQt6.QtWidgets import QToolBar


class QtTimelineToolbar(QToolBar):
    ACTIONS = []

    def __init__(self):
        super().__init__()
        self.visible = False
        self._visible_timelines_count = 0


class BeatTimelineToolbar(QtTimelineToolbar):
    ACTIONS = [Actions.BEAT_ADD, Actions.BEAT_DELETE]

    def __init__(self):
        super().__init__()
        for action in self.ACTIONS:
            self.addAction(action_to_qaction[action])
