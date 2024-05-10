from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame


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
        exc_info_text_edit = QLabel(self.exception_info)
        exc_info_text_edit.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        exc_info_text_edit.setFrameShadow(QFrame.Shadow.Sunken)
        exc_info_text_edit.setFrameShape(QFrame.Shape.Box)
        unsaved_changes_label = QLabel('Unsaved work will be lost, but TiLiA autosaves your work periodically.\nTo access saved files, restart TiLiA and go to File > Autosaves.')
        unsaved_changes_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(sorry_label)
        layout.addWidget(exc_info_text_edit)
        layout.addWidget(unsaved_changes_label)

        # layout.setContentsMargins(10, 20, 20, 10)
        layout.setSpacing(5)