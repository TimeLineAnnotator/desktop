import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QRadioButton,
    QLabel,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
)

from tilia.requests import get, Get
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.strings import (
    BEAT_TIMELINE_BY_AMOUNT_OPTION,
    BEAT_TIMELINE_BY_AMOUNT_SUFFIX,
    BEAT_TIMELINE_BY_INTERVAL_OPTION,
    BEAT_TIMELINE_BY_INTERVAL_SUFFIX,
    BEAT_TIMELINE_FILL_PROMPT,
    BEAT_TIMELINE_FILL_TITLE,
)


class FillBeatTimeline(QDialog):
    def __init__(self):
        def get_result():
            checked_option = self._options.checkedId() % 2
            return (
                self._timeline_combobox.currentData(),
                BeatTimeline.FillMethod(checked_option),
                (
                    self._by_interval_edit.value()
                    if checked_option
                    else self._by_amount_edit.value()
                ),
            )

        super().__init__(
            None, Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
        )
        self.setWindowTitle(BEAT_TIMELINE_FILL_TITLE)

        self.setLayout(QGridLayout())
        self.layout().setContentsMargins(5, 5, 5, 5)

        self._timeline_combobox = QComboBox()
        _by_amount_prompt = QRadioButton()
        self._by_amount_edit = QSpinBox()
        _by_interval_prompt = QRadioButton()
        self._by_interval_edit = QDoubleSpinBox()
        self._options = QButtonGroup(self)

        # setup method radio buttons
        _by_amount_prompt.setText(BEAT_TIMELINE_BY_AMOUNT_OPTION)
        _by_amount_prompt.toggled.connect(
            lambda checked: self._by_amount_edit.setEnabled(checked)
        )
        _by_interval_prompt.setText(BEAT_TIMELINE_BY_INTERVAL_OPTION)
        _by_interval_prompt.toggled.connect(
            lambda checked: self._by_interval_edit.setEnabled(checked)
        )

        self._options.addButton(_by_amount_prompt, 0)
        self._options.addButton(_by_interval_prompt, 1)
        _by_amount_prompt.setChecked(True)

        # setup line edits
        self._by_amount_edit.setRange(1, 2147483647)
        self._by_amount_edit.setSuffix(BEAT_TIMELINE_BY_AMOUNT_SUFFIX)
        self._by_amount_edit.setValue(1)
        self._by_interval_edit.setRange(sys.float_info.min, 60)
        self._by_interval_edit.setSuffix(BEAT_TIMELINE_BY_INTERVAL_SUFFIX)
        self._by_interval_edit.setValue(1)
        self._by_interval_edit.setEnabled(False)

        # setup combobox
        timelines = [
            tl for tl in get(Get.TIMELINES) if tl.KIND == TimelineKind.BEAT_TIMELINE
        ]
        self._prompt = QLabel(BEAT_TIMELINE_FILL_PROMPT)
        for tl in timelines:
            self._timeline_combobox.addItem(tl.name, tl)

        # setup standard buttons
        _button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        _button_box.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(
            self.accept
        )
        _button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            self.reject
        )

        # add widgets to layout
        self.layout().addWidget(self._prompt, 0, 0)
        self.layout().addWidget(self._timeline_combobox, 0, 1)
        self.layout().addWidget(_by_amount_prompt, 1, 0)
        self.layout().addWidget(self._by_amount_edit, 1, 1)
        self.layout().addWidget(_by_interval_prompt, 2, 0)
        self.layout().addWidget(self._by_interval_edit, 2, 1)
        self.layout().addWidget(_button_box, 3, 0, 1, 2)
        self.get_result = get_result

    @classmethod
    def select(
        cls,
    ) -> tuple[bool, None | tuple[BeatTimeline, BeatTimeline.FillMethod, float]]:
        instance = cls()
        if instance.exec() == QDialog.DialogCode.Accepted:
            return True, instance.get_result()
        else:
            return False, None
