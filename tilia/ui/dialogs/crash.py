from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QVBoxLayout,
    QDialogButtonBox,
    QScrollArea,
    QCheckBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
)
from tilia.log import logger
from tilia.settings import settings
from tilia.utils import open_with_os


class CrashDialog(QDialog):
    def __init__(self, exception_info):
        super().__init__()
        self.exception_info = exception_info
        self.setWindowTitle("Error")
        self._setup_widgets()

    def _setup_widgets(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        sorry_label = QLabel("TiLiA has crashed with the following error:")
        sorry_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        exc_info_text_edit = QLabel(
            f"<pre style='white-space: pre-wrap;'>{self.exception_info}</pre>"
        )
        exc_info_text_edit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        exc_info_text_edit.setWordWrap(True)
        exc_info_text_edit.setContentsMargins(5, 5, 5, 5)

        exc_info_scroll = QScrollArea()
        exc_info_scroll.setWidget(exc_info_text_edit)
        exc_info_scroll.setAutoFillBackground(False)
        exc_info_scroll.setSizeAdjustPolicy(
            QScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        exc_info_scroll.setWidgetResizable(True)
        exc_info_scroll.setFrameShadow(QFrame.Shadow.Sunken)
        exc_info_scroll.setFrameShape(QFrame.Shape.Panel)

        unsaved_changes_label = QLabel(
            "Unsaved work will be lost, but TiLiA autosaves your work periodically.\nTo access saved files, restart TiLiA and go to File > Autosaves."
        )
        unsaved_changes_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.help_button = QPushButton("Contact Support")
        self.help_button.clicked.connect(self.get_help)

        layout.addWidget(sorry_label)
        layout.addWidget(exc_info_scroll)
        layout.addWidget(unsaved_changes_label)
        layout.addWidget(self.help_button)

        layout.setSpacing(5)

    def get_help(self):
        def update_text(submitted: bool):
            if submitted:
                self.help_button.setText("✅ Details submitted")
                self.help_button.setDisabled(True)

        support_dialog = CrashSupportDialog(self)
        support_dialog.show()
        support_dialog.finished.connect(update_text)


class CrashSupportDialog(QDialog):
    def __init__(self, parent) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Contact Support")
        self._setup_widgets()

    def _setup_widgets(self):
        self.setLayout(QFormLayout())

        header = QLabel(
            "We are sorry about the crash.\n Submit your contact details and we'll be in touch."
        )
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout().addRow(header)

        email, name = settings.get_user()

        self.name_field = QLineEdit(name)
        self.name_field.setMaximumHeight(50)
        self.layout().addRow("Name", self.name_field)

        self.email_field = QLineEdit(email)
        validator = QRegularExpressionValidator(
            QRegularExpression(
                r"\A[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\z"
            )
        )
        self.email_field.textChanged.connect(self.__validate_email)
        self.email_field.setValidator(validator)
        self.email_field.setMaximumHeight(50)
        self.layout().addRow("Email", self.email_field)

        self.remember = QCheckBox()
        self.remember.setChecked(bool(name or email))
        self.layout().addRow("Remember me", self.remember)

        file = QLabel(f'<a href="{logger.log_file_name}">{logger.log_file_name}</a>')
        file.linkActivated.connect(
            lambda: open_with_os(logger.log_file_name.resolve().parents[0])
        )
        self.layout().addRow("Attached log", file)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.submit_form)
        self.button_box.rejected.connect(self.reject)
        self.layout().addRow(self.button_box)

    def __validate_email(self):
        if self.email_field.hasAcceptableInput():
            self.email_field.setStyleSheet("")
        else:
            self.email_field.setStyleSheet("QLineEdit {border: 2px solid red;}")

    def submit_form(self):
        name = self.name_field.text()
        email = self.email_field.text() if self.email_field.hasAcceptableInput() else ""
        if name or email:
            if self.remember.isChecked():
                settings.set_user(email, name)
            logger.on_user_set(email, name)
            return self.accept()
        self.reject()
