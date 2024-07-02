from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QToolBar, QCheckBox

from tilia.settings import settings
from tilia.ui import actions
from tilia.ui.actions import TiliaAction


class OptionsToolbar(QToolBar):
    def __init__(self):
        super().__init__()
        self.setObjectName("options_toolbar")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.check_box = QCheckBox("Auto-scroll")
        self.check_box.setChecked(settings.get("general", "auto-scroll"))
        self.check_box.stateChanged.connect(self.on_state_changed)
        self.addWidget(self.check_box)

    def on_state_changed(self):
        if self.check_box.isChecked():
            actions.trigger(TiliaAction.TIMELINES_AUTO_SCROLL_ENABLE)
        else:
            actions.trigger(TiliaAction.TIMELINES_AUTO_SCROLL_DISABLE)
