from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QMainWindow, QDialog

import tilia.constants


class About(QDialog):
    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self.setWindowTitle(f"About {tilia.constants.APP_NAME}")
        layout = QVBoxLayout()

        self.setLayout(layout)

        name_label = QLabel(tilia.constants.APP_NAME)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label = QLabel(tilia.constants.VERSION)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        site_label = QLabel("https://tilia-ad98d.web.app")
        site_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gh_label = QLabel("github.com/FelipeDefensor/tilia")
        gh_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license_label = QLabel("License: CC BY-SA 4.0")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(name_label)
        layout.addWidget(version_label)
        layout.addWidget(site_label)
        layout.addWidget(gh_label)
        layout.addWidget(license_label)

        self.show()
