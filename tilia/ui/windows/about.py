from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QMainWindow, QDialog

import tilia.constants

from tilia.requests import Post, post

class About(QDialog):
    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self.setWindowTitle(f"About {tilia.constants.APP_NAME}")
        layout = QVBoxLayout()

        self.setLayout(layout)

        name_label = QLabel(tilia.constants.APP_NAME)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label = QLabel('v' + tilia.constants.VERSION)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        site_label = QLabel('<a href="https://tilia-ad98d.web.app/">Website</a>')
        site_label.setOpenExternalLinks(True)
        site_label.setTextFormat(Qt.TextFormat.RichText)
        site_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gh_label = QLabel('<a href="https://github.com/FelipeDefensor/TiLiA">GitHub</a>')
        gh_label.setOpenExternalLinks(True)
        gh_label.setTextFormat(Qt.TextFormat.RichText)
        gh_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license_label = QLabel("License: CC BY-SA 4.0")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(name_label)
        layout.addWidget(version_label)
        layout.addWidget(site_label)
        layout.addWidget(gh_label)
        layout.addWidget(license_label)

        self.show()

    def closeEvent(self, event):        
        post(Post.WINDOW_ABOUT_CLOSED)
        return super().closeEvent(event)