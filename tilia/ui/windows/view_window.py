from PyQt6.QtCore import Qt
from tilia.requests import get, Get, post, Post, listen
from tilia.ui.enums import WindowState


class ViewWindow:
    def __init__(self, os_window_title: str, *args, **kwargs):
        menu_title = kwargs.pop("menu_title", os_window_title)
        super().__init__(*args, **kwargs)
        self.setWindowTitle(os_window_title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.id = get(Get.ID)
        post(Post.WINDOW_UPDATE_STATE, self.id, WindowState.CLOSED, menu_title)
        listen(self, Post.WINDOW_UPDATE_REQUEST, self.on_update_request)

    def showEvent(self, event):
        post(Post.WINDOW_UPDATE_STATE, self.id, WindowState.OPENED)
        super().showEvent(event)

    def closeEvent(self, event):
        post(Post.WINDOW_UPDATE_STATE, self.id, WindowState.CLOSED)
        event.ignore()
        self.hide()

    def on_update_request(self, window_id: int, to_show: bool) -> None:
        if window_id == self.id:
            self.blockSignals(True)
            if to_show:
                self.showNormal()
            else:
                self.hide()
            self.blockSignals(False)

    def deleteLater(self):
        post(Post.WINDOW_UPDATE_STATE, self.id, WindowState.DELETED)
        super().deleteLater()

    def update_title(self, title: str):
        post(Post.WINDOW_UPDATE_STATE, self.id, WindowState.UPDATE, title)
