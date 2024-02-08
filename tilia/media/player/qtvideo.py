from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QSizePolicy

from .qtplayer import QtPlayer

logger = logging.getLogger(__name__)


class QtVideoPlayer(QtPlayer):
    MEDIA_TYPE = "video"

    def __init__(self):
        super().__init__()
        self.widget = QVideoWidget()
        self.widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.player.setVideoOutput(self.widget)
        self.widget.setWindowTitle("TiLiA Player")
        self.widget.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.CustomizeWindowHint
        )
        self.widget.resize(800, 600)

    def _engine_load_media(self, media_path: str) -> bool:
        result = super()._engine_load_media(media_path)
        if result:
            self.widget.show()
        return result

    def _engine_exit(self):
        super()._engine_exit()
        self.widget.deleteLater()
