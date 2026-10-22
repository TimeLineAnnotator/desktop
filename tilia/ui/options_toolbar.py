from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QToolBar

from tilia.requests import Post, listen, post
from tilia.settings import settings
from tilia.ui.enums import ScrollType


class OptionsToolbar(QToolBar):
    def __init__(self):
        super().__init__()
        self.setObjectName("options_toolbar")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addWidget(QLabel("Auto-scroll"))
        self.combobox = QComboBox()
        for option in ScrollType.get_option_list():
            self.combobox.addItem(option.title())
        self.combobox.setCurrentText(
            ScrollType.get_str_from_enum(settings.get("general", "auto-scroll"))
        )
        self.combobox.currentTextChanged.connect(self.on_state_changed)
        self.addWidget(self.combobox)
        self.addSeparator()
        self.center_on_selection_checkbox = QCheckBox("Center on selection")
        # Clicking the checkbox must not steal keyboard focus from the
        # timelines: the whole point is to keep navigating with arrow keys.
        self.center_on_selection_checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.center_on_selection_checkbox.setToolTip(
            "Scroll the view to a newly selected element when it is out of view"
            " (e.g. when navigating with the arrow keys). Does not move the playhead."
        )
        self.center_on_selection_checkbox.setChecked(
            settings.get("general", "center_on_selection")
        )
        self.center_on_selection_checkbox.toggled.connect(
            self.on_center_on_selection_toggled
        )
        self.addWidget(self.center_on_selection_checkbox)
        listen(
            self,
            Post.SETTINGS_UPDATED,
            self.on_settings_updated,
        )

    def on_state_changed(self, option):
        scroll_type = ScrollType.get_enum_from_str(option)
        settings.set("general", "auto-scroll", scroll_type)
        post(Post.TIMELINES_AUTO_SCROLL_UPDATE, scroll_type)

    def on_center_on_selection_toggled(self, checked: bool):
        settings.set("general", "center_on_selection", checked)

    def on_settings_updated(self, updated_settings: list[str]):
        if "general" in updated_settings:
            scroll_type = settings.get("general", "auto-scroll")
            self.combobox.blockSignals(True)
            self.combobox.setCurrentText(ScrollType.get_str_from_enum(scroll_type))
            post(Post.TIMELINES_AUTO_SCROLL_UPDATE, scroll_type)
            self.combobox.blockSignals(False)

            self.center_on_selection_checkbox.blockSignals(True)
            self.center_on_selection_checkbox.setChecked(
                settings.get("general", "center_on_selection")
            )
            self.center_on_selection_checkbox.blockSignals(False)
