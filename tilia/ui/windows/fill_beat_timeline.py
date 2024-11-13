from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator, QDoubleValidator
from PyQt6.QtWidgets import QButtonGroup, QGridLayout, QRadioButton, QLabel, QDialog, QDialogButtonBox, QComboBox, \
    QLineEdit

from tilia.requests import get, Get
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.strings import (
    BEAT_TIMELINE_BY_AMOUNT_OPTION,
    BEAT_TIMELINE_BY_AMOUNT_PLACEHOLDER,
    BEAT_TIMELINE_BY_INTERVAL_OPTION,
    BEAT_TIMELINE_BY_INTERVAL_PLACEHOLDER,
    BEAT_TIMELINE_FILL_PROMPT,
    BEAT_TIMELINE_FILL_TITLE,
)


class FillBeatTimeline(QDialog):
    def __init__(self):
        super().__init__(
            None, Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
        )
        self.setWindowTitle(BEAT_TIMELINE_FILL_TITLE)

        self.setLayout(QGridLayout())
        self.layout().setContentsMargins(5, 5, 5, 5)

        self._timeline_combobox = QComboBox()
        _by_amount_prompt = QRadioButton()
        self._by_amount_edit = QLineEdit()
        _by_interval = QRadioButton()
        self._by_interval_edit = QLineEdit()
        self._options = QButtonGroup(self)

        # setup method radio buttons
        _by_amount_prompt.setText(BEAT_TIMELINE_BY_AMOUNT_OPTION)
        _by_interval.setText(BEAT_TIMELINE_BY_INTERVAL_OPTION)

        self._options.addButton(_by_amount_prompt, 0)
        self._options.addButton(_by_interval, 1)
        _by_amount_prompt.setChecked(True)

        # setup line edits
        self._by_amount_edit.setValidator(QIntValidator())
        self._by_amount_edit.setPlaceholderText(BEAT_TIMELINE_BY_AMOUNT_PLACEHOLDER)
        self._by_interval_edit.setValidator(QDoubleValidator())
        self._by_interval_edit.setPlaceholderText(BEAT_TIMELINE_BY_INTERVAL_PLACEHOLDER)

        # setup combobox
        timelines = [tl for tl in get(Get.TIMELINES) if tl.KIND == TimelineKind.BEAT_TIMELINE]
        self._prompt = QLabel(BEAT_TIMELINE_FILL_PROMPT)
        for tl in timelines:
            self._timeline_combobox.addItem(tl.name, tl)

        # setup standard buttons
        _button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        _button_box.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(
            self.on_ok
        )
        _button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            self.reject
        )

        # add widgets to layout
        self.layout().addWidget(self._prompt, 0, 0)
        self.layout().addWidget(self._timeline_combobox, 0, 1)
        self.layout().addWidget(_by_amount_prompt, 1, 0)
        self.layout().addWidget(self._by_amount_edit, 1, 1)
        self.layout().addWidget(_by_interval, 2, 0)
        self.layout().addWidget(self._by_interval_edit, 2, 1)
        self.layout().addWidget(_button_box, 3, 0, 1, 2)

    def get_method(self) -> BeatTimeline.FillMethod:
        match self._options.checkedId():
            case 0:
                return BeatTimeline.FillMethod.BY_AMOUNT
            case 1:
                return BeatTimeline.FillMethod.BY_INTERVAL

    def get_timeline(self) -> BeatTimeline:
        return self._timeline_combobox.currentData()

    def get_value(self) -> float:
        if self.get_method() == BeatTimeline.FillMethod.BY_AMOUNT:
            return int(self._by_amount_edit.text())
        else:
            return float(self._by_interval_edit.text())

    @staticmethod
    def accent_invalid_input(widget: QLineEdit):
        widget.setStyleSheet('color: red; background-color: lightpink;')
        widget.textEdited.connect(lambda: widget.setStyleSheet(''))

    def on_ok(self):
        if self.get_method() == BeatTimeline.FillMethod.BY_AMOUNT:
            if not self._by_amount_edit.text():
                self.accent_invalid_input(self._by_amount_edit)
                return
        elif not self._by_interval_edit.text():
            self.accent_invalid_input(self._by_interval_edit)
            return
        else:
            self.accept()

    @classmethod
    def select(cls) -> tuple[bool, None | tuple[BeatTimeline, BeatTimeline.FillMethod, float]]:
        instance = cls()
        accepted = instance.exec()

        if accepted == QDialog.DialogCode.Accepted:
            return True, (instance.get_timeline(), instance.get_method(), instance.get_value())
        else:
            return False, None
