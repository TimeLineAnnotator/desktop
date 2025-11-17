from __future__ import annotations

from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QSizePolicy

from .qtplayer import QtPlayer
from tilia.ui.windows.view_window import ViewWindow


class QtVideoPlayer(QtPlayer):
    MEDIA_TYPE = "video"

    def __init__(self):
        super().__init__()
        self.widget = QVideoWindow()
        self.player.setVideoOutput(self.widget)

    def _engine_load_media(self, media_path: str) -> bool:
        result = super()._engine_load_media(media_path)
        if result:
            self.widget.show()
        return result

    def _engine_exit(self):
        super()._engine_exit()
        self.widget.deleteLater()


class QVideoWindow(ViewWindow, QVideoWidget):
    def __init__(self):
        super().__init__("TiLiA Player", menu_title="Video Player")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resize(800, 600)
