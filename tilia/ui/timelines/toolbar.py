import logging

from PyQt6.QtWidgets import QToolBar

from tilia.ui.actions import taction_to_qaction

logger = logging.getLogger(__name__)


class TimelineToolbar(QToolBar):
    ACTIONS = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visible = False
        self._visible_timelines_count = 0
        for action in self.ACTIONS:
            self.addAction(taction_to_qaction[action])
