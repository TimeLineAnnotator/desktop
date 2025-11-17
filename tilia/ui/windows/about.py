from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QMainWindow,
    QScrollArea,
    QVBoxLayout,
)
from re import split, sub

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
        contact_fields = {
            "Website": tilia.constants.WEBSITE_URL,
            "GitHub": tilia.constants.GITHUB_URL,
            "Contact us": tilia.constants.EMAIL_URL,
        }
        contact_label = QLabel(
            " | ".join(
                [
                    f"<a href={link}>{label}</a>"
                    for label, link in contact_fields.items()
                ]
            )
        )
        contact_label.setOpenExternalLinks(True)
        contact_label.setTextFormat(Qt.TextFormat.RichText)
        contact_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        license_label = QLabel(
            f'<a href="#license">{tilia.constants.APP_NAME} Copyright © {tilia.constants.YEAR} {tilia.constants.AUTHOR}</a>'
        )
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license_label.linkActivated.connect(self.open_link)

        layout.addWidget(name_label)
        layout.addWidget(version_label)
        layout.addWidget(contact_label)
        layout.addSpacing(25)
        layout.addWidget(line)
        layout.addWidget(license_label)

        self.show()

        post(Post.WINDOW_OPEN_DONE, WindowKind.ABOUT)

    def open_link(self, link):
        match link:
            case "#license":
                License(self).show()

    def closeEvent(self, event):
        post(Post.WINDOW_CLOSE_DONE, WindowKind.ABOUT)
        return super().closeEvent(event)


class License(QDialog):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setWindowTitle("License")
        layout = QVBoxLayout()
        self.setLayout(layout)

        notice = QLabel(tilia.constants.NOTICE)
        notice.setWordWrap(True)

        with open(
            Path(__file__).parent.parent.parent.parent / "LICENSE", encoding="utf-8"
        ) as license_file:
            license_text = split(
                "How to Apply These Terms to Your New Programs", license_file.read()
            )[0]

        formatted_text = f'<pre style="white-space: pre-wrap;">{license_text}</pre>'
        text_with_links = sub(
            "<https:([^>]+)>",
            lambda y: f'<a href="{y[0][1:-1]}">{y[0][1:-1]}</a>',
            formatted_text,
        )

        license_text = QLabel(text_with_links)
        license_text.setTextFormat(Qt.TextFormat.RichText)
        license_text.setOpenExternalLinks(True)
        license_text.setContentsMargins(5, 5, 5, 5)

        license_scroll = QScrollArea()
        license_scroll.setWidget(license_text)
        license_scroll.setAutoFillBackground(False)
        license_scroll.setSizeAdjustPolicy(
            QScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        license_scroll.setWidgetResizable(True)
        license_scroll.setFrameShadow(QFrame.Shadow.Sunken)
        license_scroll.setFrameShape(QFrame.Shape.Panel)

        layout.addWidget(notice)
        layout.addWidget(license_scroll)
        layout.setSpacing(5)
