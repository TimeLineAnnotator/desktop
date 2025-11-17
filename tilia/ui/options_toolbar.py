from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolBar, QComboBox, QLabel

from tilia.settings import settings
from tilia.ui.enums import ScrollType
from tilia.requests import listen, Post, post


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
        listen(
            self,
            Post.SETTINGS_UPDATED,
            self.on_settings_updated,
        )

    def on_state_changed(self, option):
        scroll_type = ScrollType.get_enum_from_str(option)
        settings.set("general", "auto-scroll", scroll_type)
        post(Post.TIMELINES_AUTO_SCROLL_UPDATE, scroll_type)

    def on_settings_updated(self, updated_settings: list[str]):
        if "general" in updated_settings:
            scroll_type = settings.get("general", "auto-scroll")
            self.combobox.blockSignals(True)
            self.combobox.setCurrentText(ScrollType.get_str_from_enum(scroll_type))
            post(Post.TIMELINES_AUTO_SCROLL_UPDATE, scroll_type)
            self.combobox.blockSignals(False)
