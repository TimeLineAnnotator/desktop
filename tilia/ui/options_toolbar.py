from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QToolBar, QCheckBox

from tilia import settings
from tilia.ui import actions
from tilia.ui.actions import TiliaAction


class OptionsToolbar(QToolBar):
    def __init__(self):
        super().__init__()
        self.check_box = QCheckBox("Auto-scroll")
        self.check_box.setCheckState(
            Qt.CheckState(Qt.CheckState.Checked)
            if settings.get("general", "auto-scroll")
            else Qt.CheckState(Qt.CheckState.Unchecked)
        )
        self.check_box.stateChanged.connect(self.on_state_changed)
        self.addWidget(self.check_box)

    def on_state_changed(self):
        if self.check_box.isChecked():
            actions.trigger(TiliaAction.TIMELINES_AUTO_SCROLL_ENABLE)
        else:
            actions.trigger(TiliaAction.TIMELINES_AUTO_SCROLL_DISABLE)
