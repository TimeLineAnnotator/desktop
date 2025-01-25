from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QMainWindow, QDialog

import tilia.constants

from tilia.requests import Post, post
from tilia.ui.windows import WindowKind


class About(QDialog):
    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self.setWindowTitle(f"About {tilia.constants.APP_NAME}")
        layout = QVBoxLayout()

        self.setLayout(layout)

        name_label = QLabel(tilia.constants.APP_NAME)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label = QLabel("v" + tilia.constants.VERSION)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        site_label = QLabel(f'<a href="{tilia.constants.WEBSITE_URL}">Website</a>')
        site_label.setOpenExternalLinks(True)
        site_label.setTextFormat(Qt.TextFormat.RichText)
        site_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gh_label = QLabel(f'<a href="{tilia.constants.GITHUB_URL}">GitHub</a>')
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

        post(Post.WINDOW_OPEN_DONE, WindowKind.ABOUT)

    def closeEvent(self, event):
        post(Post.WINDOW_CLOSE_DONE, WindowKind.ABOUT)
        return super().closeEvent(event)
