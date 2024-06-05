from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame, QScrollArea


class CrashDialog(QDialog):
    def __init__(self, exception_info):
        super().__init__()
        self.exception_info = exception_info
        self.setWindowTitle('Error')
        self._setup_widgets()

    def _setup_widgets(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        sorry_label = QLabel('TiLiA has crashed with the following error:')
        sorry_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        exc_info_text_edit = QLabel(f"<pre style='white-space: pre-wrap;'>{self.exception_info}</pre>")
        exc_info_text_edit.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        exc_info_text_edit.setWordWrap(True)
        exc_info_text_edit.setContentsMargins(5, 5, 5, 5)

        exc_info_scroll = QScrollArea()
        exc_info_scroll.setWidget(exc_info_text_edit)
        exc_info_scroll.setAutoFillBackground(False)
        exc_info_scroll.setSizeAdjustPolicy(QScrollArea.SizeAdjustPolicy.AdjustToContents)
        exc_info_scroll.setWidgetResizable(True)
        exc_info_scroll.setFrameShadow(QFrame.Shadow.Sunken)
        exc_info_scroll.setFrameShape(QFrame.Shape.Panel)

        unsaved_changes_label = QLabel('Unsaved work will be lost, but TiLiA autosaves your work periodically.\nTo access saved files, restart TiLiA and go to File > Autosaves.')
        unsaved_changes_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(sorry_label)
        layout.addWidget(exc_info_scroll)
        layout.addWidget(unsaved_changes_label)

        layout.setSpacing(5)